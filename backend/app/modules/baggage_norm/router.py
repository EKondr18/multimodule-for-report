from datetime import date
from io import BytesIO, StringIO

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/baggage-norm", tags=["baggage-norm"])

MASTER_PATH = "data/baggage_norm/master.csv"
DATALENS_PATH = "data/baggage_norm/datalens.csv"


def _load_master():
    import pandas as pd
    from app.core import github_storage
    from app.modules.baggage_norm.processing import empty_master

    content, sha = github_storage.read_file(MASTER_PATH)
    if content is None:
        return empty_master(), None
    df = pd.read_csv(StringIO(content))
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df, sha


def _load_datalens():
    import pandas as pd
    from app.core import github_storage
    from app.modules.baggage_norm.processing import DATALENS_COLUMNS

    content, sha = github_storage.read_file(DATALENS_PATH)
    if content is None:
        return pd.DataFrame(columns=DATALENS_COLUMNS), None
    return pd.read_csv(StringIO(content)), sha


def _merge_datalens(existing, df_new):
    """Чистая функция без сетевых вызовов: дописывает производные строки
    новой выгрузки поверх уже загруженного datalens.csv.

    Как и в merge_with_master, дедупликация ищет совпадения только среди
    строк, чья дата попадает в диапазон новой выгрузки (сравнение по строкам
    "YYYY-MM-DD" — лексикографический порядок совпадает с хронологическим),
    а не по всему архиву — он уже дедуплицирован раньше."""
    import pandas as pd
    from app.modules.baggage_norm.processing import derive_datalens

    new_rows = derive_datalens(df_new).copy()
    new_rows["date"] = new_rows["date"].dt.strftime("%Y-%m-%d")

    if existing.empty:
        combined = new_rows.drop_duplicates()
    else:
        period_start = new_rows["date"].min()
        period_end = new_rows["date"].max()
        in_period_mask = (existing["date"] >= period_start) & (existing["date"] <= period_end)

        untouched = existing[~in_period_mask]
        in_period = pd.concat([existing[in_period_mask], new_rows], ignore_index=True)
        in_period = in_period.drop_duplicates()

        combined = pd.concat([untouched, in_period], ignore_index=True)
    return combined.sort_values("date").reset_index(drop=True)


@router.post("/process")
async def process_weekly_file(file: UploadFile):
    import asyncio

    from app.core import github_storage
    from app.modules.baggage_norm.processing import merge_with_master, read_weekly_excel

    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Ожидается файл Excel (.xlsx/.xls)")

    raw = await file.read()
    try:
        df_new = read_weekly_excel(BytesIO(raw))
    except Exception as exc:
        raise HTTPException(400, f"Не удалось разобрать файл: {exc}") from exc

    # master.csv и datalens.csv независимы друг от друга — читаем и потом
    # пишем их параллельно (2 сетевых похода к GitHub вместо 4 последовательных),
    # т.к. каждый Contents API round-trip может занимать заметное время, а на
    # Vercel Hobby жёсткий лимит на выполнение функции — 10 секунд.
    (df_master, master_sha), (existing_datalens, datalens_sha) = await asyncio.gather(
        asyncio.to_thread(_load_master),
        asyncio.to_thread(_load_datalens),
    )

    combined_master = merge_with_master(df_master, df_new)
    combined_datalens = _merge_datalens(existing_datalens, df_new)

    commit_message = f"baggage_norm: добавлена выгрузка от {date.today().isoformat()} (+{len(df_new)} строк)"
    await asyncio.gather(
        asyncio.to_thread(
            github_storage.write_file,
            MASTER_PATH, combined_master.to_csv(index=False), commit_message, master_sha,
        ),
        asyncio.to_thread(
            github_storage.write_file,
            DATALENS_PATH, combined_datalens.to_csv(index=False), commit_message, datalens_sha,
        ),
    )

    return {
        "added": len(df_new),
        "total": len(combined_datalens),
    }


@router.get("/download")
def download_datalens_csv(start_date: str | None = None, end_date: str | None = None):
    import pandas as pd
    from app.core import github_storage
    from app.modules.baggage_norm.processing import derive_datalens

    content, _ = github_storage.read_file(DATALENS_PATH)
    if content is None:
        df_master, _ = _load_master()
        datalens = derive_datalens(df_master)
    else:
        datalens = pd.read_csv(StringIO(content))

    if start_date or end_date:
        try:
            parsed_start = pd.to_datetime(start_date) if start_date else None
            parsed_end = pd.to_datetime(end_date) if end_date else None
        except ValueError as exc:
            raise HTTPException(400, f"Некорректная дата: {exc}") from exc
        if parsed_start is not None and parsed_end is not None and parsed_start > parsed_end:
            raise HTTPException(400, "Дата начала периода позже даты окончания")

        dates = pd.to_datetime(datalens["date"])
        mask = pd.Series(True, index=datalens.index)
        if parsed_start is not None:
            mask &= dates >= parsed_start
        if parsed_end is not None:
            mask &= dates <= parsed_end
        datalens = datalens[mask]
        filename = f"bagazh_dlya_datalens_{start_date or 'nachalo'}_{end_date or 'konec'}.csv"
    else:
        filename = "bagazh_dlya_datalens.csv"

    return StreamingResponse(
        iter([datalens.to_csv(index=False)]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

from datetime import date
from io import BytesIO, StringIO

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/baggage-norm", tags=["baggage-norm"])

# Архив хранится по одному файлу на месяц (data/baggage_norm/master/YYYY-MM.csv
# и .../datalens/YYYY-MM.csv), а не одним вечно растущим файлом — иначе
# каждая еженедельная загрузка перезаписывает через GitHub API весь архив
# целиком (сейчас это уже 80000+ строк), и один только base64-запрос на
# запись такого объёма упирается в лимит выполнения функции на Vercel.
#
# LEGACY_*_PATH — старые монолитные файлы, которые существовали до перехода
# на помесячное хранение. Их никто больше не перезаписывает. При первом
# обращении к месяцу, для которого ещё нет отдельного файла, история за этот
# месяц один раз подтягивается оттуда (см. _load_month) — дальше все запросы
# идут только к маленькому месячному файлу. /download продолжает читать
# LEGACY-файлы наравне с месячными, чтобы не потерять историю, которая ещё
# не была затронута ни одной новой загрузкой.
MASTER_DIR = "data/baggage_norm/master"
DATALENS_DIR = "data/baggage_norm/datalens"
LEGACY_MASTER_PATH = "data/baggage_norm/master.csv"
LEGACY_DATALENS_PATH = "data/baggage_norm/datalens.csv"


def _month_key(ts) -> str:
    return ts.strftime("%Y-%m")


def _load_legacy_master():
    import pandas as pd
    from app.core import github_storage
    from app.modules.baggage_norm.processing import empty_master

    content, _ = github_storage.read_file(LEGACY_MASTER_PATH)
    if content is None:
        return empty_master()
    df = pd.read_csv(StringIO(content))
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def _load_legacy_datalens():
    import pandas as pd
    from app.core import github_storage
    from app.modules.baggage_norm.processing import DATALENS_COLUMNS

    content, _ = github_storage.read_file(LEGACY_DATALENS_PATH)
    if content is None:
        return pd.DataFrame(columns=DATALENS_COLUMNS)
    return pd.read_csv(StringIO(content))


def _merge_datalens(existing, df_new):
    """Чистая функция без сетевых вызовов: дописывает производные строки
    новой выгрузки поверх уже загруженного datalens.csv за месяц.

    Дедупликация ищет совпадения только среди строк, чья дата попадает в
    диапазон новой выгрузки (сравнение по строкам "YYYY-MM-DD" —
    лексикографический порядок совпадает с хронологическим)."""
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


def _process_month_sync(m, df_new_month, commit_message, legacy_master, legacy_datalens):
    """Синхронная read-merge-write операция для одного месяца, с повтором
    при конфликте версий (кто-то — например, параллельный повторный запрос
    с фронтенда — успел записать этот же файл между нашим чтением и записью).

    Раньше конфликт при записи (GithubException 409/422) просто вылетал
    исключением из asyncio.gather и обрывал ответ, из-за чего запись за
    один из месяцев многострочной выгрузки могла тихо потеряться, если
    несколько одновременных попыток загрузки гонялись за один и тот же
    новый файл (см. баг с пропавшими данными за август при повторных
    попытках после «пробуждения» Render). Теперь при конфликте состояние
    перечитывается заново и merge повторяется на актуальных данных."""
    import pandas as pd
    from github import GithubException

    from app.core import github_storage
    from app.modules.baggage_norm.processing import (
        DATALENS_COLUMNS, empty_master, merge_with_master,
    )

    master_path = f"{MASTER_DIR}/{m}.csv"
    datalens_path = f"{DATALENS_DIR}/{m}.csv"

    max_attempts = 5
    for attempt in range(max_attempts):
        master_content, master_sha = github_storage.read_file(master_path)
        if master_content is not None:
            df_master_existing = pd.read_csv(StringIO(master_content))
            if not df_master_existing.empty:
                df_master_existing["date"] = pd.to_datetime(df_master_existing["date"])
        elif legacy_master is not None and not legacy_master.empty:
            month_mask = legacy_master["date"].apply(_month_key) == m
            df_master_existing = legacy_master[month_mask].reset_index(drop=True)
        else:
            df_master_existing = empty_master()

        datalens_content, datalens_sha = github_storage.read_file(datalens_path)
        if datalens_content is not None:
            df_datalens_existing = pd.read_csv(StringIO(datalens_content))
        elif legacy_datalens is not None and not legacy_datalens.empty:
            month_mask = legacy_datalens["date"].astype(str).str.startswith(m)
            df_datalens_existing = legacy_datalens[month_mask].reset_index(drop=True)
        else:
            df_datalens_existing = pd.DataFrame(columns=DATALENS_COLUMNS)

        combined_master = merge_with_master(df_master_existing, df_new_month)
        combined_datalens = _merge_datalens(df_datalens_existing, df_new_month)

        try:
            github_storage.write_file(
                master_path, combined_master.to_csv(index=False), commit_message, master_sha,
            )
            github_storage.write_file(
                datalens_path, combined_datalens.to_csv(index=False), commit_message, datalens_sha,
            )
            return
        except GithubException as exc:
            if exc.status in (409, 422) and attempt < max_attempts - 1:
                continue
            raise


@router.post("/process")
async def process_weekly_file(file: UploadFile):
    import asyncio
    import time

    from app.modules.baggage_norm.processing import read_weekly_excel

    t0 = time.perf_counter()

    def _log(label: str) -> None:
        print(f"[baggage_norm/process] {label}: {time.perf_counter() - t0:.2f}s", flush=True)

    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Ожидается файл Excel (.xlsx/.xls)")

    raw = await file.read()
    _log(f"file read from request ({len(raw)/1e6:.2f} MB)")
    try:
        df_new = read_weekly_excel(BytesIO(raw))
    except Exception as exc:
        raise HTTPException(400, f"Не удалось разобрать файл: {exc}") from exc
    _log(f"xlsx parsed ({len(df_new)} строк)")

    df_new = df_new.copy()
    df_new["_month"] = df_new["date"].apply(_month_key)
    months = sorted(df_new["_month"].unique())
    _log(f"months detected: {months}")

    # Легаси-архив подтягиваем не по разу на месяц, а максимум один раз за
    # весь запрос — но только если хотя бы для одного из месяцев ещё нет
    # своего файла (дешёвый список файлов в директории вместо полного чтения
    # каждого месячного файла).
    from app.core import github_storage
    existing_master_months = {
        p.rsplit("/", 1)[-1].removesuffix(".csv")
        for p in await asyncio.to_thread(github_storage.list_files, MASTER_DIR)
    }
    if any(m not in existing_master_months for m in months):
        legacy_master, legacy_datalens = await asyncio.gather(
            asyncio.to_thread(_load_legacy_master),
            asyncio.to_thread(_load_legacy_datalens),
        )
        _log(f"legacy archive read (master {len(legacy_master)} строк, datalens {len(legacy_datalens)} строк)")
    else:
        legacy_master, legacy_datalens = None, None
        _log("legacy archive skipped (every month already has its own file)")

    commit_message = f"baggage_norm: добавлена выгрузка от {date.today().isoformat()} (+{len(df_new)} строк)"

    await asyncio.gather(*[
        asyncio.to_thread(
            _process_month_sync,
            m,
            df_new[df_new["_month"] == m].drop(columns=["_month"]),
            commit_message,
            legacy_master,
            legacy_datalens,
        )
        for m in months
    ])
    _log("all months written")

    months_str = ", ".join(months)
    return {"added": len(df_new), "months": months_str}


@router.get("/download")
async def download_datalens_csv(start_date: str | None = None, end_date: str | None = None):
    import asyncio

    import pandas as pd
    from app.core import github_storage
    from app.modules.baggage_norm.processing import DATALENS_COLUMNS

    try:
        parsed_start = pd.to_datetime(start_date) if start_date else None
        parsed_end = pd.to_datetime(end_date) if end_date else None
    except ValueError as exc:
        raise HTTPException(400, f"Некорректная дата: {exc}") from exc
    if parsed_start is not None and parsed_end is not None and parsed_start > parsed_end:
        raise HTTPException(400, "Дата начала периода позже даты окончания")

    month_paths = await asyncio.to_thread(github_storage.list_files, DATALENS_DIR)
    if parsed_start is not None or parsed_end is not None:
        lo = parsed_start.strftime("%Y-%m") if parsed_start is not None else "0000-00"
        hi = parsed_end.strftime("%Y-%m") if parsed_end is not None else "9999-99"
        month_paths = [
            p for p in month_paths
            if lo <= p.rsplit("/", 1)[-1].removesuffix(".csv") <= hi
        ]

    # Читаем все нужные месячные файлы (и legacy-архив) параллельно —
    # при полной выгрузке это может быть десяток+ файлов.
    read_results = await asyncio.gather(
        *[asyncio.to_thread(github_storage.read_file, p) for p in month_paths],
        asyncio.to_thread(github_storage.read_file, LEGACY_DATALENS_PATH),
    )
    contents = [content for content, _sha in read_results]

    frames = [pd.read_csv(StringIO(c)) for c in contents if c]
    if frames:
        datalens = pd.concat(frames, ignore_index=True).drop_duplicates()
    else:
        datalens = pd.DataFrame(columns=DATALENS_COLUMNS)

    if parsed_start is not None or parsed_end is not None:
        dates = pd.to_datetime(datalens["date"]) if not datalens.empty else datalens["date"]
        mask = pd.Series(True, index=datalens.index)
        if parsed_start is not None:
            mask &= dates >= parsed_start
        if parsed_end is not None:
            mask &= dates <= parsed_end
        datalens = datalens[mask]
        filename = f"bagazh_dlya_datalens_{start_date or 'nachalo'}_{end_date or 'konec'}.csv"
    else:
        filename = "bagazh_dlya_datalens.csv"

    datalens = datalens.sort_values("date") if not datalens.empty else datalens

    return StreamingResponse(
        iter([datalens.to_csv(index=False)]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

from datetime import date
from io import BytesIO, StringIO

import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.core import github_storage
from app.modules.baggage_norm.processing import (
    DATALENS_COLUMNS,
    derive_datalens,
    empty_master,
    merge_with_master,
    read_weekly_excel,
)

router = APIRouter(prefix="/api/baggage-norm", tags=["baggage-norm"])

MASTER_PATH = "data/baggage_norm/master.csv"
DATALENS_PATH = "data/baggage_norm/datalens.csv"


def _load_master() -> tuple[pd.DataFrame, str | None]:
    content, sha = github_storage.read_file(MASTER_PATH)
    if content is None:
        return empty_master(), None
    df = pd.read_csv(StringIO(content))
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df, sha


def _load_datalens() -> tuple[pd.DataFrame, str | None]:
    content, sha = github_storage.read_file(DATALENS_PATH)
    if content is None:
        return pd.DataFrame(columns=DATALENS_COLUMNS), None
    return pd.read_csv(StringIO(content)), sha


def _rows(datalens: pd.DataFrame) -> list[dict]:
    return datalens.to_dict(orient="records")


def _append_to_datalens(df_new: pd.DataFrame, message: str) -> pd.DataFrame:
    """Дописывает производные строки новой загрузки в общий накопительный
    datalens.csv (не пересчитывает его из master.csv — иначе была бы потеряна
    история, заведённая до появления приложения)."""
    new_rows = derive_datalens(df_new).copy()
    new_rows["date"] = new_rows["date"].dt.strftime("%Y-%m-%d")

    existing, sha = _load_datalens()
    combined = pd.concat([existing, new_rows], ignore_index=True).drop_duplicates()
    combined = combined.sort_values("date").reset_index(drop=True)

    github_storage.write_file(DATALENS_PATH, combined.to_csv(index=False), message=message, sha=sha)
    return combined


@router.get("/current")
def get_current():
    datalens, _ = _load_datalens()
    return {"rows": _rows(datalens), "total": len(datalens)}


@router.post("/process")
async def process_weekly_file(file: UploadFile):
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Ожидается файл Excel (.xlsx/.xls)")

    raw = await file.read()
    try:
        df_new = read_weekly_excel(BytesIO(raw))
    except Exception as exc:
        raise HTTPException(400, f"Не удалось разобрать файл: {exc}") from exc

    df_master, sha = _load_master()
    combined_master = merge_with_master(df_master, df_new)

    commit_message = f"baggage_norm: добавлена выгрузка от {date.today().isoformat()} (+{len(df_new)} строк)"
    github_storage.write_file(MASTER_PATH, combined_master.to_csv(index=False), message=commit_message, sha=sha)
    datalens = _append_to_datalens(df_new, message=commit_message)

    return {
        "rows": _rows(datalens),
        "added": len(df_new),
        "total": len(datalens),
    }


@router.get("/download")
def download_datalens_csv():
    content, _ = github_storage.read_file(DATALENS_PATH)
    if content is None:
        df_master, _ = _load_master()
        content = derive_datalens(df_master).to_csv(index=False)
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="bagazh_dlya_datalens.csv"'
        },
    )

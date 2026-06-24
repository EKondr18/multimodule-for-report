from datetime import date
from io import BytesIO, StringIO

import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.core import github_storage
from app.modules.baggage_norm.processing import (
    derive_datalens,
    empty_master,
    merge_with_master,
    read_weekly_excel,
)

router = APIRouter(prefix="/api/baggage-norm", tags=["baggage-norm"])

MASTER_PATH = "data/baggage_norm/master.csv"


def _load_master() -> tuple[pd.DataFrame, str | None]:
    content, sha = github_storage.read_file(MASTER_PATH)
    if content is None:
        return empty_master(), None
    df = pd.read_csv(StringIO(content))
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df, sha


def _datalens_rows(df_master: pd.DataFrame) -> list[dict]:
    datalens = derive_datalens(df_master).copy()
    if not datalens.empty:
        datalens["date"] = datalens["date"].dt.strftime("%Y-%m-%d")
    return datalens.to_dict(orient="records")


@router.get("/current")
def get_current():
    df_master, _ = _load_master()
    return {"rows": _datalens_rows(df_master), "total": len(df_master)}


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
    combined = merge_with_master(df_master, df_new)

    github_storage.write_file(
        MASTER_PATH,
        combined.to_csv(index=False),
        message=f"baggage_norm: добавлена выгрузка от {date.today().isoformat()} (+{len(df_new)} строк)",
        sha=sha,
    )

    return {
        "rows": _datalens_rows(combined),
        "added": len(df_new),
        "total": len(combined),
    }


@router.get("/download")
def download_datalens_csv():
    df_master, _ = _load_master()
    datalens = derive_datalens(df_master)
    buffer = StringIO()
    datalens.to_csv(buffer, index=False, encoding="utf-8")
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="bagazh_dlya_datalens.csv"'
        },
    )

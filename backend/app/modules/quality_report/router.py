from io import BytesIO

import pandas as pd
from fastapi import APIRouter, Form, HTTPException, UploadFile

from app.modules.quality_report.processing import (
    GRANULARITIES,
    build_violations_tables,
    read_violations_file,
)

router = APIRouter(prefix="/api/quality-report", tags=["quality-report"])


@router.post("/violations")
async def violations_summary(
    perron_file: UploadFile,
    avk_file: UploadFile,
    start_date: str = Form(...),
    end_date: str = Form(...),
    granularity: str = Form(...),
):
    if granularity not in GRANULARITIES:
        raise HTTPException(400, f"Неизвестный временной срез: {granularity}")
    if not perron_file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "«Нарушения на перроне» — ожидается excel-файл")
    if not avk_file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "«Нарушения в АВК» — ожидается excel-файл")

    try:
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
    except ValueError as exc:
        raise HTTPException(400, f"Некорректная дата: {exc}") from exc
    if start > end:
        raise HTTPException(400, "Дата начала периода позже даты окончания")

    perron_raw = await perron_file.read()
    avk_raw = await avk_file.read()
    try:
        df_perron = read_violations_file(BytesIO(perron_raw))
        df_avk = read_violations_file(BytesIO(avk_raw))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"Не удалось разобрать файл: {exc}") from exc

    tables = build_violations_tables(df_perron, df_avk, start, end, granularity)
    return {"tables": tables}

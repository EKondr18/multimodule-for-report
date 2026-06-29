from io import BytesIO

import pandas as pd
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.modules.quality_report.processing import (
    FO_SIZ_CHECKS_SHEET,
    GRANULARITIES,
    PAB_FO_ETHICS_SHEET,
    PAB_PT_SHEET,
    PAB_RK_SHEET,
    RPO_CHECKS_SHEET,
    build_quality_tables,
    read_grh_checks_sheet,
    read_lir_szv_file,
    read_pab_checks_sheet,
    read_violations_file,
)

router = APIRouter(prefix="/api/quality-report", tags=["quality-report"])


def _check_excel_filename(file: UploadFile, label: str) -> None:
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, f"«{label}» — ожидается excel-файл")


@router.post("/summary")
async def quality_summary(
    perron_file: UploadFile | None = File(None),
    avk_file: UploadFile | None = File(None),
    grh_file: UploadFile | None = File(None),
    lir_file: UploadFile | None = File(None),
    pab_file: UploadFile | None = File(None),
    start_date: str = Form(...),
    end_date: str = Form(...),
    granularity: str = Form(...),
):
    if granularity not in GRANULARITIES:
        raise HTTPException(400, f"Неизвестный временной срез: {granularity}")

    try:
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
    except ValueError as exc:
        raise HTTPException(400, f"Некорректная дата: {exc}") from exc
    if start > end:
        raise HTTPException(400, "Дата начала периода позже даты окончания")

    df_perron = None
    df_avk = None
    df_grh_rpo = None
    df_grh_fo_siz = None
    df_lir = None
    df_pab_fo_ethics = None
    df_pab_rk = None
    df_pab_pt = None

    try:
        if perron_file is not None and perron_file.filename:
            _check_excel_filename(perron_file, "Нарушения на перроне")
            df_perron = read_violations_file(BytesIO(await perron_file.read()))
        if avk_file is not None and avk_file.filename:
            _check_excel_filename(avk_file, "Нарушения в АВК")
            df_avk = read_violations_file(BytesIO(await avk_file.read()))
        if grh_file is not None and grh_file.filename:
            _check_excel_filename(grh_file, "Проверки GRH")
            grh_raw = await grh_file.read()
            df_grh_rpo = read_grh_checks_sheet(BytesIO(grh_raw), RPO_CHECKS_SHEET)
            df_grh_fo_siz = read_grh_checks_sheet(BytesIO(grh_raw), FO_SIZ_CHECKS_SHEET)
        if lir_file is not None and lir_file.filename:
            _check_excel_filename(lir_file, "Мониторинг LIR/СЗВ")
            df_lir = read_lir_szv_file(BytesIO(await lir_file.read()))
        if pab_file is not None and pab_file.filename:
            _check_excel_filename(pab_file, "Проверки PAB")
            pab_raw = await pab_file.read()
            df_pab_fo_ethics = read_pab_checks_sheet(BytesIO(pab_raw), PAB_FO_ETHICS_SHEET)
            df_pab_rk = read_pab_checks_sheet(BytesIO(pab_raw), PAB_RK_SHEET)
            df_pab_pt = read_pab_checks_sheet(BytesIO(pab_raw), PAB_PT_SHEET)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"Не удалось разобрать файл: {exc}") from exc

    tables = build_quality_tables(
        df_perron,
        df_avk,
        df_grh_rpo,
        df_grh_fo_siz,
        df_lir,
        df_pab_fo_ethics,
        df_pab_rk,
        df_pab_pt,
        start,
        end,
        granularity,
    )
    return {"tables": tables}

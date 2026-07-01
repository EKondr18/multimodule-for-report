from io import BytesIO

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

router = APIRouter(prefix="/api/month-report", tags=["month-report"])


def _check_excel(file: UploadFile, label: str) -> None:
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, f"«{label}» — ожидается excel-файл")


ALLOWED_GRANULARITIES = {"month", "quarter", "year"}


@router.post("/summary")
async def month_summary(
    perron_file: UploadFile | None = File(None),
    avk_file: UploadFile | None = File(None),
    appeals_file: UploadFile | None = File(None),
    production_file: UploadFile | None = File(None),
    start_date: str = Form(...),
    end_date: str = Form(...),
    granularity: str = Form("month"),
):
    import pandas as pd
    from app.modules.month_report.processing import (
        build_month_tables,
        read_appeals_file,
        read_avk_full,
        read_perron_full,
        read_production_file,
    )

    if granularity not in ALLOWED_GRANULARITIES:
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
    df_appeals = None
    production_data = None

    try:
        if perron_file is not None and perron_file.filename:
            _check_excel(perron_file, "Нарушения на перроне")
            df_perron = read_perron_full(BytesIO(await perron_file.read()))
        if avk_file is not None and avk_file.filename:
            _check_excel(avk_file, "Нарушения в АВК")
            df_avk = read_avk_full(BytesIO(await avk_file.read()))
        if appeals_file is not None and appeals_file.filename:
            _check_excel(appeals_file, "Обращения")
            df_appeals = read_appeals_file(BytesIO(await appeals_file.read()))
        if production_file is not None and production_file.filename:
            _check_excel(production_file, "Производственные показатели")
            production_data = read_production_file(BytesIO(await production_file.read()))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"Не удалось разобрать файл: {exc}") from exc

    tables = build_month_tables(df_perron, df_avk, df_appeals, production_data, start, end, granularity)
    return {"tables": tables}

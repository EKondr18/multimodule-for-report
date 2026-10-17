import asyncio
import hashlib
from io import BytesIO

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.request_cache import dedup
from app.core.upload_limits import read_upload_limited
from app.core.validation import check_excel_filename as _check_excel

router = APIRouter(prefix="/api/month-report", tags=["month-report"])


ALLOWED_GRANULARITIES = {"month", "quarter", "year"}


def _build_summary(
    perron_bytes: bytes | None,
    avk_bytes: bytes | None,
    appeals_bytes: bytes | None,
    production_bytes: bytes | None,
    start_date: str,
    end_date: str,
    granularity: str,
) -> dict:
    """Синхронная (блокирующая) часть — весь pandas-разбор и построение
    таблиц. Вызывается через asyncio.to_thread по тому же принципу, что и
    в quality_report/router.py — см. комментарий там и в
    app/core/request_cache.py."""
    import pandas as pd
    from app.modules.month_report.processing import (
        build_month_tables,
        read_appeals_file,
        read_avk_full,
        read_perron_full_variants,
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
    df_perron_tdb = None
    df_avk = None
    df_appeals = None
    production_data = None

    try:
        if perron_bytes is not None:
            # Книга парсится один раз, а не по разу на каждый вариант дедупа
            # (стандартный + с Исполнителем для таблицы 14) — см. processing.py.
            df_perron, df_perron_tdb = read_perron_full_variants(BytesIO(perron_bytes))
        if avk_bytes is not None:
            df_avk = read_avk_full(BytesIO(avk_bytes))
        if appeals_bytes is not None:
            df_appeals = read_appeals_file(BytesIO(appeals_bytes))
        if production_bytes is not None:
            production_data = read_production_file(BytesIO(production_bytes))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"Не удалось разобрать файл: {exc}") from exc

    tables = build_month_tables(
        df_perron, df_avk, df_appeals, production_data, start, end, granularity,
        df_perron_tdb=df_perron_tdb,
    )
    return {"tables": tables}


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
    perron_bytes = None
    avk_bytes = None
    appeals_bytes = None
    production_bytes = None

    if perron_file is not None and perron_file.filename:
        _check_excel(perron_file, "Нарушения на перроне")
        perron_bytes = await read_upload_limited(perron_file)
    if avk_file is not None and avk_file.filename:
        _check_excel(avk_file, "Нарушения в АВК")
        avk_bytes = await read_upload_limited(avk_file)
    if appeals_file is not None and appeals_file.filename:
        _check_excel(appeals_file, "Обращения")
        appeals_bytes = await read_upload_limited(appeals_file)
    if production_file is not None and production_file.filename:
        _check_excel(production_file, "Производственные показатели")
        production_bytes = await read_upload_limited(production_file)

    # Дедупликация повторных попыток fetchWithWakeup — см. комментарий в
    # quality_report/router.py и app/core/request_cache.py.
    hasher = hashlib.sha256()
    for chunk in (perron_bytes, avk_bytes, appeals_bytes, production_bytes):
        hasher.update(b"\0" if chunk is None else chunk)
        hasher.update(b"|")
    hasher.update(f"{start_date}|{end_date}|{granularity}".encode())
    cache_key = hasher.hexdigest()

    async def compute() -> dict:
        return await asyncio.to_thread(
            _build_summary,
            perron_bytes,
            avk_bytes,
            appeals_bytes,
            production_bytes,
            start_date,
            end_date,
            granularity,
        )

    return await dedup(cache_key, compute)

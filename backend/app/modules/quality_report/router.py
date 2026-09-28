import asyncio
import hashlib
from io import BytesIO

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.request_cache import dedup

router = APIRouter(prefix="/api/quality-report", tags=["quality-report"])


def _check_excel_filename(file: UploadFile, label: str) -> None:
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, f"«{label}» — ожидается excel-файл")


def _build_summary(
    perron_bytes: bytes | None,
    avk_bytes: bytes | None,
    grh_bytes: bytes | None,
    lir_bytes: bytes | None,
    pab_bytes: bytes | None,
    start_date: str,
    end_date: str,
    granularity: str,
) -> dict:
    """Синхронная (блокирующая) часть — весь pandas-разбор и построение
    таблиц. Вызывается через asyncio.to_thread, чтобы не блокировать event
    loop на время расчёта — иначе повторная попытка (см. fetchWithWakeup на
    фронтенде) не смогла бы попасть в dedup() и дождаться результата первой
    попытки, а встала бы в очередь позади неё."""
    import pandas as pd
    from app.modules.quality_report.processing import (
        FO_SIZ_CHECKS_SHEET,
        GRANULARITIES,
        PAB_BAGGAGE_SHEET,
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
    df_pab_baggage = None

    try:
        if perron_bytes is not None:
            df_perron = read_violations_file(BytesIO(perron_bytes))
        if avk_bytes is not None:
            df_avk = read_violations_file(BytesIO(avk_bytes))
        if grh_bytes is not None:
            # Одна книга парсится один раз, а не по разу на каждый лист —
            # раньше pd.ExcelFile(...) пересобирался с нуля для каждого листа.
            grh_xl = pd.ExcelFile(BytesIO(grh_bytes))
            df_grh_rpo = read_grh_checks_sheet(grh_xl, RPO_CHECKS_SHEET)
            df_grh_fo_siz = read_grh_checks_sheet(grh_xl, FO_SIZ_CHECKS_SHEET)
        if lir_bytes is not None:
            df_lir = read_lir_szv_file(BytesIO(lir_bytes))
        if pab_bytes is not None:
            pab_xl = pd.ExcelFile(BytesIO(pab_bytes))
            df_pab_fo_ethics = read_pab_checks_sheet(pab_xl, PAB_FO_ETHICS_SHEET)
            df_pab_rk = read_pab_checks_sheet(pab_xl, PAB_RK_SHEET)
            df_pab_pt = read_pab_checks_sheet(pab_xl, PAB_PT_SHEET)
            df_pab_baggage = read_pab_checks_sheet(pab_xl, PAB_BAGGAGE_SHEET)
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
        df_pab_baggage,
        start,
        end,
        granularity,
    )
    return {"tables": tables}


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
    perron_bytes = None
    avk_bytes = None
    grh_bytes = None
    lir_bytes = None
    pab_bytes = None

    if perron_file is not None and perron_file.filename:
        _check_excel_filename(perron_file, "Нарушения на перроне")
        perron_bytes = await perron_file.read()
    if avk_file is not None and avk_file.filename:
        _check_excel_filename(avk_file, "Нарушения в АВК")
        avk_bytes = await avk_file.read()
    if grh_file is not None and grh_file.filename:
        _check_excel_filename(grh_file, "Проверки GRH")
        grh_bytes = await grh_file.read()
    if lir_file is not None and lir_file.filename:
        _check_excel_filename(lir_file, "Мониторинг LIR/СЗВ")
        lir_bytes = await lir_file.read()
    if pab_file is not None and pab_file.filename:
        _check_excel_filename(pab_file, "Проверки PAB")
        pab_bytes = await pab_file.read()

    # Дедупликация: fetchWithWakeup на фронтенде при обрыве соединения
    # повторяет тот же запрос (те же файлы, те же параметры) до 10 раз
    # подряд. Без этого каждая повторная попытка запускала бы тот же
    # тяжёлый разбор+сравнение заново, не давая предыдущей попытке
    # спокойно доработать — см. app/core/request_cache.py.
    hasher = hashlib.sha256()
    for chunk in (perron_bytes, avk_bytes, grh_bytes, lir_bytes, pab_bytes):
        hasher.update(b"\0" if chunk is None else chunk)
        hasher.update(b"|")
    hasher.update(f"{start_date}|{end_date}|{granularity}".encode())
    cache_key = hasher.hexdigest()

    async def compute() -> dict:
        return await asyncio.to_thread(
            _build_summary,
            perron_bytes,
            avk_bytes,
            grh_bytes,
            lir_bytes,
            pab_bytes,
            start_date,
            end_date,
            granularity,
        )

    return await dedup(cache_key, compute)

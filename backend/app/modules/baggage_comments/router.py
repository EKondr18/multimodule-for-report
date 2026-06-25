import base64
from io import BytesIO

from fastapi import APIRouter, Form, HTTPException, UploadFile

from app.modules.baggage_comments.processing import (
    TBS_OUTPUT_COLUMNS,
    merge_comments,
    merge_tbs,
    read_events_file,
    read_norm_file,
    read_tbs_events_file,
    read_tbs_flights_file,
)

router = APIRouter(prefix="/api/baggage-comments", tags=["baggage-comments"])

SUPPORTED_STATIONS = {"vko", "tbs"}


def _to_xlsx_base64(df) -> str:
    buffer = BytesIO()
    df.to_excel(buffer, index=False, engine="openpyxl")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


@router.post("/process")
async def process_files(
    norm_file: UploadFile,
    events_file: UploadFile,
    station: str = Form("vko"),
):
    if station not in SUPPORTED_STATIONS:
        raise HTTPException(400, f"Обработка для станции {station.upper()} ещё не реализована")

    if station == "vko":
        if not norm_file.filename.lower().endswith(".csv"):
            raise HTTPException(400, "«Норматив выдачи багажа» — ожидается csv-файл")
        if not events_file.filename.lower().endswith((".xlsx", ".xls")):
            raise HTTPException(400, "«События по выдаче» — ожидается excel-файл")

        norm_raw = await norm_file.read()
        events_raw = await events_file.read()
        try:
            df_norm = read_norm_file(BytesIO(norm_raw))
            df_events = read_events_file(BytesIO(events_raw))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(400, f"Не удалось разобрать файл: {exc}") from exc

        merged = merge_comments(df_norm, df_events)
        return {
            "rows": merged.to_dict(orient="records"),
            "total": len(merged),
            "xlsx_base64": _to_xlsx_base64(merged),
        }

    # station == "tbs"
    if not norm_file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "«Рейсы из TBS (прилет)» — ожидается excel-файл")
    if not events_file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "«События по багажу» — ожидается excel-файл")

    flights_raw = await norm_file.read()
    events_raw = await events_file.read()
    try:
        df_flights = read_tbs_flights_file(BytesIO(flights_raw))
        df_events = read_tbs_events_file(BytesIO(events_raw))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"Не удалось разобрать файл: {exc}") from exc

    merged = merge_tbs(df_flights, df_events)
    totals = {
        col: int(merged[col].sum())
        for col in TBS_OUTPUT_COLUMNS
        if col not in ("Дата рейса", "Номер рейса")
    }

    return {
        "rows": merged.to_dict(orient="records"),
        "total": len(merged),
        "totals": totals,
        "xlsx_base64": _to_xlsx_base64(merged),
    }

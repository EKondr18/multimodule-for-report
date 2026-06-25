import base64
from io import BytesIO

from fastapi import APIRouter, Form, HTTPException, UploadFile

from app.modules.baggage_comments.processing import merge_comments, read_events_file, read_norm_file

router = APIRouter(prefix="/api/baggage-comments", tags=["baggage-comments"])

SUPPORTED_STATIONS = {"vko"}


@router.post("/process")
async def process_files(
    norm_file: UploadFile,
    events_file: UploadFile,
    station: str = Form("vko"),
):
    if station not in SUPPORTED_STATIONS:
        raise HTTPException(400, f"Обработка для станции {station.upper()} ещё не реализована")
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

    buffer = BytesIO()
    merged.to_excel(buffer, index=False, engine="openpyxl")
    xlsx_base64 = base64.b64encode(buffer.getvalue()).decode("ascii")

    return {
        "rows": merged.to_dict(orient="records"),
        "total": len(merged),
        "xlsx_base64": xlsx_base64,
    }

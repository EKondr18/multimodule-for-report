from io import BytesIO

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/tech-dedup", tags=["tech-dedup"])


@router.post("/process")
async def process_file(file: UploadFile):
    from app.modules.tech_dedup.processing import remove_duplicates

    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Ожидается файл Excel (.xlsx/.xls)")

    raw = await file.read()
    try:
        cleaned_bytes, initial_rows, final_rows = remove_duplicates(BytesIO(raw))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"Не удалось обработать файл: {exc}") from exc

    removed = initial_rows - final_rows
    filename = file.filename.rsplit(".", 1)[0] + "_cleaned.xlsx"

    return StreamingResponse(
        iter([cleaned_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Initial-Rows": str(initial_rows),
            "X-Final-Rows": str(final_rows),
            "X-Removed-Rows": str(removed),
            "Access-Control-Expose-Headers": "X-Initial-Rows, X-Final-Rows, X-Removed-Rows",
        },
    )

"""Единый лимит размера загружаемых файлов.

Реальные xlsx-выгрузки в этом приложении — порядка 10-20 МБ. 50 МБ даёт
комфортный запас сверху и при этом отсекает абсурдно большие/ошибочные
загрузки, которые на бесплатном тарифе Render (512 МБ RAM) могут просто
уложить процесс при разборе pandas'ом.
"""

from fastapi import HTTPException, UploadFile

MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024  # 50 МБ


def _human_mb(num_bytes: int) -> str:
    return f"{num_bytes / (1024 * 1024):.0f} МБ"


async def read_upload_limited(file: UploadFile, max_size: int = MAX_UPLOAD_SIZE_BYTES) -> bytes:
    """Читает файл целиком, но прерывается с 413, если он больше max_size.

    Не полагается только на заголовок Content-Length (он может быть не
    передан клиентом, например при chunked-передаче) — читает чанками и
    считает фактический размер, останавливаясь, как только лимит
    превышен, не дожидаясь полной загрузки лишних данных в память.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_size:
            raise HTTPException(
                413,
                f"«{file.filename}» превышает допустимый размер файла "
                f"({_human_mb(max_size)})",
            )
        chunks.append(chunk)
    return b"".join(chunks)

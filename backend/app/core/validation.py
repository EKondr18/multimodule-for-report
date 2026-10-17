"""Общая валидация загружаемых файлов, общая для всех роутеров-модулей."""

from fastapi import HTTPException, UploadFile


def check_filename_extension(file: UploadFile, label: str, extensions: tuple[str, ...]) -> None:
    """Проверяет расширение имени файла (без учёта регистра) и бросает
    HTTPException(400) с понятным сообщением на русском, если оно не
    входит в допустимый список."""
    if not file.filename.lower().endswith(extensions):
        expected = "/".join(ext.lstrip(".") for ext in extensions)
        raise HTTPException(400, f"«{label}» — ожидается файл формата {expected}")


def check_excel_filename(file: UploadFile, label: str) -> None:
    check_filename_extension(file, label, (".xlsx", ".xls"))

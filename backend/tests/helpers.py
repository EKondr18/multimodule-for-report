"""Общие помощники для тестов: сборка синтетических excel-файлов."""

from io import BytesIO

import pandas as pd

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def make_xlsx(sheets: dict[str, pd.DataFrame]) -> bytes:
    """Excel-книга в байтах: по одному листу на ключ словаря."""
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)
    return buf.getvalue()


def make_weekly_xlsx(rows: list[tuple[str, str, str]]) -> bytes:
    """Выгрузка «BI МАВ» в формате, который ждёт read_weekly_excel:
    8 строк шапки, затем данные. Колонки, которые модуль не читает, пустые.

    rows: (дата "dd.mm.yy", номер рейса, номер места/mc)."""
    width = 29  # len(COLUMN_NAMES) в baggage_norm/processing.py
    # Последняя колонка заполнена, иначе pandas при чтении обрежет пустые
    # хвостовые колонки и разбор упадёт на проверке числа колонок.
    header = [[f"шапка {i}"] + [None] * (width - 2) + ["x"] for i in range(8)]
    body = []
    for date_str, flight, mc in rows:
        line = [None] * width
        line[0] = date_str
        line[1] = flight
        line[4] = mc
        line[-1] = "x"
        body.append(line)
    df = pd.DataFrame(header + body)
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Sheet1", index=False, header=False)
    return buf.getvalue()

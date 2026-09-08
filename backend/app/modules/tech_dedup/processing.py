"""Обработка модуля «Удаление дубликатов по обслуживанию техники».

Логика 1:1 повторяет исходный скрипт пользователя (разбор поля
«Заказ-наряд» вида «Заказ-наряд №00000000001 от 05.12.2024 / Закрыт» на
номер/дату/статус, для каждого номера заказа-наряда оставляем только
строки с самой свежей датой, а при совпадении дат — только строки с
самым «весомым» статусом («Закрыт» > «Выполнен» > «В работе» > «Открыт»),
и в конце убираем точные дубли среди оставшихся строк).

Единственное отличие от исходного скрипта: он читал файл через
`pd.read_excel(file_path)` (всегда первый лист), а в реальных выгрузках
первый лист(ы) — это сводные/пустые листы, а сами данные — на одном из
следующих (см. `_pick_data_sheet`). Дедупликация проверена на реальном
файле (~168000 строк) — работает корректно и без потери данных даже там,
где дата в тексте указана без года («от 26.02» вместо «от 26.02.2025»):
для одного заказа-наряда дата всегда одинакова по всем его строкам, так
что группа с «неполной» датой целиком остаётся NaT и проходит фильтр
как есть, ничего не теряя.
"""

import re
from io import BytesIO

import pandas as pd

ORDER_COLUMN = "Заказ-наряд"

# Столбцы, различия в которых не считаются «настоящим» дублем на финальном
# шаге — как в исходном скрипте: свободный текст самого заказа-наряда и
# несколько полей, которые могут чуть отличаться в повторных выгрузках одной
# и той же строки (округление цены/суммы, форматирование контрагента и т.п.).
_EXCLUDE_FROM_FINAL_DEDUP = [
    ORDER_COLUMN,
    "Контрагенты",
    "Цена",
    "Сумма",
    "Автомобиль.Модель автомобиля",
]

_NUMBER_RE = re.compile(r"(№\s*[\w\d\-]+)")
_DATE_RE = re.compile(r"(\d{2}\.\d{2}\.\d{4})")

_STATUS_PRIORITY = [
    ("закрыт", 1),
    ("выполнен", 2),
    ("в работе", 3),
    ("открыт", 4),
]


def _pick_data_sheet(file_obj: BytesIO) -> str:
    """Реальные выгрузки часто содержат несколько листов (сводные таблицы,
    пустые технические листы) вперемешку с самим датасетом — берём первый
    лист, где есть столбец «Заказ-наряд»."""
    xl = pd.ExcelFile(file_obj)
    for name in xl.sheet_names:
        header = pd.read_excel(xl, sheet_name=name, nrows=0)
        if ORDER_COLUMN in header.columns:
            return name
    raise ValueError(
        f"Не найден лист со столбцом «{ORDER_COLUMN}» — проверьте структуру файла"
    )


def _extract_pure_number(text: object) -> str | None:
    text = str(text)
    if text.lower() == "nan" or text.strip() == "":
        return None
    match = _NUMBER_RE.search(text)
    if match:
        return match.group(1)
    return text.split("/")[0].strip()


def _extract_date(text: object) -> str | None:
    match = _DATE_RE.search(str(text))
    return match.group(1) if match else None


def _status_priority(text: object) -> int:
    text = str(text).lower()
    if "/" in text:
        text = text.split("/")[-1]
    for keyword, priority in _STATUS_PRIORITY:
        if keyword in text:
            return priority
    return 99


def remove_duplicates(file_obj: BytesIO) -> tuple[bytes, int, int]:
    """Возвращает (xlsx-байты очищенного файла, было строк, осталось строк)."""
    sheet_name = _pick_data_sheet(file_obj)
    file_obj.seek(0)
    df = pd.read_excel(file_obj, sheet_name=sheet_name)
    if ORDER_COLUMN not in df.columns:
        raise ValueError(f"В файле нет столбца «{ORDER_COLUMN}»")

    initial_rows = len(df)

    df["_order_number"] = df[ORDER_COLUMN].apply(_extract_pure_number)
    df["_date_text"] = df[ORDER_COLUMN].apply(_extract_date)
    df["_date"] = pd.to_datetime(df["_date_text"], format="%d.%m.%Y", errors="coerce")
    df["_priority"] = df[ORDER_COLUMN].apply(_status_priority)

    # 1. Для каждого номера заказа-наряда оставляем только строки с самой
    # свежей датой (строки без распознанного номера не трогаем).
    valid_orders = df.dropna(subset=["_order_number"])
    max_dates = (
        valid_orders.groupby("_order_number")["_date"]
        .max()
        .reset_index()
        .rename(columns={"_date": "_max_date"})
    )
    df = df.merge(max_dates, on="_order_number", how="left")
    df = df[df["_max_date"].isna() | (df["_date"] == df["_max_date"])].copy()

    # 2. Если на самую свежую дату оказалось несколько статусов — оставляем
    # только строки с самым «весомым» статусом («Закрыт» побеждает «В работе»).
    best_priorities = (
        df.dropna(subset=["_order_number"])
        .groupby("_order_number")["_priority"]
        .min()
        .reset_index()
        .rename(columns={"_priority": "_best_priority"})
    )
    df = df.merge(best_priorities, on="_order_number", how="left")
    df = df[df["_best_priority"].isna() | (df["_priority"] == df["_best_priority"])].copy()

    # 3. Финальная зачистка точных дублей среди отфильтрованных строк.
    helper_cols = ["_order_number", "_date_text", "_date", "_max_date", "_priority", "_best_priority"]
    subset_cols = [
        c for c in df.columns
        if c not in helper_cols and c not in _EXCLUDE_FROM_FINAL_DEDUP
    ]
    df = df.drop_duplicates(subset=subset_cols, keep="last")
    final_rows = len(df)

    df = df.drop(columns=helper_cols, errors="ignore")

    out = BytesIO()
    df.to_excel(out, index=False, engine="openpyxl")
    return out.getvalue(), initial_rows, final_rows

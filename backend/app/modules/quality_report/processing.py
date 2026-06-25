"""Обработка модуля «Отчёт по качеству», раздел «Нарушения».

На вход — выгрузки нарушений по перрону и АВК (лист «ТАБЛИЦА» в каждом
файле, с разным регистром колонки даты — «Дата»/«дата» — и разным набором
остальных колонок). Для таблицы 1 нужны дата и категория нарушения; для детализирующих таблиц
(1.1 и 2.1) — также описание, исполнитель и подразделение; для таблицы 2
(только файл «Перрон») — дополнительно подкатегория и причина.

Данные за выбранный период агрегируются по срезам (неделя/месяц/квартал/
год) календарными границами, с обрезкой первого и последнего интервала по
границам периода — например, период 08.06.2026-21.06.2026 со срезом
«неделя» даёт два интервала: 08.06-14.06 и 15.06-21.06.
"""

from io import BytesIO

import pandas as pd

VIOLATIONS_SHEET = "ТАБЛИЦА"

GRANULARITIES = {"week", "month", "quarter", "year"}

ALCOHOL_CATEGORY = "Алкогольное и наркотическое опъянение"

INSTALLATION_CATEGORY = "Встреча ВС на МС"
INSTALLATION_SUBCATEGORY = "Установка ВС на допустимые точки"

REASON_KVS_BRAKING = "Несвоевременное торможение КВС"
REASON_OUT_OF_VIEW = "Невозможно оценить (вне ракурса СОК)"
REASON_AOOPO = "Вина АООПО"


def _find_column(columns: list[str], name: str) -> str | None:
    name = name.strip().lower()
    for col in columns:
        if str(col).strip().lower() == name:
            return col
    return None


def read_violations_file(file_obj: BytesIO) -> pd.DataFrame:
    df = pd.read_excel(file_obj, sheet_name=VIOLATIONS_SHEET)
    columns = list(df.columns)

    date_col = _find_column(columns, "дата")
    category_col = _find_column(columns, "категория")
    if date_col is None or category_col is None:
        raise ValueError("В файле нарушений нет колонок «Дата» и/или «Категория»")

    subcategory_col = _find_column(columns, "подкатегория")
    reason_col = _find_column(columns, "причина")
    description_col = _find_column(columns, "описание")
    executor_col = _find_column(columns, "исполнитель")
    department_col = _find_column(columns, "подразделение")

    rename = {date_col: "date", category_col: "category"}
    keep = [date_col, category_col]
    for col, key in (
        (subcategory_col, "subcategory"),
        (reason_col, "reason"),
        (description_col, "description"),
        (executor_col, "executor"),
        (department_col, "department"),
    ):
        if col is not None:
            rename[col] = key
            keep.append(col)

    result = df[keep].rename(columns=rename)
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    result = result.dropna(subset=["date"])
    result["category"] = result["category"].astype(str).str.strip()
    for key in ("subcategory", "reason", "description", "executor", "department"):
        if key not in result.columns:
            result[key] = None
        else:
            stripped = result[key].apply(lambda v: str(v).strip() if pd.notna(v) else None)
            result[key] = stripped.where(stripped != "", None)
    return result


def _period_end(cur: pd.Timestamp, granularity: str) -> pd.Timestamp:
    if granularity == "week":
        return cur + pd.Timedelta(days=6)
    if granularity == "month":
        return cur + pd.offsets.MonthEnd(0)
    if granularity == "quarter":
        return cur + pd.offsets.QuarterEnd(0)
    if granularity == "year":
        return cur + pd.offsets.YearEnd(0)
    raise ValueError(f"Неизвестный временной срез: {granularity}")


def generate_buckets(
    start: pd.Timestamp, end: pd.Timestamp, granularity: str
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    if granularity not in GRANULARITIES:
        raise ValueError(f"Неизвестный временной срез: {granularity}")

    buckets = []
    cur = start
    while cur <= end:
        nominal_end = _period_end(cur, granularity)
        bucket_end = min(nominal_end, end)
        buckets.append((cur, bucket_end))
        cur = nominal_end + pd.Timedelta(days=1)
    return buckets


MONTH_NAMES = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]


def _format_period(start: pd.Timestamp, end: pd.Timestamp, granularity: str) -> str:
    if granularity == "week":
        return f"{start.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}"
    if granularity == "month":
        return f"{MONTH_NAMES[start.month - 1]} {start.year}"
    if granularity == "quarter":
        quarter = (start.month - 1) // 3 + 1
        return f"{quarter} квартал {start.year}"
    if granularity == "year":
        return str(start.year)
    raise ValueError(f"Неизвестный временной срез: {granularity}")


def build_category_count_table(
    df: pd.DataFrame,
    category: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    granularity: str,
) -> list[dict]:
    in_period = df[(df["date"] >= start) & (df["date"] <= end) & (df["category"] == category)]
    buckets = generate_buckets(start, end, granularity)

    rows = []
    for bucket_start, bucket_end in buckets:
        count = int(((in_period["date"] >= bucket_start) & (in_period["date"] <= bucket_end)).sum())
        rows.append({"Период": _format_period(bucket_start, bucket_end, granularity), "Кол-во": count})
    return rows


def _classify_reason(reason: str | None) -> str | None:
    if reason is None or (not isinstance(reason, str) and pd.isna(reason)):
        return None
    text = str(reason).lower()
    if "несвоевременное торможение" in text:
        return REASON_KVS_BRAKING
    if "вне ракурса" in text or "сок" in text:
        return REASON_OUT_OF_VIEW
    return REASON_AOOPO


def _installation_subset(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    in_period = df[
        (df["date"] >= start)
        & (df["date"] <= end)
        & (df["category"] == INSTALLATION_CATEGORY)
        & (df["subcategory"] == INSTALLATION_SUBCATEGORY)
    ].copy()
    in_period["reason_bucket"] = in_period["reason"].apply(_classify_reason)
    return in_period[in_period["reason_bucket"].notna()]


def build_installation_table(
    df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, granularity: str
) -> list[dict]:
    in_period = _installation_subset(df, start, end)
    buckets = generate_buckets(start, end, granularity)

    rows = []
    for bucket_start, bucket_end in buckets:
        bucket_data = in_period[(in_period["date"] >= bucket_start) & (in_period["date"] <= bucket_end)]
        counts = bucket_data["reason_bucket"].value_counts()
        rows.append(
            {
                "Период": _format_period(bucket_start, bucket_end, granularity),
                REASON_KVS_BRAKING: int(counts.get(REASON_KVS_BRAKING, 0)),
                REASON_OUT_OF_VIEW: int(counts.get(REASON_OUT_OF_VIEW, 0)),
                REASON_AOOPO: int(counts.get(REASON_AOOPO, 0)),
            }
        )
    return rows


def _str_or_blank(value) -> str:
    return value if isinstance(value, str) else ""


def _detail_rows(df: pd.DataFrame) -> list[dict]:
    return [
        {
            "Описание": _str_or_blank(row["description"]),
            "Исполнитель": _str_or_blank(row["executor"]),
            "Подразделение": _str_or_blank(row["department"]),
        }
        for _, row in df.iterrows()
    ]


def build_installation_aoopo_detail(
    df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> list[dict]:
    in_period = _installation_subset(df, start, end)
    aoopo = in_period[in_period["reason_bucket"] == REASON_AOOPO]
    return _detail_rows(aoopo)


def build_alcohol_detail(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> list[dict]:
    in_period = df[
        (df["date"] >= start) & (df["date"] <= end) & (df["category"] == ALCOHOL_CATEGORY)
    ]
    return _detail_rows(in_period)


def build_violations_tables(
    df_perron: pd.DataFrame,
    df_avk: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    granularity: str,
) -> list[dict]:
    combined = pd.concat([df_perron, df_avk], ignore_index=True)

    alcohol_rows = build_category_count_table(combined, ALCOHOL_CATEGORY, start, end, granularity)
    alcohol_detail_rows = build_alcohol_detail(combined, start, end)
    installation_rows = build_installation_table(df_perron, start, end, granularity)
    installation_aoopo_rows = build_installation_aoopo_detail(df_perron, start, end)

    detail_columns = ["Описание", "Исполнитель", "Подразделение"]

    return [
        {
            "id": "alcohol",
            "title": "1. Алкогольное/наркотическое опьянение",
            "columns": ["Период", "Кол-во"],
            "rows": alcohol_rows,
        },
        {
            "id": "alcohol_detail",
            "title": "1.1. Алкогольное/наркотическое опьянение — детализация",
            "columns": detail_columns,
            "rows": alcohol_detail_rows,
        },
        {
            "id": "installation",
            "title": "2. Установка ВС не по разметке",
            "columns": ["Период", REASON_KVS_BRAKING, REASON_OUT_OF_VIEW, REASON_AOOPO],
            "rows": installation_rows,
        },
        {
            "id": "installation_aoopo_detail",
            "title": "2.1. Вина АООПО — детализация",
            "columns": detail_columns,
            "rows": installation_aoopo_rows,
        },
    ]

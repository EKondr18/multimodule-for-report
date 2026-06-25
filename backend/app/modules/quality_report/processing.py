"""Обработка модуля «Отчёт по качеству» — единый набор таблиц без разделения
на разделы Нарушения/Проверки/Мониторинг.

На вход — до трёх независимо загружаемых excel-файлов: «Нарушения на
перроне», «Нарушения в АВК» (лист «ТАБЛИЦА» в каждом, с разным регистром
колонки даты — «Дата»/«дата» — и разным набором остальных колонок) и
«Проверки GRH» (лист «РПО»). Каждая таблица строится из того, что
загружено; если для неё не хватает нужного файла — вместо данных
выводится отметка `NOT_UPLOADED` ("Файл не загружен"), на уровне всей
таблицы (1, 1.1, 2, 2.1) либо на уровне отдельных ячеек, если в одной
таблице разные колонки зависят от разных файлов (3).

Для таблицы 1 нужны дата и категория нарушения; для детализирующих таблиц
(1.1 и 2.1) — также описание, исполнитель и подразделение; для таблицы 2
(только файл «Перрон») — дополнительно подкатегория и причина; для
таблицы 3 — подкатегория и заключение (файл «Перрон») плюс дата из файла
GRH. Строки в детализирующих таблицах сортируются по дате от старых к
новым.

Данные за выбранный период агрегируются по срезам (неделя/месяц/квартал/
год) календарными границами, с обрезкой первого и последнего интервала по
границам периода — например, период 08.06.2026-21.06.2026 со срезом
«неделя» даёт два интервала: 08.06-14.06 и 15.06-21.06.
"""

from io import BytesIO

import pandas as pd

VIOLATIONS_SHEET = "ТАБЛИЦА"
RPO_CHECKS_SHEET = "РПО"

GRANULARITIES = {"week", "month", "quarter", "year"}

ALCOHOL_CATEGORY = "Алкогольное и наркотическое опъянение"

INSTALLATION_CATEGORY = "Встреча ВС на МС"
INSTALLATION_SUBCATEGORY = "Установка ВС на допустимые точки"

REASON_KVS_BRAKING = "Несвоевременное торможение КВС"
REASON_OUT_OF_VIEW = "Невозможно оценить (вне ракурса СОК)"
REASON_AOOPO = "Вина АООПО"

RPO_SUBCATEGORY = "Руководство подъездом /отъездом;"
RPO_CONCLUSION = "с виной"

NOT_UPLOADED = "Файл не загружен"


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
    conclusion_col = _find_column(columns, "заключение")

    rename = {date_col: "date", category_col: "category"}
    keep = [date_col, category_col]
    for col, key in (
        (subcategory_col, "subcategory"),
        (reason_col, "reason"),
        (description_col, "description"),
        (executor_col, "executor"),
        (department_col, "department"),
        (conclusion_col, "conclusion"),
    ):
        if col is not None:
            rename[col] = key
            keep.append(col)

    result = df[keep].rename(columns=rename)
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    result = result.dropna(subset=["date"])
    result["category"] = result["category"].astype(str).str.strip()
    for key in ("subcategory", "reason", "description", "executor", "department", "conclusion"):
        if key not in result.columns:
            result[key] = None
        else:
            stripped = result[key].apply(lambda v: str(v).strip() if pd.notna(v) else None)
            result[key] = stripped.where(stripped != "", None)
    return result


def read_rpo_checks_file(file_obj: BytesIO) -> pd.DataFrame:
    df = pd.read_excel(file_obj, sheet_name=RPO_CHECKS_SHEET)
    columns = list(df.columns)

    date_col = _find_column(columns, "дата")
    if date_col is None:
        raise ValueError("В файле проверок РПО нет колонки «Дата»")

    result = df[[date_col]].rename(columns={date_col: "date"})
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    return result.dropna(subset=["date"])


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
            "Дата": row["date"].strftime("%d.%m.%Y"),
            "Описание": _str_or_blank(row["description"]),
            "Исполнитель": _str_or_blank(row["executor"]),
            "Подразделение": _str_or_blank(row["department"]),
        }
        for _, row in df.sort_values("date").iterrows()
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


def build_checks_table(
    df_grh: pd.DataFrame | None,
    df_perron: pd.DataFrame | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
    granularity: str,
) -> list[dict]:
    buckets = generate_buckets(start, end, granularity)

    complaints = None
    if df_perron is not None:
        complaints = df_perron[
            (df_perron["subcategory"] == RPO_SUBCATEGORY) & (df_perron["conclusion"] == RPO_CONCLUSION)
        ]

    rows = []
    for bucket_start, bucket_end in buckets:
        row = {"Период": _format_period(bucket_start, bucket_end, granularity)}
        if df_grh is None:
            row["Кол-во проверок"] = NOT_UPLOADED
        else:
            in_bucket = df_grh[(df_grh["date"] >= bucket_start) & (df_grh["date"] <= bucket_end)]
            row["Кол-во проверок"] = int(len(in_bucket))
        if complaints is None:
            row["Кол-во замечаний"] = NOT_UPLOADED
        else:
            in_bucket = complaints[(complaints["date"] >= bucket_start) & (complaints["date"] <= bucket_end)]
            row["Кол-во замечаний"] = int(len(in_bucket))
        rows.append(row)
    return rows


def _not_uploaded_table(table_id: str, title: str, columns: list[str]) -> dict:
    return {"id": table_id, "title": title, "columns": columns, "message": NOT_UPLOADED, "rows": []}


def build_quality_tables(
    df_perron: pd.DataFrame | None,
    df_avk: pd.DataFrame | None,
    df_grh: pd.DataFrame | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
    granularity: str,
) -> list[dict]:
    detail_columns = ["Дата", "Описание", "Исполнитель", "Подразделение"]
    available = [df for df in (df_perron, df_avk) if df is not None]
    combined = pd.concat(available, ignore_index=True) if available else None

    if combined is not None:
        alcohol_table = {
            "id": "alcohol",
            "title": "1. Алкогольное/наркотическое опьянение",
            "columns": ["Период", "Кол-во"],
            "rows": build_category_count_table(combined, ALCOHOL_CATEGORY, start, end, granularity),
        }
        alcohol_detail_table = {
            "id": "alcohol_detail",
            "title": "1.1. Алкогольное/наркотическое опьянение — детализация",
            "columns": detail_columns,
            "rows": build_alcohol_detail(combined, start, end),
        }
    else:
        alcohol_table = _not_uploaded_table("alcohol", "1. Алкогольное/наркотическое опьянение", ["Период", "Кол-во"])
        alcohol_detail_table = _not_uploaded_table(
            "alcohol_detail", "1.1. Алкогольное/наркотическое опьянение — детализация", detail_columns
        )

    if df_perron is not None:
        installation_table = {
            "id": "installation",
            "title": "2. Установка ВС не по разметке",
            "columns": ["Период", REASON_KVS_BRAKING, REASON_OUT_OF_VIEW, REASON_AOOPO],
            "rows": build_installation_table(df_perron, start, end, granularity),
        }
        installation_detail_table = {
            "id": "installation_aoopo_detail",
            "title": "2.1. Вина АООПО — детализация",
            "columns": detail_columns,
            "rows": build_installation_aoopo_detail(df_perron, start, end),
        }
    else:
        installation_table = _not_uploaded_table(
            "installation",
            "2. Установка ВС не по разметке",
            ["Период", REASON_KVS_BRAKING, REASON_OUT_OF_VIEW, REASON_AOOPO],
        )
        installation_detail_table = _not_uploaded_table(
            "installation_aoopo_detail", "2.1. Вина АООПО — детализация", detail_columns
        )

    checks_table = {
        "id": "rpo_checks",
        "title": "3. Мониторинг корректности процедур РПО",
        "columns": ["Период", "Кол-во проверок", "Кол-во замечаний"],
        "rows": build_checks_table(df_grh, df_perron, start, end, granularity),
    }

    return [alcohol_table, alcohol_detail_table, installation_table, installation_detail_table, checks_table]

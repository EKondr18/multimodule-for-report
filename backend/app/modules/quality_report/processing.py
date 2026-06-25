"""Обработка модуля «Отчёт по качеству» — единый набор таблиц без разделения
на разделы Нарушения/Проверки/Мониторинг.

На вход — до четырёх независимо загружаемых excel-файлов: «Нарушения на
перроне», «Нарушения в АВК» (лист «ТАБЛИЦА» в каждом, с разным регистром
колонки даты — «Дата»/«дата» — и разным набором остальных колонок),
«Проверки GRH» (листы «РПО» и «ФО и СИЗ» — по одному на каждую из таблиц
3 и 4) и «Мониторинг LIR/СЗВ» (лист «LIR СЗВ 2026», колонки «Дата», «ФИО
Агента», «Описание причины замечания» — для таблиц 6, 6.1, 6.2). Каждая таблица строится из
того, что загружено; если для неё не хватает нужного файла/листа — вместо
данных выводится отметка `NOT_UPLOADED` ("Файл не загружен"), на уровне
всей таблицы (1, 1.1, 2, 2.1, 5, 6, 6.1, 6.2) либо на уровне отдельных
ячеек, если в одной таблице разные колонки зависят от разных файлов (3, 4).

Для таблицы 1 нужны дата и категория нарушения; для детализирующих таблиц
(1.1 и 2.1) — также описание, исполнитель и подразделение; для таблицы 2
(только файл «Перрон») — дополнительно подкатегория и причина; для таблиц
3 и 4 — подкатегория и заключение (файл «Перрон») плюс дата из
соответствующего листа файла GRH; для таблицы 5 (только файл «Перрон») —
описание, место, бортовой номер, исполнитель и подразделение; для таблиц
6, 6.1, 6.2 (только файл «Мониторинг LIR/СЗВ») — дата, ФИО агента и
описание причины замечания (строка считается замечанием, если в этой
колонке не написано «без замечаний»). Строки в детализирующих и списочных
таблицах (1.1, 2.1, 5) сортируются по дате от старых к новым.

ФИО агентов в файле LIR/СЗВ могут заноситься с разным количеством пробелов,
регистром или опечатками — перед подсчётом по сотруднику такие варианты
схлопываются в одно каноническое имя (см. `_canonicalize_agent_names`):
сначала группировка по «очищенному» от лишних пробелов и регистра
варианту, затем — слияние похожих вариантов (опечатки) по строковому
сходству (`difflib`).

Данные за выбранный период агрегируются по срезам (неделя/месяц/квартал/
год) календарными границами, с обрезкой первого и последнего интервала по
границам периода — например, период 08.06.2026-21.06.2026 со срезом
«неделя» даёт два интервала: 08.06-14.06 и 15.06-21.06. Таблица 6.1 считает
нарушения по сотрудникам в пределах выбранного периода (без разбивки по
срезу); таблица 6.2 — топ-10 сотрудников по нарушениям за всю историю
загруженного файла, независимо от выбранного периода.
"""

import difflib
from io import BytesIO

import pandas as pd

VIOLATIONS_SHEET = "ТАБЛИЦА"
RPO_CHECKS_SHEET = "РПО"
FO_SIZ_CHECKS_SHEET = "ФО и СИЗ"
LIR_SZV_SHEET = "LIR СЗВ 2026"

GRANULARITIES = {"week", "month", "quarter", "year"}

ALCOHOL_CATEGORY = "Алкогольное и наркотическое опъянение"

INSTALLATION_CATEGORY = "Встреча ВС на МС"
INSTALLATION_SUBCATEGORY = "Установка ВС на допустимые точки"

REASON_KVS_BRAKING = "Несвоевременное торможение КВС"
REASON_OUT_OF_VIEW = "Невозможно оценить (вне ракурса СОК)"
REASON_AOOPO = "Вина АООПО"

RPO_SUBCATEGORY = "Руководство подъездом /отъездом;"

FO_SUBCATEGORIES = {
    "Нарушение ФО",
    "Нарушение элементов корпоративного стиля",
    "Соблюдение СИЗ",
}

WITH_FAULT_CONCLUSION = "с виной"

SAFETY_CATEGORY = "Техника безопасности, охраны труда"

NO_VIOLATIONS_TEXT = "без замечаний"
AGENT_NAME_SIMILARITY_THRESHOLD = 0.9

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
    place_col = _find_column(columns, "место")
    tail_number_col = _find_column(columns, "б/н")

    rename = {date_col: "date", category_col: "category"}
    keep = [date_col, category_col]
    for col, key in (
        (subcategory_col, "subcategory"),
        (reason_col, "reason"),
        (description_col, "description"),
        (executor_col, "executor"),
        (department_col, "department"),
        (conclusion_col, "conclusion"),
        (place_col, "place"),
        (tail_number_col, "tail_number"),
    ):
        if col is not None:
            rename[col] = key
            keep.append(col)

    result = df[keep].rename(columns=rename)
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    result = result.dropna(subset=["date"])
    result["category"] = result["category"].astype(str).str.strip()
    for key in (
        "subcategory",
        "reason",
        "description",
        "executor",
        "department",
        "conclusion",
        "place",
        "tail_number",
    ):
        if key not in result.columns:
            result[key] = None
        else:
            stripped = result[key].apply(lambda v: str(v).strip() if pd.notna(v) else None)
            result[key] = stripped.where(stripped != "", None)
    return result


def read_grh_checks_sheet(file_obj: BytesIO, sheet_name: str) -> pd.DataFrame | None:
    xl = pd.ExcelFile(file_obj)
    if sheet_name not in xl.sheet_names:
        return None

    df = xl.parse(sheet_name)
    columns = list(df.columns)
    date_col = _find_column(columns, "дата")
    if date_col is None:
        raise ValueError(f"На листе «{sheet_name}» файла GRH нет колонки «Дата»")

    result = df[[date_col]].rename(columns={date_col: "date"})
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    return result.dropna(subset=["date"])


def _find_column_contains(columns: list[str], substr: str) -> str | None:
    substr = substr.strip().lower()
    for col in columns:
        if substr in str(col).strip().lower():
            return col
    return None


def _clean_agent_name(raw) -> str | None:
    if not isinstance(raw, str):
        return None
    cleaned = " ".join(raw.split())
    return cleaned or None


def _canonicalize_agent_names(names: pd.Series) -> dict[str, str]:
    """Map each distinct cleaned name to a canonical display name, merging
    variants that differ only by case or by a small number of typos."""
    counts = names.value_counts()
    fold_groups: dict[str, list[str]] = {}
    for name in counts.index:
        fold_groups.setdefault(name.casefold(), []).append(name)

    fold_keys = list(fold_groups.keys())
    clusters: list[list[str]] = []
    for key in fold_keys:
        match = next(
            (
                cluster
                for cluster in clusters
                if any(
                    difflib.SequenceMatcher(None, key, existing).ratio() >= AGENT_NAME_SIMILARITY_THRESHOLD
                    for existing in cluster
                )
            ),
            None,
        )
        if match is None:
            clusters.append([key])
        else:
            match.append(key)

    mapping: dict[str, str] = {}
    for cluster in clusters:
        candidates = [name for fold_key in cluster for name in fold_groups[fold_key]]
        canonical = max(candidates, key=lambda n: counts[n])
        for fold_key in cluster:
            for name in fold_groups[fold_key]:
                mapping[name] = canonical
    return mapping


def read_lir_szv_file(file_obj: BytesIO) -> pd.DataFrame:
    xl = pd.ExcelFile(file_obj)
    if LIR_SZV_SHEET not in xl.sheet_names:
        raise ValueError(f"В файле «Мониторинг LIR/СЗВ» нет листа «{LIR_SZV_SHEET}»")
    df = xl.parse(LIR_SZV_SHEET)
    columns = list(df.columns)

    date_col = _find_column(columns, "дата") or _find_column_contains(columns, "дата")
    agent_col = _find_column_contains(columns, "фио")
    reason_col = _find_column_contains(columns, "причин")
    if date_col is None or agent_col is None or reason_col is None:
        raise ValueError(
            "В файле «Мониторинг LIR/СЗВ» нет колонок «Дата», «ФИО Агента» "
            "и/или «Описание причины замечания»"
        )

    result = df[[date_col, agent_col, reason_col]].rename(
        columns={date_col: "date", agent_col: "agent_raw", reason_col: "reason_description"}
    )
    result["date"] = pd.to_datetime(result["date"], errors="coerce", dayfirst=True)
    result = result.dropna(subset=["date"])

    result["agent_raw"] = result["agent_raw"].apply(_clean_agent_name)
    result = result.dropna(subset=["agent_raw"])

    canonical_map = _canonicalize_agent_names(result["agent_raw"])
    result["agent"] = result["agent_raw"].map(canonical_map)

    result["reason_description"] = result["reason_description"].apply(
        lambda v: str(v).strip() if pd.notna(v) else ""
    )
    result["has_violation"] = result["reason_description"].str.casefold() != NO_VIOLATIONS_TEXT.casefold()
    return result.drop(columns=["agent_raw"])


def build_lir_szv_table(
    df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, granularity: str
) -> list[dict]:
    in_period = df[(df["date"] >= start) & (df["date"] <= end)]
    buckets = generate_buckets(start, end, granularity)

    rows = []
    for bucket_start, bucket_end in buckets:
        bucket_data = in_period[(in_period["date"] >= bucket_start) & (in_period["date"] <= bucket_end)]
        rows.append(
            {
                "Период": _format_period(bucket_start, bucket_end, granularity),
                "Кол-во проверок": int(len(bucket_data)),
                "Кол-во замечаний": int(bucket_data["has_violation"].sum()),
            }
        )
    return rows


def build_lir_szv_employee_detail(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> list[dict]:
    in_period = df[(df["date"] >= start) & (df["date"] <= end) & df["has_violation"]]
    counts = in_period.groupby("agent").size().sort_values(ascending=False)
    return [{"ФИО Агента": agent, "Кол-во нарушений": int(count)} for agent, count in counts.items()]


def build_lir_szv_top_employees(df: pd.DataFrame, top_n: int = 10) -> list[dict]:
    violations = df[df["has_violation"]]
    counts = violations.groupby("agent").size().sort_values(ascending=False).head(top_n)
    return [{"ФИО Агента": agent, "Кол-во нарушений": int(count)} for agent, count in counts.items()]


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


def _rpo_complaints_filter(df_perron: pd.DataFrame) -> pd.DataFrame:
    return df_perron[
        (df_perron["subcategory"] == RPO_SUBCATEGORY) & (df_perron["conclusion"] == WITH_FAULT_CONCLUSION)
    ]


def _fo_siz_complaints_filter(df_perron: pd.DataFrame) -> pd.DataFrame:
    return df_perron[
        (df_perron["subcategory"].isin(FO_SUBCATEGORIES))
        & (df_perron["conclusion"] == WITH_FAULT_CONCLUSION)
    ]


def build_monitoring_table(
    df_checks: pd.DataFrame | None,
    df_perron: pd.DataFrame | None,
    complaints_filter,
    start: pd.Timestamp,
    end: pd.Timestamp,
    granularity: str,
) -> list[dict]:
    buckets = generate_buckets(start, end, granularity)

    complaints = complaints_filter(df_perron) if df_perron is not None else None

    rows = []
    for bucket_start, bucket_end in buckets:
        row = {"Период": _format_period(bucket_start, bucket_end, granularity)}
        if df_checks is None:
            row["Кол-во проверок"] = NOT_UPLOADED
        else:
            in_bucket = df_checks[(df_checks["date"] >= bucket_start) & (df_checks["date"] <= bucket_end)]
            row["Кол-во проверок"] = int(len(in_bucket))
        if complaints is None:
            row["Кол-во замечаний"] = NOT_UPLOADED
        else:
            in_bucket = complaints[(complaints["date"] >= bucket_start) & (complaints["date"] <= bucket_end)]
            row["Кол-во замечаний"] = int(len(in_bucket))
        rows.append(row)
    return rows


def _format_place(place, tail_number) -> str:
    place_text = _str_or_blank(place)
    tail_text = _str_or_blank(tail_number)
    if place_text.endswith(".0") and place_text[:-2].isdigit():
        place_text = place_text[:-2]
    if place_text.isdigit():
        place_text = f"МС{place_text}"
    return " ".join(part for part in (place_text, tail_text) if part)


def build_safety_violations_table(
    df_perron: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> list[dict]:
    in_period = df_perron[
        (df_perron["date"] >= start) & (df_perron["date"] <= end) & (df_perron["category"] == SAFETY_CATEGORY)
    ]
    return [
        {
            "Дата": row["date"].strftime("%d.%m.%Y"),
            "Категория": row["category"],
            "Описание": _str_or_blank(row["description"]),
            "Место": _format_place(row["place"], row["tail_number"]),
            "Исполнитель": _str_or_blank(row["executor"]),
            "Подразделение": _str_or_blank(row["department"]),
        }
        for _, row in in_period.sort_values("date").iterrows()
    ]


def _not_uploaded_table(table_id: str, title: str, columns: list[str]) -> dict:
    return {"id": table_id, "title": title, "columns": columns, "message": NOT_UPLOADED, "rows": []}


def build_quality_tables(
    df_perron: pd.DataFrame | None,
    df_avk: pd.DataFrame | None,
    df_grh_rpo: pd.DataFrame | None,
    df_grh_fo_siz: pd.DataFrame | None,
    df_lir: pd.DataFrame | None,
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

    monitoring_columns = ["Период", "Кол-во проверок", "Кол-во замечаний"]

    rpo_table = {
        "id": "rpo_checks",
        "title": "3. Мониторинг корректности процедур РПО",
        "columns": monitoring_columns,
        "rows": build_monitoring_table(df_grh_rpo, df_perron, _rpo_complaints_filter, start, end, granularity),
    }

    fo_siz_table = {
        "id": "fo_siz_checks",
        "title": "4. Мониторинг ношения ФО и СИЗ",
        "columns": monitoring_columns,
        "rows": build_monitoring_table(df_grh_fo_siz, df_perron, _fo_siz_complaints_filter, start, end, granularity),
    }

    safety_columns = ["Дата", "Категория", "Описание", "Место", "Исполнитель", "Подразделение"]
    if df_perron is not None:
        safety_table = {
            "id": "safety_violations",
            "title": "5. Нарушения техники безопасности и охраны труда",
            "columns": safety_columns,
            "rows": build_safety_violations_table(df_perron, start, end),
        }
    else:
        safety_table = _not_uploaded_table(
            "safety_violations", "5. Нарушения техники безопасности и охраны труда", safety_columns
        )

    lir_columns = ["Период", "Кол-во проверок", "Кол-во замечаний"]
    employee_columns = ["ФИО Агента", "Кол-во нарушений"]
    if df_lir is not None:
        lir_table = {
            "id": "lir_szv",
            "title": "6. Мониторинг LIR/СЗВ",
            "columns": lir_columns,
            "rows": build_lir_szv_table(df_lir, start, end, granularity),
        }
        lir_employee_detail_table = {
            "id": "lir_szv_employee_detail",
            "title": "6.1. Нарушения по сотрудникам за период",
            "columns": employee_columns,
            "rows": build_lir_szv_employee_detail(df_lir, start, end),
        }
        lir_top_employees_table = {
            "id": "lir_szv_top_employees",
            "title": "6.2. Топ-10 сотрудников по нарушениям за всю историю",
            "columns": employee_columns,
            "rows": build_lir_szv_top_employees(df_lir),
        }
    else:
        lir_table = _not_uploaded_table("lir_szv", "6. Мониторинг LIR/СЗВ", lir_columns)
        lir_employee_detail_table = _not_uploaded_table(
            "lir_szv_employee_detail", "6.1. Нарушения по сотрудникам за период", employee_columns
        )
        lir_top_employees_table = _not_uploaded_table(
            "lir_szv_top_employees", "6.2. Топ-10 сотрудников по нарушениям за всю историю", employee_columns
        )

    return [
        alcohol_table,
        alcohol_detail_table,
        installation_table,
        installation_detail_table,
        rpo_table,
        fo_siz_table,
        safety_table,
        lir_table,
        lir_employee_detail_table,
        lir_top_employees_table,
    ]

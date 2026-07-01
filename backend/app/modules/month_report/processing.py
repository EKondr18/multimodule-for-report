"""
Обработка данных для вкладки «Месяц» отчёта по качеству.

Источники данных
----------------
* «Производственные показатели» (лист «Производственный отчет») — таблица 1.
* «Нарушения на перроне» (лист «ТАБЛИЦА») — с удалением дублей по
  (Дата, Описание, Авиакомпания, Место) перед обработкой.
* «Нарушения в АВК» (лист «ТАБЛИЦА»).
* «Обращения» (лист «Экспорт») — столбец «Результат».

Таблица 1 — «Производственные показатели»
    Одна строка: Рейсы, Пассажиры, Багаж, Груз, Почта.
    Рейсы и Пассажиры — из колонки «Всего (AODB)»; остальные — из «Всего».

Таблица 2 — «Кол-во нарушений и обращений»
    Строки по месяцам в выбранном периоде.
    Нарушения = строки Перрон + АВК где Заключение = «с виной».
    Обращения = строки Обращений где Результат = «Подтверждено».
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import BinaryIO

import pandas as pd

VIOLATIONS_SHEET = "ТАБЛИЦА"
APPEALS_SHEET = "Экспорт"
PRODUCTION_SHEET = "Производственный отчет"

WITH_FAULT_CONCLUSION = "с виной"
CONFIRMED_RESULT = "Подтверждено"
NOT_UPLOADED = "Файл не загружен"

EXCLUDED_APPEAL_TYPES = {"Информационное письмо", "Благодарность", "Исходящее"}

PRODUCTION_ROWS = ["Рейсы", "Пассажиры", "Багаж", "Груз", "Почта"]
# Рейсы и Пассажиры → «Всего (AODB)»; остальные → «Всего»
_AODB_ROWS = {"Рейсы", "Пассажиры"}

_RU_MONTHS = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
}


def _find_col(columns: list, keyword: str) -> str | None:
    kw = keyword.lower()
    for c in columns:
        if isinstance(c, str) and kw in c.strip().lower():
            return c
    return None


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------

def read_violations_simple(file_obj: BinaryIO, deduplicate: bool = False) -> pd.DataFrame:
    """
    Read a violations file (ТАБЛИЦА sheet) and return a DataFrame with
    columns [date, conclusion].

    If deduplicate=True, drop rows where (Дата, Описание, Авиакомпания, Место)
    are all identical before any further processing.
    """
    raw = pd.read_excel(file_obj, sheet_name=VIOLATIONS_SHEET)
    cols = list(raw.columns)

    date_c = _find_col(cols, "дата")
    conclusion_c = _find_col(cols, "заключен")

    if date_c is None or conclusion_c is None:
        raise ValueError(
            "В файле нарушений не найдены столбцы «Дата» и/или «Заключение»"
        )

    if deduplicate:
        desc_c = _find_col(cols, "описан")
        airline_c = _find_col(cols, "авиакомпани")
        place_c = _find_col(cols, "мест")
        dedup_cols = [c for c in [date_c, desc_c, airline_c, place_c] if c is not None]
        if dedup_cols:
            raw = raw.drop_duplicates(subset=dedup_cols, keep="first")

    result = raw[[date_c, conclusion_c]].rename(
        columns={date_c: "date", conclusion_c: "conclusion"}
    )
    result["date"] = pd.to_datetime(result["date"], errors="coerce", dayfirst=True)
    result = result.dropna(subset=["date"]).reset_index(drop=True)
    result["conclusion"] = result["conclusion"].astype(str).str.strip()
    return result


def read_perron_full(file_obj: BinaryIO) -> pd.DataFrame:
    """
    Read perron violations file (ТАБЛИЦА sheet) and return DataFrame with
    columns [date, conclusion, department]. Deduplication on
    (Дата, Описание, Авиакомпания, Место) is always applied.
    """
    raw = pd.read_excel(file_obj, sheet_name=VIOLATIONS_SHEET)
    cols = list(raw.columns)

    date_c = _find_col(cols, "дата")
    conclusion_c = _find_col(cols, "заключен")
    dept_c = _find_col(cols, "подразделен")
    cat_c = _find_col(cols, "категори")
    subcat_c = _find_col(cols, "подкатегори") or _find_col(cols, "типов")
    exec_c = _find_col(cols, "исполнител")

    if date_c is None or conclusion_c is None:
        raise ValueError(
            "В файле нарушений на перроне не найдены столбцы «Дата» и/или «Заключение»"
        )

    # Deduplication
    desc_c = _find_col(cols, "описан")
    airline_c = _find_col(cols, "авиакомпани")
    place_c = _find_col(cols, "мест")
    dedup_cols = [c for c in [date_c, desc_c, airline_c, place_c] if c is not None]
    if dedup_cols:
        raw = raw.drop_duplicates(subset=dedup_cols, keep="first")

    keep = [date_c, conclusion_c]
    rename = {date_c: "date", conclusion_c: "conclusion"}
    if dept_c is not None:
        keep.append(dept_c)
        rename[dept_c] = "department"
    if cat_c is not None:
        keep.append(cat_c)
        rename[cat_c] = "category"
    if subcat_c is not None:
        keep.append(subcat_c)
        rename[subcat_c] = "subcategory"
    if exec_c is not None:
        keep.append(exec_c)
        rename[exec_c] = "executor"

    result = raw[keep].rename(columns=rename)
    result["date"] = pd.to_datetime(result["date"], errors="coerce", dayfirst=True)
    result = result.dropna(subset=["date"]).reset_index(drop=True)
    result["conclusion"] = result["conclusion"].astype(str).str.strip()
    for col in ("department", "category", "subcategory", "executor"):
        if col in result.columns:
            result[col] = result[col].astype(str).str.strip()
        else:
            result[col] = ""
    return result


def read_avk_full(file_obj: BinaryIO) -> pd.DataFrame:
    """
    Read AVK violations file and return DataFrame with
    columns [date, conclusion, department, category].
    Used by tables 2, 3 and 4.
    """
    raw = pd.read_excel(file_obj, sheet_name=VIOLATIONS_SHEET)
    cols = list(raw.columns)

    date_c = _find_col(cols, "дата")
    conclusion_c = _find_col(cols, "заключен")
    dept_c = _find_col(cols, "подразделен")
    cat_c = _find_col(cols, "категори")

    if date_c is None or conclusion_c is None:
        raise ValueError(
            "В файле «Нарушения в АВК» не найдены столбцы «Дата» и/или «Заключение»"
        )

    keep = [date_c, conclusion_c]
    rename = {date_c: "date", conclusion_c: "conclusion"}
    if dept_c is not None:
        keep.append(dept_c)
        rename[dept_c] = "department"
    subcat_c = _find_col(cols, "подкатегори")
    exec_c = _find_col(cols, "исполнител")

    if cat_c is not None:
        keep.append(cat_c)
        rename[cat_c] = "category"
    if subcat_c is not None:
        keep.append(subcat_c)
        rename[subcat_c] = "subcategory"
    if exec_c is not None:
        keep.append(exec_c)
        rename[exec_c] = "executor"

    result = raw[keep].rename(columns=rename)
    result["date"] = pd.to_datetime(result["date"], errors="coerce", dayfirst=True)
    result = result.dropna(subset=["date"]).reset_index(drop=True)
    result["conclusion"] = result["conclusion"].astype(str).str.strip()
    if "department" in result.columns:
        result["department"] = result["department"].astype(str).str.strip()
    else:
        result["department"] = ""
    if "category" in result.columns:
        result["category"] = result["category"].astype(str).str.strip()
    else:
        result["category"] = ""
    if "subcategory" in result.columns:
        result["subcategory"] = result["subcategory"].astype(str).str.strip()
    else:
        result["subcategory"] = ""
    if "executor" in result.columns:
        result["executor"] = result["executor"].astype(str).str.strip()
    else:
        result["executor"] = ""
    return result


def read_appeals_file(file_obj: BinaryIO) -> pd.DataFrame:
    """
    Read appeals file (Обращения) and return DataFrame with
    [date, result, appeal_type, responsible_services].
    responsible_services is a frozenset of stripped service names per row.
    """
    df = pd.read_excel(file_obj, sheet_name=APPEALS_SHEET)
    cols = list(df.columns)

    date_c = _find_col(cols, "дата обращени")
    result_c = _find_col(cols, "результат")
    type_c = _find_col(cols, "тип обращени")
    resp_c = _find_col(cols, "ответственные службы")

    if date_c is None or result_c is None:
        raise ValueError(
            "В файле «Обращения» не найдены столбцы «Дата обращения» и/или «Результат»"
        )

    keep = [date_c, result_c]
    rename = {date_c: "date", result_c: "result"}
    if type_c is not None:
        keep.append(type_c)
        rename[type_c] = "appeal_type"
    if resp_c is not None:
        keep.append(resp_c)
        rename[resp_c] = "responsible_services_raw"

    out = df[keep].rename(columns=rename)
    out["date"] = pd.to_datetime(out["date"], errors="coerce", dayfirst=True)
    out = out.dropna(subset=["date"]).reset_index(drop=True)
    out["result"] = out["result"].astype(str).str.strip()

    if "appeal_type" in out.columns:
        out["appeal_type"] = out["appeal_type"].astype(str).str.strip()
    else:
        out["appeal_type"] = ""

    def _parse_services(val: object) -> frozenset:
        if not isinstance(val, str) or not val.strip():
            return frozenset()
        return frozenset(s.strip() for s in val.split(",") if s.strip())

    if "responsible_services_raw" in out.columns:
        out["responsible_services"] = out["responsible_services_raw"].apply(_parse_services)
        out = out.drop(columns=["responsible_services_raw"])
    else:
        out["responsible_services"] = frozenset()

    return out


def read_production_file(file_obj: BinaryIO) -> dict[str, int | None]:
    """
    Parse production indicators file and return
    {metric_name: value} for each of PRODUCTION_ROWS.
    """
    df = pd.read_excel(file_obj, sheet_name=PRODUCTION_SHEET, header=None)

    # Find the header row containing "Всего (AODB)"
    header_idx = None
    for i, row in df.iterrows():
        if any(
            isinstance(v, str) and "всего (aodb)" in v.lower()
            for v in row
        ):
            header_idx = i
            break

    if header_idx is None:
        raise ValueError(
            "В файле «Производственные показатели» не найдена строка заголовков"
        )

    headers = df.iloc[header_idx].tolist()

    vsego_aodb_col = None
    vsego_col = None
    for j, h in enumerate(headers):
        if not isinstance(h, str):
            continue
        h_clean = h.strip()
        if h_clean == "Всего (AODB)" and vsego_aodb_col is None:
            vsego_aodb_col = j
        elif h_clean == "Всего" and vsego_col is None:
            vsego_col = j

    if vsego_aodb_col is None or vsego_col is None:
        raise ValueError(
            "В файле «Производственные показатели» не найдены столбцы «Всего (AODB)» и/или «Всего»"
        )

    data: dict[str, int | None] = {}
    for i in range(int(header_idx) + 1, len(df)):
        row_name = df.iloc[i, 0]
        if not isinstance(row_name, str):
            continue
        row_name = row_name.strip()
        if row_name in PRODUCTION_ROWS:
            target_col = vsego_aodb_col if row_name in _AODB_ROWS else vsego_col
            val = df.iloc[i, target_col]
            data[row_name] = int(val) if pd.notna(val) else None

    return data


# ---------------------------------------------------------------------------
# Period helpers
# ---------------------------------------------------------------------------

_RU_QUARTERS = {1: "I", 2: "II", 3: "III", 4: "IV"}


def _month_label(ts: pd.Timestamp) -> str:
    return f"{_RU_MONTHS[ts.month]} {ts.year}"


def _quarter_label(ts: pd.Timestamp) -> str:
    q = (ts.month - 1) // 3 + 1
    return f"{_RU_QUARTERS[q]} кв. {ts.year}"


def _year_label(ts: pd.Timestamp) -> str:
    return str(ts.year)


def _month_buckets(start: pd.Timestamp, end: pd.Timestamp) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    buckets = []
    current = start.replace(day=1)
    while current <= end:
        next_month = (current + pd.DateOffset(months=1)).replace(day=1)
        bucket_end = min(next_month - pd.Timedelta(days=1), end)
        buckets.append((current, bucket_end))
        current = next_month
    return buckets


def _quarter_buckets(start: pd.Timestamp, end: pd.Timestamp) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    buckets = []
    # align to quarter start
    m = start.month
    q_start_month = ((m - 1) // 3) * 3 + 1
    current = start.replace(month=q_start_month, day=1)
    while current <= end:
        q_end_month = q_start_month + 2
        next_q = (current + pd.DateOffset(months=3)).replace(day=1)
        bucket_end = min(next_q - pd.Timedelta(days=1), end)
        buckets.append((current, bucket_end))
        current = next_q
        q_start_month = current.month
    return buckets


def _year_buckets(start: pd.Timestamp, end: pd.Timestamp) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    buckets = []
    current = start.replace(month=1, day=1)
    while current <= end:
        next_year = current.replace(year=current.year + 1)
        bucket_end = min(next_year - pd.Timedelta(days=1), end)
        buckets.append((current, bucket_end))
        current = next_year
    return buckets


def _period_buckets(
    start: pd.Timestamp, end: pd.Timestamp, granularity: str
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    if granularity == "quarter":
        return _quarter_buckets(start, end)
    if granularity == "year":
        return _year_buckets(start, end)
    return _month_buckets(start, end)


def _period_label(ts: pd.Timestamp, granularity: str) -> str:
    if granularity == "quarter":
        return _quarter_label(ts)
    if granularity == "year":
        return _year_label(ts)
    return _month_label(ts)


# ---------------------------------------------------------------------------
# Table builders
# ---------------------------------------------------------------------------

def build_production_table(data: dict[str, int | None]) -> list[dict]:
    row = {metric: (data.get(metric) if data.get(metric) is not None else NOT_UPLOADED)
           for metric in PRODUCTION_ROWS}
    return [row]


COL_COMBINED = "Нарушения+Обращения (подтвержденные)"
COL_APPEALS_NO_THANKS = "Обращения (без благодарностей)"


def build_violations_appeals_table(
    df_perron: pd.DataFrame | None,
    df_avk: pd.DataFrame | None,
    df_appeals: pd.DataFrame | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
    granularity: str = "month",
) -> list[dict]:
    no_violations_data = df_perron is None and df_avk is None
    buckets = _period_buckets(start, end, granularity)

    rows = []
    for bucket_start, bucket_end in buckets:
        label = _period_label(bucket_start, granularity)

        # Count с виной from perron + avk
        violations_count = 0
        if not no_violations_data:
            for df in [df_perron, df_avk]:
                if df is None:
                    continue
                in_period = df[
                    (df["date"] >= bucket_start) & (df["date"] <= bucket_end)
                ]
                violations_count += int((in_period["conclusion"] == WITH_FAULT_CONCLUSION).sum())

        # Count confirmed appeals (Результат = Подтверждено)
        confirmed_count = 0
        appeals_no_thanks: int | str = NOT_UPLOADED
        if df_appeals is not None:
            in_period_a = df_appeals[
                (df_appeals["date"] >= bucket_start) & (df_appeals["date"] <= bucket_end)
            ]
            confirmed_count = int((in_period_a["result"] == CONFIRMED_RESULT).sum())
            # Обращения без исключённых типов
            appeals_no_thanks = int(
                (~in_period_a["appeal_type"].isin(EXCLUDED_APPEAL_TYPES)).sum()
            )

        # Combined column: NOT_UPLOADED only if BOTH sources are missing
        if no_violations_data and df_appeals is None:
            combined: int | str = NOT_UPLOADED
        else:
            combined = violations_count + confirmed_count

        rows.append({
            "Период": label,
            COL_COMBINED: combined,
            COL_APPEALS_NO_THANKS: appeals_no_thanks,
        })

    return rows


def build_avk_departments_table(
    df_avk: pd.DataFrame | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[dict]:
    """
    Table 3: per-department count of AVK violations where Заключение = «с виной».
    Departments from AVK's 'department' column, ordered descending by count.
    Bottom row: ИТОГО.
    """
    if df_avk is None:
        return []

    in_avk = df_avk[
        (df_avk["date"] >= start)
        & (df_avk["date"] <= end)
        & (df_avk["conclusion"] == WITH_FAULT_CONCLUSION)
    ]

    dept_counts = (
        in_avk["department"]
        .replace("nan", pd.NA)
        .dropna()
        .value_counts()
    )

    rows = []
    total = 0
    for dept, count in dept_counts.items():
        c = int(count)
        total += c
        rows.append({"Служба": dept, "Кол-во нарушений": c})

    rows.append({"Служба": "ИТОГО", "Кол-во нарушений": total})
    return rows


def _norm_cat(s: str) -> str:
    """Normalize category name: lowercase, collapse spaces, unify separators (/ , _)."""
    import re
    s = s.strip().lower()
    s = re.sub(r"[/,_]+", " ", s)  # /, , and _ → space
    s = re.sub(r"\s+", " ", s)
    return s


def _clean_display(s: str) -> str:
    """Clean category/subcategory name for display: remove underscores, normalize spaces."""
    import re
    s = re.sub(r"_+", " ", s.strip())
    return re.sub(r"\s+", " ", s).strip()


# Departments merged into ДСТ for table 10
_DST_ALIASES = {"ДСТ", "ССТ", "СПТ"}


def build_perron_departments_table(
    df_perron: pd.DataFrame | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[dict]:
    """
    Table 10: per-department count of perron violations where Заключение = «с виной».
    ССТ and СПТ are merged into ДСТ. Ordered descending; ИТОГО at bottom.
    """
    if df_perron is None:
        return []

    in_perron = df_perron[
        (df_perron["date"] >= start)
        & (df_perron["date"] <= end)
        & (df_perron["conclusion"] == WITH_FAULT_CONCLUSION)
    ].copy()

    # Merge ССТ and СПТ into ДСТ
    in_perron["department"] = in_perron["department"].apply(
        lambda d: "ДСТ" if d in _DST_ALIASES else d
    )

    dept_counts = (
        in_perron["department"]
        .replace("nan", pd.NA)
        .dropna()
        .value_counts()
    )

    rows = []
    total = 0
    for dept, count in dept_counts.items():
        c = int(count)
        total += c
        rows.append({"Служба": dept, "Кол-во нарушений": c})

    rows.append({"Служба": "ИТОГО", "Кол-во нарушений": total})
    return rows


# Category groups for Table 4 — order defines output row order.
# Each entry: (display_label, [file_category_values_that_map_to_it]).
# Matching is normalized (case-insensitive, / and , treated as space).
_CATEGORY_GROUPS: list[tuple[str, list[str]]] = [
    ("Регистрация", ["Регистрация"]),
    ("Оформление багажа", ["Оформление багажа"]),
    ("Нарушение ФО/этики", ["Нарушение ФО/этики", "Нарушение ФО,этики", "Нарушения ФО/этики", "Нарушения ФО,этики"]),
    ("Посадка", ["Посадка"]),
    ("Своевременность выполнения задач", [
        "Своевременность назначения и выполнения задач",
        "Взаимодействие между подразделениями",
    ]),
    ("Трудовая дисциплина и безопасность", [
        "Заполнение_документации",
        "Внутриобъектовый режим",
        "Алкогольное и наркотическое опъянение",
        "Обучение и квалификация персонала",
    ]),
    ("Использование оборудования", ["Использование оборудования"]),
    ("Прилет", ["Прилет"]),
]

# Pre-build normalized lookup: norm_value → group_index
_NORM_CAT_MAP: dict[str, int] = {}
for _gi, (_lbl, _vals) in enumerate(_CATEGORY_GROUPS):
    for _v in _vals:
        _NORM_CAT_MAP[_norm_cat(_v)] = _gi


def build_avk_categories_table(
    df_avk: pd.DataFrame | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[dict]:
    """
    Table 4: AVK violations (Заключение = «с виной») grouped by Категория.
    Rows follow _CATEGORY_GROUPS order; bottom row ИТОГО.
    Category matching is normalized (case-insensitive, / and , treated as space).
    """
    if df_avk is None:
        return []

    in_avk = df_avk[
        (df_avk["date"] >= start)
        & (df_avk["date"] <= end)
        & (df_avk["conclusion"] == WITH_FAULT_CONCLUSION)
    ]

    counts = [0] * len(_CATEGORY_GROUPS)
    for raw_cat in in_avk["category"]:
        gi = _NORM_CAT_MAP.get(_norm_cat(str(raw_cat)))
        if gi is not None:
            counts[gi] += 1

    rows = []
    total = 0
    for gi, (label, _) in enumerate(_CATEGORY_GROUPS):
        c = counts[gi]
        total += c
        rows.append({"Категория": label, "Кол-во нарушений": c})

    return rows


# ---------------------------------------------------------------------------
# Subcategory tables (5, 6, 7) — generic builder + per-table definitions
# ---------------------------------------------------------------------------

def _norm_subcat(s: str) -> str:
    """Normalize subcategory for matching: lowercase, strip, collapse spaces."""
    return " ".join(s.strip().lower().split())


# (table_id, title, category_norm_keys, groups)
# groups: list of (display_label, list_of_file_values | None)
# None → catch-all "Другое"

_SUBCAT_TABLE_5 = (
    "registration_subcat",
    "5. Регистрация",
    # category filter — normalized; covers "регистрация"
    {"регистрация"},
    [
        ("Оформление ручной клади",             ["Ручная кладь оформлена с нарушением"]),
        ("Информирование пассажиров",           ["Доведение необходимой информации"]),
        ("Другое",                              None),
        ("Выделение информации на ПТ",          ["Выделение информации на ПТ"]),
        ("Включение ИМ",                        ["Включение ИМ"]),
        ("Опрос о запрещенных предметах",       ["Не запрашивает запрещенные предметы в багаже/РК"]),
        ("Приглашение пассажиров на стойку",    ["Не приглашает пассажиров на стойку"]),
        ("Проверка данных перед выдачей ПТ",    ["Проверка данных перед выдачей ПТ"]),
        ("Предложение дополнительных услуг",    ["Предложение дополнительных услуг"]),
        ("Процедура регистрации",               ["Процедура регистрации"]),
        ("Дубликат посадочного талона",         ["Дубликат посадочного талона"]),
        ("Рассадка пассажиров на ВС",           ["Рассадка пассажиров на ВС"]),
        ("Блокировка ПК",                       ["Блокировка ПК"]),
        ("Установка табличек ОГ",               ["Информационная табличка ОГ"]),
        ("Ошибки при проверке паспортов/виз",   ["Проверка паспортных данных"]),
        ("Использование продукции АК",          ["Установка продукции компании, калибратора, ПТ, ББ"]),
        ("Обслуживание несопровождаемых детей", ["Несопровождаемый ребенок"]),
        ("Обслуживание ММП",                    ["Пассажиры из числа инвалидов"]),
    ],
)

_SUBCAT_TABLE_6 = (
    "baggage_subcat",
    "6. Оформление багажа",
    {"оформление багажа"},
    [
        ("Маркировка багажа",             ["Некорректная маркировка багажа при регистрации"]),
        ("Отправка багажа по ленте",      ["По ленте отправлено место багажа с нарушением"]),
        ("Фиксация повреждения багажа",   ["Фиксация повреждения багажа"]),
        ("Оплата за СНБ",                 ["Оплата за СНБ"]),
        ("Сдвоенный багаж",               ["Сдвоенный багаж"]),
        ("Опрос о принадлежности багажа", ["Опрос о принадлежности багажа"]),
        ("Другое",                        None),
    ],
)

_SUBCAT_TABLE_7 = (
    "fo_ethics_subcat",
    "7. Нарушение ФО/этики",
    # normalized form of "нарушение фо этики" covers all separators
    {"нарушение фо этики", "нарушения фо этики"},
    [
        ("Несоблюдение этики общения",              ["Несоблюдение этики общения"]),
        ("Использование личного МТ",                ["Использование личного МТ"]),
        ("Фразеология",                             ["Фразеология"]),
        ("Внешний вид",                             ["Внешний вид"]),
        ("Бейдж прикреплен не верно/отсутствует",  ["Бейдж прикреплен не верно/отсутствует",
                                                     "Бейдж прикреплен не верно/ отсутствует"]),
        ("Нарушение ФО",                            ["Нарушение ФО"]),
        ("Прием пищи в неположенном месте",         ["Прием пищи в неположенном месте"]),
        ("Другое",                                  None),
        ("Соблюдение чистоты и порядка",            ["Соблюдение чистоты и порядка"]),
    ],
)

_SUBCAT_TABLE_8 = (
    "boarding_subcat",
    "8. Посадка",
    {"посадка"},
    [
        ("Осмотр зоны выхода на посадку",          ["Не осмотрел аванперрон/галерею после КП"]),
        ("Верификация ПТ с паспортом",             ["Не производит верификацию ПТ с паспортными данными"]),
        ("Неотсканированный ПТ",                   ["Неотсканированный ПТ"]),
        ("Использование продукции АК",             ["Установка продукции компании, калибратора, ПТ, ББ"]),
        ("Блокировка ПК",                          ["Блокировка ПК"]),
        ("Закрытие дверей и отправка автобусов",   ["Закрытие дверей и отправка автобусов"]),
        ("Другое",                                 None),
        ("Включение ИМ",                           ["Включение ИМ"]),
        ("Контроль габаритов ручной клади",        ["Измерение ручной клади"]),
        ("Проверка неявки",                        ["Не производит проверку неявки"]),
        ("Обслуживание приоритетных пассажиров",   ["Обслуживание приоритетных категорий пассажиров"]),
        ("Невылет пассажира",                      ["Невылет пассажира"]),
        ("Отказ в перевозке",                      ["Отказ в перевозке"]),
        ("Расстановка тенсаторов",                 ["Расстановка тенсаторов"]),
        ("Засыл пассажира",                        ["Засыл пассажира"]),
        ("Обслуживание несопровождаемых детей",    ["Несопровождаемый ребенок"]),
    ],
)

_SUBCAT_TABLES = [_SUBCAT_TABLE_5, _SUBCAT_TABLE_6, _SUBCAT_TABLE_7, _SUBCAT_TABLE_8]


def build_avk_subcategory_table(
    df_avk: pd.DataFrame | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
    category_norm_keys: set[str],
    groups: list[tuple[str, list[str] | None]],
) -> list[dict]:
    """
    Generic subcategory breakdown for AVK violations (Заключение = «с виной»).
    category_norm_keys: set of normalized category values to match.
    groups: (display_label, file_subcat_values | None); None = catch-all.
    """
    if df_avk is None:
        return []

    mask = (
        (df_avk["date"] >= start)
        & (df_avk["date"] <= end)
        & (df_avk["conclusion"] == WITH_FAULT_CONCLUSION)
        & (df_avk["category"].apply(_norm_cat).isin(category_norm_keys))
    )
    in_avk = df_avk[mask]

    # Build normalized lookup: norm_subcat → group_index
    norm_map: dict[str, int] = {}
    catchall_idx: int | None = None
    for gi, (_, vals) in enumerate(groups):
        if vals is None:
            catchall_idx = gi
        else:
            for v in vals:
                norm_map[_norm_subcat(v)] = gi

    counts = [0] * len(groups)
    for raw_sub in in_avk["subcategory"]:
        gi = norm_map.get(_norm_subcat(str(raw_sub)))
        if gi is not None:
            counts[gi] += 1
        elif catchall_idx is not None:
            counts[catchall_idx] += 1

    rows: list[dict] = []
    total = 0
    for gi, (label, _) in enumerate(groups):
        c = counts[gi]
        total += c
        rows.append({"Подкатегория": label, "Кол-во нарушений": c})

    return rows


# ---------------------------------------------------------------------------
# Employee tables (9 and 9.1)
# ---------------------------------------------------------------------------

_COL_2M = "Кол-во нарушений (за 2 месяца назад)"
_COL_1M = "Кол-во нарушений (за 1 месяц назад)"
_COL_CUR = "Кол-во нарушений (За текущий месяц)"
_MIN_VIOLATIONS = 3


def _normalize_employee(name: str) -> str:
    return " ".join(str(name).strip().lower().split())


def _group_employees(counts: "pd.Series[int]", threshold: float = 0.85) -> dict[str, str]:
    """Union-find fuzzy grouping of employee names. Returns raw_name → canonical_name."""
    unique = list(counts.index)
    n = len(unique)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            if counts.iloc[ri] >= counts.iloc[rj]:
                parent[rj] = ri
            else:
                parent[ri] = rj

    for i in range(n):
        for j in range(i + 1, n):
            if SequenceMatcher(
                None,
                _normalize_employee(unique[i]),
                _normalize_employee(unique[j]),
            ).ratio() >= threshold:
                union(i, j)

    return {unique[i]: unique[find(i)] for i in range(n)}


def _fault_in_period(
    df: pd.DataFrame, s: pd.Timestamp, e: pd.Timestamp
) -> pd.DataFrame:
    return df[
        (df["date"] >= s)
        & (df["date"] <= e)
        & (df["conclusion"] == WITH_FAULT_CONCLUSION)
    ]


def _prev_month_range(ref: pd.Timestamp, months_back: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return (start, end) for the calendar month `months_back` before ref's month."""
    anchor = ref.replace(day=1)
    for _ in range(months_back):
        anchor = (anchor - pd.Timedelta(days=1)).replace(day=1)
    end = (anchor + pd.DateOffset(months=1)).replace(day=1) - pd.Timedelta(days=1)
    return anchor, end


def build_avk_employees_table(
    df_avk: pd.DataFrame | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[list[dict], list[str]]:
    """
    Table 9: employees with >= 3 'с виной' violations in current period,
    sorted desc, with counts for the two preceding calendar months.
    Returns (rows, columns).
    """
    columns = ["Сотрудник", _COL_2M, _COL_1M, _COL_CUR]
    if df_avk is None:
        return [], columns

    prev1_s, prev1_e = _prev_month_range(start, 1)
    prev2_s, prev2_e = _prev_month_range(start, 2)

    cur_df = _fault_in_period(df_avk, start, end)
    p1_df = _fault_in_period(df_avk, prev1_s, prev1_e)
    p2_df = _fault_in_period(df_avk, prev2_s, prev2_e)

    # Build name map from all names across all three periods
    all_names = (
        pd.concat([cur_df["executor"], p1_df["executor"], p2_df["executor"]])
        .replace("nan", pd.NA)
        .dropna()
    )
    if all_names.empty:
        return [], columns
    name_map = _group_employees(all_names.value_counts())

    def canonical_counts(df: pd.DataFrame) -> dict[str, int]:
        s = (
            df["executor"]
            .replace("nan", pd.NA)
            .dropna()
            .map(lambda n: name_map.get(n, n))
            .value_counts()
        )
        return s.to_dict()

    cur_cnt = canonical_counts(cur_df)
    p1_cnt = canonical_counts(p1_df)
    p2_cnt = canonical_counts(p2_df)

    eligible = sorted(
        [(name, c) for name, c in cur_cnt.items() if c >= _MIN_VIOLATIONS],
        key=lambda x: -x[1],
    )

    rows = [
        {
            "Сотрудник": name,
            _COL_2M: p2_cnt.get(name, 0),
            _COL_1M: p1_cnt.get(name, 0),
            _COL_CUR: cur_c,
        }
        for name, cur_c in eligible
    ]
    return rows, columns


def build_avk_repeat_employees_table(
    df_avk: pd.DataFrame | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[dict]:
    """
    Table 9.1: employees with >= 3 'с виной' violations in a single subcategory
    in the current period. Column 'Подразделение/Сотрудник' = dept + ' - ' + name.
    """
    if df_avk is None:
        return []

    cur = _fault_in_period(df_avk, start, end).copy()
    if cur.empty:
        return []

    valid_exec = cur["executor"].replace("nan", pd.NA).dropna()
    if not valid_exec.empty:
        name_map = _group_employees(valid_exec.value_counts())
        cur["executor"] = cur["executor"].map(lambda n: name_map.get(n, n) if n != "nan" else pd.NA)

    cur["dept_emp"] = cur["department"].fillna("") + " - " + cur["executor"].fillna("")

    grouped = (
        cur.groupby(["dept_emp", "subcategory"])
        .size()
        .reset_index(name="count")
    )
    grouped = grouped[grouped["count"] >= _MIN_VIOLATIONS].sort_values("count", ascending=False)

    return [
        {
            "Подразделение/Сотрудник": row["dept_emp"],
            "Подкатегория нарушения": row["subcategory"],
            "Кол-во нарушений": int(row["count"]),
        }
        for _, row in grouped.iterrows()
    ]


# ---------------------------------------------------------------------------
# Tables 11–13: per-category / per-subcategory perron breakdowns
# ---------------------------------------------------------------------------

# (display_label, list_of_file_values | None)
# None = catch-all «Другое».
# _norm_cat maps / and space identically, so slash display names match space file values.
_AVS_GROUPS: list[tuple[str, list[str] | None]] = [
    ("Подгон отгон спецтехники к/от ВС",        ["Подгон отгон спецтехники к от ВС"]),
    ("Контроль загрузки/выгрузки ВС",            ["Контроль загрузки выгрузки ВС"]),
    ("Внешний осмотр ВС",                        ["Внешний осмотр ВС"]),
    ("Встреча ВС на МС",                         ["Встреча ВС на МС"]),
    ("Заполнение документации",                  ["Заполнение документации"]),
    ("Установка УК и конусов",                   ["Установка УК и конусов"]),
    ("Подготовка перрона/спецтехники к НО ВС",   ["Подготовка перрона спецтехники к НО ВС"]),
    ("Использование оборудования",               ["Использование оборудования"]),
    ("Заправка/дозаправка/слив топлива",         ["Заправка дозаправка слив топлива"]),
    ("Обслуживание WTS и VS",                    ["Обслуживание WTS и VS"]),
    ("Заключительные работы по обслуживанию ВС", ["Заключительные работы по обслуживанию ВС"]),
    ("Открытие/закрытие дверей и люков",         ["Открытие закрытие дверей и люков"]),
    ("Центровка ВС",                             ["Центровка ВС"]),
    ("Другое",                                   None),
    ("Повреждение ВС",                           ["Повреждение ВС"]),
    ("Порча имущества",                          ["Порча имущества"]),
    ("Обслуживание ВС при неблагоприятных МУ",   ["Обслуживание ВС при неблагоприятных МУ"]),
    ("Несвоевременный вывоз СТ с МС",            ["Несвоевременный вывоз СТ с МС"]),
    ("ПОО",                                      ["ПОО"]),
    ("Обспечение стоянки ВС",                    ["Обспечение стоянки ВС", "Обеспечение стоянки ВС"]),
    ("Задержка рейса",                           ["Задержка рейса"]),
]

# Flat list of all non-catch-all file values (used by _PERRON_CAT_GROUPS)
_AVS_FILE_VALUES = [v for _, vals in _AVS_GROUPS if vals for v in vals]

_NVZ_CATEGORIES = [
    "Своевременность назначения и выполнения задач",
    "Взаимодействие между подразделениями",
]

_ETS_CATEGORIES = [
    "Несоблюдение ПДД",
    "Световое обозначение транспорта",
    "Обеспечение остановки и стоянки ТС",
    "ДТП",
    "Движение без регулировщика",
    "Осмотр ТС",
    "Чистота ТС",
    "Отказы и неисправности ТС",
]

# Table 14: parent categories (file values) to filter on
_TDB_PARENT_CATS_FILE = [
    "Техника безопасности охраны труда",
    "Техника безопасности, охраны труда",
    "Алкогольное и наркотическое опьянение",
    "Алкогольное и наркотическое опъянение",
    "Внутриобъектовый режим",
    "Нарушение ФО этики",
    "Нарушение ФО, этики",
    "Нарушение ФО/этики",
    "Нарушения ФО этики",
    "Нарушения ФО, этики",
    "Нарушения ФО/этики",
]

# Table 14: subcategory groups — order defines row order; None = catch-all «Другое»
_TDB_SUBCAT_GROUPS: list[tuple[str, list[str] | None]] = [
    ("Соблюдение СИЗ",                                       ["Соблюдение СИЗ"]),
    ("Алкогольное опьянение",                                ["Алкогольное опьянение", "Алкогольное опъянение"]),
    ("Отсутствие пропуска на видном месте",                  ["Отсутствие пропуска на видном месте"]),
    ("Другое",                                               None),
    ("Прохождение МО",                                       ["Прохождение МО"]),
    ("Нарушение ФО",                                         ["Нарушение ФО"]),
    ("Порча имущества компании",                             ["Порча имущества компании"]),
    ("Использование личного МТ",                             ["Использование личного МТ"]),
    ("Хождение по транспортерной ленте",                     ["Хождение по транспортерной ленте"]),
    ("Передвижение пешком по маршруту движения ТС/перрону",  [
        "Передвижение пешком по маршруту движения ТС/перрону",
        "Передвижение пешком по маршруту движения ТС перрону",
    ]),
    ("Выход на перрон без жилета",                           ["Выход на перрон без жилета"]),
    ("Выполнение работ без стремянки",                       ["Выполнение работ без стремянки"]),
    ("Использование средств подмащивания",                   ["Использование средств подмащивания"]),
    ("Выполнение работ в наушниках",                         ["Выполнение работ в наушниках"]),
    ("Несоблюдение этики общения",                           ["Несоблюдение этики общения"]),
    ("Наркотическое опьянение",                              ["Наркотическое опьянение", "Наркотическое опъянение"]),
]


def _filter_perron_cats(
    df: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    file_categories: list[str],
) -> pd.DataFrame:
    norm_set = {_norm_cat(c) for c in file_categories}
    return df[
        (df["date"] >= start)
        & (df["date"] <= end)
        & (df["conclusion"] == WITH_FAULT_CONCLUSION)
        & (df["category"].apply(_norm_cat).isin(norm_set))
    ].copy()


def _merge_dst(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["department"] = df["department"].apply(lambda d: "ДСТ" if d in _DST_ALIASES else d)
    return df


def _dept_breakdown(df: pd.DataFrame) -> dict[str, int]:
    df = _merge_dst(df)
    counts = df["department"].replace("nan", pd.NA).dropna().value_counts()
    return {d: int(c) for d, c in counts.items()}


def _format_dept_str(dept_counts: dict[str, int]) -> str:
    return ", ".join(f"{d} – {c}" for d, c in dept_counts.items())


def build_avs_table(
    df_perron: pd.DataFrame | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict:
    """Table 11b: Обслуживание ВС — each specific category, count only."""
    col_cat, col_cnt = "Категория", "Кол-во нарушений"
    columns = [col_cat, col_cnt]
    if df_perron is None:
        return {"columns": columns, "rows": [], "message": NOT_UPLOADED}

    sub = _filter_perron_cats(df_perron, start, end, _AVS_FILE_VALUES)

    # Build normalized lookup for non-catch-all groups
    norm_map: dict[str, int] = {}
    catchall_idx: int | None = None
    for gi, (_, vals) in enumerate(_AVS_GROUPS):
        if vals is None:
            catchall_idx = gi
        else:
            for v in vals:
                norm_map[_norm_cat(v)] = gi

    counts = [0] * len(_AVS_GROUPS)
    for raw_cat in sub["category"]:
        gi = norm_map.get(_norm_cat(str(raw_cat)))
        if gi is not None:
            counts[gi] += 1
        elif catchall_idx is not None:
            counts[catchall_idx] += 1

    total = 0
    rows = []
    for gi, (label, _) in enumerate(_AVS_GROUPS):
        c = counts[gi]
        total += c
        rows.append({col_cat: label, col_cnt: c})
    return {"columns": columns, "rows": rows}


def build_nvz_table(
    df_perron: pd.DataFrame | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict:
    """Table 12: Назначение и выполнение задач — categories + dept breakdown."""
    col_cat, col_cnt = "Категория", "Кол-во нарушений"
    col_dept, col_dc = "Служба", "Кол-во нарушений (служба)"
    columns = [col_cat, col_cnt, col_dept, col_dc]
    if df_perron is None:
        return {"columns": columns, "rows": [], "message": NOT_UPLOADED}

    sub = _filter_perron_cats(df_perron, start, end, _NVZ_CATEGORIES)
    row_groups = []
    grand_total = 0
    all_depts: dict[str, int] = {}

    for cat in _NVZ_CATEGORIES:
        mask = sub["category"].apply(_norm_cat) == _norm_cat(cat)
        grp = sub[mask]
        cnt = len(grp)
        grand_total += cnt
        depts = _dept_breakdown(grp)
        for d, c in depts.items():
            all_depts[d] = all_depts.get(d, 0) + c
        row_groups.append({
            col_cat: _clean_display(cat),
            col_cnt: cnt,
            "details": [{col_dept: d, col_dc: c} for d, c in depts.items()],
        })

    return {"columns": columns, "rows": [], "span_columns": 2, "row_groups": row_groups}


def build_ets_table(
    df_perron: pd.DataFrame | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict:
    """
    Table 13: Эксплуатация ТС — categories + dept breakdown +
    top-2 subcategories per category with their dept breakdown as text.
    """
    col_cat, col_cnt = "Категория", "Кол-во нарушений"
    col_dept, col_dc = "Служба", "Кол-во нарушений (служба)"
    col_sub, col_sdepts = "Типовые нарушения", "Кол-во по службам"
    columns = [col_cat, col_cnt, col_dept, col_dc, col_sub, col_sdepts]

    if df_perron is None:
        return {"columns": columns, "rows": [], "message": NOT_UPLOADED}

    sub = _filter_perron_cats(df_perron, start, end, _ETS_CATEGORIES)
    row_groups = []
    grand_total = 0
    all_depts: dict[str, int] = {}

    for cat in _ETS_CATEGORIES:
        mask = sub["category"].apply(_norm_cat) == _norm_cat(cat)
        grp = sub[mask].copy()
        cnt = len(grp)
        grand_total += cnt
        depts = _dept_breakdown(grp)
        for d, c in depts.items():
            all_depts[d] = all_depts.get(d, 0) + c

        # dept detail rows
        dept_rows = [{col_dept: d, col_dc: c, col_sub: "", col_sdepts: ""}
                     for d, c in depts.items()]

        # top-2 subcategory rows
        subcat_rows: list[dict] = []
        if "subcategory" in grp.columns:
            grp_merged = _merge_dst(grp)
            grp_merged["subcategory"] = grp_merged["subcategory"].apply(_clean_display)
            top2 = (
                grp_merged["subcategory"]
                .replace("nan", pd.NA)
                .dropna()
                .value_counts()
                .head(2)
            )
            for sc_name in top2.index:
                sc_grp = grp_merged[grp_merged["subcategory"] == sc_name]
                sc_depts = sc_grp["department"].replace("nan", pd.NA).dropna().value_counts()
                dept_str = _format_dept_str({d: int(c) for d, c in sc_depts.items()})
                subcat_rows.append({col_dept: "", col_dc: "", col_sub: sc_name, col_sdepts: dept_str})

        row_groups.append({
            col_cat: _clean_display(cat),
            col_cnt: cnt,
            "details": dept_rows + subcat_rows,
        })

    return {"columns": columns, "rows": [], "span_columns": 2, "row_groups": row_groups}


def build_tdb_table(
    df_perron: pd.DataFrame | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict:
    """Table 14: Трудовая дисциплина и безопасность — subcategories + dept breakdown."""
    col_sub = "Подкатегория"
    col_cnt = "Кол-во нарушений"
    col_dept = "Служба"
    col_dc = "Кол-во нарушений (служба)"
    columns = [col_sub, col_cnt, col_dept, col_dc]

    if df_perron is None:
        return {"columns": columns, "rows": [], "message": NOT_UPLOADED}

    sub = _filter_perron_cats(df_perron, start, end, _TDB_PARENT_CATS_FILE)

    norm_map: dict[str, int] = {}
    catchall_idx: int | None = None
    for gi, (_, vals) in enumerate(_TDB_SUBCAT_GROUPS):
        if vals is None:
            catchall_idx = gi
        else:
            for v in vals:
                norm_map[_norm_subcat(v)] = gi

    counts = [0] * len(_TDB_SUBCAT_GROUPS)
    dept_per_group: list[dict[str, int]] = [{} for _ in _TDB_SUBCAT_GROUPS]

    sub_merged = _merge_dst(sub)
    for _, row in sub_merged.iterrows():
        raw_sub = str(row.get("subcategory", ""))
        dept = str(row.get("department", ""))
        gi = norm_map.get(_norm_subcat(raw_sub))
        if gi is None:
            gi = catchall_idx
        if gi is not None:
            counts[gi] += 1
            if dept not in ("nan", ""):
                dept_per_group[gi][dept] = dept_per_group[gi].get(dept, 0) + 1

    row_groups = []
    grand_total = 0
    all_depts: dict[str, int] = {}

    for gi, (label, _) in enumerate(_TDB_SUBCAT_GROUPS):
        c = counts[gi]
        grand_total += c
        depts = sorted(dept_per_group[gi].items(), key=lambda x: -x[1])
        for d, dc in depts:
            all_depts[d] = all_depts.get(d, 0) + dc
        row_groups.append({
            col_sub: label,
            col_cnt: c,
            "details": [{col_dept: d, col_dc: dc} for d, dc in depts],
        })

    return {"columns": columns, "rows": [], "span_columns": 2, "row_groups": row_groups}


# ---------------------------------------------------------------------------
# Tables 15, 16: flat subcategory breakdown (no dept split) — generic helper
# ---------------------------------------------------------------------------

def _build_flat_subcat_table(
    df_perron: pd.DataFrame | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
    parent_cats: list[str],
    subcat_groups: list[tuple[str, list[str] | None]],
) -> dict:
    """Flat Подкатегория | Кол-во нарушений table filtered by parent categories."""
    col_sub, col_cnt = "Подкатегория", "Кол-во нарушений"
    columns = [col_sub, col_cnt]
    if df_perron is None:
        return {"columns": columns, "rows": [], "message": NOT_UPLOADED}

    sub = _filter_perron_cats(df_perron, start, end, parent_cats)

    norm_map: dict[str, int] = {}
    catchall_idx: int | None = None
    for gi, (_, vals) in enumerate(subcat_groups):
        if vals is None:
            catchall_idx = gi
        else:
            for v in vals:
                norm_map[_norm_subcat(v)] = gi

    counts = [0] * len(subcat_groups)
    for raw_sub in sub["subcategory"]:
        gi = norm_map.get(_norm_subcat(str(raw_sub)))
        if gi is None:
            gi = catchall_idx
        if gi is not None:
            counts[gi] += 1

    rows = [{col_sub: label, col_cnt: counts[gi]} for gi, (label, _) in enumerate(subcat_groups)]
    return {"columns": columns, "rows": rows}


_DKV_PARENT_CATS_FILE = [
    "Высадка посадка пассажиров",
    "Высадка/посадка пассажиров",
    "Высадка, посадка пассажиров",
    "Доставка пассажиров автобусами",
    "Ошибочная высадка пассажиров",
]

_DKV_SUBCAT_GROUPS: list[tuple[str, list[str] | None]] = [
    ("Контроль скоплений пассажиров на трапе",           ["Контроль скоплений пассажиров на трапе",
                                                           "Контроль скоплении пассажиров на трапе"]),
    ("Проверка безопасной высадки и посадки пассажиров", ["Проверка безопасной высадки и посадки пассажиров"]),
    ("Включение информационного табло",                  ["Включение информационного табло"]),
    ("Запрос на разрешение к высадке пассажиров",        ["Запрос на разрешение к высадке пассажиров"]),
    ("Соблюдение схемы расположения водителей",          ["Соблюдение схемы расположения водителей"]),
    ("Контроль за пассажирами",                          ["Контроль за пассажирами"]),
    ("Доставка пассажиров БК",                           ["Доставка пассажиров БК"]),
    ("Открытие дверей при неблагоприятных погодных условиях", [
        "Открытие дверей при неблагоприятных погодных условиях",
        "Открытие дверей  при неблагоприятных погодных условиях",
    ]),
    ("Голосовое оповещение в автобусе",                  ["Голосовое оповещение в автобусе"]),
]


def build_dkv_table(
    df_perron: pd.DataFrame | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict:
    """Table 15: Доставка клиентов с/до ВС — subcategory flat breakdown."""
    return _build_flat_subcat_table(df_perron, start, end, _DKV_PARENT_CATS_FILE, _DKV_SUBCAT_GROUPS)


_OB_PARENT_CATS_FILE = [
    "Комплектация багажа",
    "Доставка багажа из в ЗО на с МС",
    "Доставка багажа из/в ЗО на/с МС",
]

_OB_SUBCAT_GROUPS: list[tuple[str, list[str] | None]] = [
    ("Повреждение",                                              ["Повреждение"]),
    ("Загрузка в соответствующее СД",                           ["Загрузка в соответствующее СД"]),
    ("Корректность загрузки багажа",                            ["Корректность загрузки багажа"]),
    ("Длительное ожидание выдачи багажа",                       ["Длительное ожидание выдачи багажа"]),
    ("Вылет пассажира без багажа",                              ["Вылет пассажира без багажа"]),
    ("Проверка СД",                                             ["Проверка СД"]),
    ("Приоритетность выгрузки багажа",                          ["Приоритетность выгрузки багажа"]),
    ("Другое",                                                  None),
    ("Проверка целостности багажа и средств пакетирования",     [
        "Проверка целостности багажа и средств пакетирования",
    ]),
    ("Недостача",                                               ["Недостача"]),
]


def build_ob_table(
    df_perron: pd.DataFrame | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict:
    """Table 16: Обслуживание багажа — subcategory flat breakdown."""
    return _build_flat_subcat_table(df_perron, start, end, _OB_PARENT_CATS_FILE, _OB_SUBCAT_GROUPS)


# ---------------------------------------------------------------------------
# Tables 17, 17.1: perron employee violation tables
# ---------------------------------------------------------------------------

def build_perron_employees_table(
    df_perron: pd.DataFrame | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> tuple[list[dict], list[str]]:
    """Table 17: perron employees with >= 3 violations, same logic as table 9."""
    return build_avk_employees_table(df_perron, start, end)


def build_perron_repeat_employees_table(
    df_perron: pd.DataFrame | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[dict]:
    """Table 17.1: perron repeat employees by subcategory, same logic as table 9.1."""
    return build_avk_repeat_employees_table(df_perron, start, end)


# ---------------------------------------------------------------------------
# Table 11 (distribution): perron violation distribution by category + dept breakdown
# ---------------------------------------------------------------------------

_PERRON_CAT_GROUPS: list[tuple[str, list[str]]] = [
    ("Обслуживание ВС", _AVS_FILE_VALUES),
    ("Назначение и выполнение задач", [
        "Своевременность назначения и выполнения задач",
        "Взаимодействие между подразделениями",
    ]),
    ("Эксплуатация ТС", [
        "Несоблюдение ПДД",
        "Световое обозначение транспорта",
        "Обеспечение остановки и стоянки ТС",
        "ДТП",
        "Движение без регулировщика",
        "Осмотр ТС",
        "Чистота ТС",
        "Отказы и неисправности ТС",
    ]),
    ("Трудовая дисциплина и безопасность", [
        "Техника безопасности охраны труда",
        "Алкогольное и наркотическое опьянение",
        "Алкогольное и наркотическое опъянение",
        "Внутриобъектовый режим",
        "Нарушение ФО этики",
        "Нарушение ФО/этики",
        "Нарушение ФО,этики",
    ]),
    ("Доставка клиентов с/до ВС", [
        "Высадка посадка пассажиров",
        "Доставка пассажиров автобусами",
        "Ошибочная высадка пассажиров",
    ]),
    ("Обслуживание багажа", [
        "Комплектация багажа",
        "Доставка багажа из/в ЗО на/с МС",
    ]),
    ("Обслуживание груза/почты", [
        "Обслуживание груза/почты",
        "Обслуживание груза почты",
    ]),
]

# Normalized lookup: norm_value → group_index (last mapping wins for duplicates)
_PERRON_CAT_NORM_MAP: dict[str, int] = {}
for _pcgi, (_pclbl, _pcvals) in enumerate(_PERRON_CAT_GROUPS):
    for _pcv in _pcvals:
        _PERRON_CAT_NORM_MAP[_norm_cat(_pcv)] = _pcgi


def build_perron_categories_table(
    df_perron: pd.DataFrame | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict:
    """
    Table 11: perron violations (Заключение = «с виной») grouped by category.
    Returns a dict with row_groups for merged-cell rendering:
      each group = {display_col: val, ..., 'details': [{dept_col: val, count_col: val}, ...]}
    ДСТ/ССТ/СПТ are merged in the department breakdown.
    """
    col_cat = "Категория"
    col_total = "Кол-во нарушений"
    col_dept = "Служба"
    col_dept_cnt = "Кол-во нарушений (служба)"
    columns = [col_cat, col_total, col_dept, col_dept_cnt]

    if df_perron is None:
        return {
            "columns": columns,
            "rows": [],
            "message": NOT_UPLOADED,
        }

    in_perron = df_perron[
        (df_perron["date"] >= start)
        & (df_perron["date"] <= end)
        & (df_perron["conclusion"] == WITH_FAULT_CONCLUSION)
    ].copy()

    # Merge ДСТ/ССТ/СПТ in dept column
    in_perron["department"] = in_perron["department"].apply(
        lambda d: "ДСТ" if d in _DST_ALIASES else d
    )

    # Assign each row to a group
    in_perron["_group_idx"] = in_perron["category"].apply(
        lambda c: _PERRON_CAT_NORM_MAP.get(_norm_cat(str(c)))
    )

    row_groups = []
    for gi, (label, _) in enumerate(_PERRON_CAT_GROUPS):
        grp = in_perron[in_perron["_group_idx"] == gi]
        total = len(grp)
        dept_counts = (
            grp["department"]
            .replace("nan", pd.NA)
            .dropna()
            .value_counts()
            .sort_values(ascending=False)
        )
        details = [
            {col_dept: dept, col_dept_cnt: int(cnt)}
            for dept, cnt in dept_counts.items()
        ]
        row_groups.append({
            col_cat: label,
            col_total: total,
            "details": details,
        })

    return {
        "columns": columns,
        "rows": [],
        "span_columns": 2,
        "row_groups": row_groups,
    }


def _not_uploaded_table(tid: str, title: str, columns: list[str]) -> dict:
    return {
        "id": tid,
        "title": title,
        "columns": columns,
        "message": NOT_UPLOADED,
        "rows": [],
    }


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_month_tables(
    df_perron: pd.DataFrame | None,
    df_avk: pd.DataFrame | None,
    df_appeals: pd.DataFrame | None,
    production_data: dict[str, int | None] | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
    granularity: str = "month",
) -> list[dict]:
    production_columns = PRODUCTION_ROWS

    if production_data is not None:
        production_table = {
            "id": "production_indicators",
            "title": "1. Производственные показатели",
            "columns": production_columns,
            "rows": build_production_table(production_data),
        }
    else:
        production_table = _not_uploaded_table(
            "production_indicators",
            "1. Производственные показатели",
            production_columns,
        )

    violations_appeals_table = {
        "id": "violations_appeals",
        "title": "2. Кол-во нарушений и обращений",
        "columns": ["Период", COL_COMBINED, COL_APPEALS_NO_THANKS],
        "rows": build_violations_appeals_table(df_perron, df_avk, df_appeals, start, end, granularity),
    }

    dept_cols = ["Служба", "Кол-во нарушений"]
    if df_avk is not None:
        avk_dept_table = {
            "id": "avk_departments",
            "title": "3. Количество нарушений в АВК",
            "columns": dept_cols,
            "rows": build_avk_departments_table(df_avk, start, end),
        }
    else:
        avk_dept_table = _not_uploaded_table(
            "avk_departments", "3. Количество нарушений в АВК", dept_cols
        )

    cat_cols = ["Категория", "Кол-во нарушений"]
    if df_avk is not None:
        avk_cat_table = {
            "id": "avk_categories",
            "title": "4. Распределение нарушений в АВК",
            "columns": cat_cols,
            "rows": build_avk_categories_table(df_avk, start, end),
        }
    else:
        avk_cat_table = _not_uploaded_table(
            "avk_categories", "4. Распределение нарушений в АВК", cat_cols
        )

    subcat_cols = ["Подкатегория", "Кол-во нарушений"]
    subcat_tables = []
    for tid, title, cat_keys, groups in _SUBCAT_TABLES:
        if df_avk is not None:
            subcat_tables.append({
                "id": tid,
                "title": title,
                "columns": subcat_cols,
                "rows": build_avk_subcategory_table(df_avk, start, end, cat_keys, groups),
            })
        else:
            subcat_tables.append(_not_uploaded_table(tid, title, subcat_cols))

    # Table 9: employees
    emp_cols_default = ["Сотрудник", _COL_2M, _COL_1M, _COL_CUR]
    if df_avk is not None:
        emp_rows, emp_cols = build_avk_employees_table(df_avk, start, end)
        employees_table: dict = {
            "id": "avk_employees",
            "title": "9. Сотрудники АВК",
            "columns": emp_cols,
            "rows": emp_rows,
        }
    else:
        employees_table = _not_uploaded_table("avk_employees", "9. Сотрудники АВК", emp_cols_default)

    # Table 9.1: repeat employees
    repeat_cols = ["Подразделение/Сотрудник", "Подкатегория нарушения", "Кол-во нарушений"]
    if df_avk is not None:
        repeat_table: dict = {
            "id": "avk_repeat_employees",
            "title": "9.1 Повторяющиеся сотрудники АВК",
            "columns": repeat_cols,
            "rows": build_avk_repeat_employees_table(df_avk, start, end),
        }
    else:
        repeat_table = _not_uploaded_table("avk_repeat_employees", "9.1 Повторяющиеся сотрудники АВК", repeat_cols)

    # Table 10: perron departments
    perron_dept_cols = ["Служба", "Кол-во нарушений"]
    if df_perron is not None:
        perron_dept_table: dict = {
            "id": "perron_departments",
            "title": "10. Количество нарушений на перроне",
            "columns": perron_dept_cols,
            "rows": build_perron_departments_table(df_perron, start, end),
        }
    else:
        perron_dept_table = _not_uploaded_table(
            "perron_departments", "10. Количество нарушений на перроне", perron_dept_cols
        )

    # Table 11: perron category distribution with dept breakdown
    perron_cat_data = build_perron_categories_table(df_perron, start, end)
    perron_cat_table: dict = {
        "id": "perron_categories",
        "title": "11. Распределение нарушений на перроне",
        **perron_cat_data,
    }

    _flat_sub_cols = ["Подкатегория", "Кол-во нарушений"]
    _tdb_cols = ["Подкатегория", "Кол-во нарушений", "Служба", "Кол-во нарушений (служба)"]
    _perron_emp_cols_default = ["Сотрудник", _COL_2M, _COL_1M, _COL_CUR]
    _perron_repeat_cols = ["Подразделение/Сотрудник", "Подкатегория нарушения", "Кол-во нарушений"]
    if df_perron is not None:
        avs: dict = {"id": "avs_breakdown", "title": "11. Обслуживание ВС",
                     **build_avs_table(df_perron, start, end)}
        nvz: dict = {"id": "nvz_breakdown", "title": "12. Назначение и выполнение задач",
                     **build_nvz_table(df_perron, start, end)}
        ets: dict = {"id": "ets_breakdown", "title": "13. Эксплуатация ТС",
                     **build_ets_table(df_perron, start, end)}
        tdb: dict = {"id": "tdb_breakdown", "title": "14. Трудовая дисциплина и безопасность",
                     **build_tdb_table(df_perron, start, end)}
        dkv: dict = {"id": "dkv_breakdown", "title": "15. Доставка клиентов с/до ВС",
                     **build_dkv_table(df_perron, start, end)}
        ob: dict = {"id": "ob_breakdown", "title": "16. Обслуживание багажа",
                    **build_ob_table(df_perron, start, end)}
        perron_emp_rows, perron_emp_cols = build_perron_employees_table(df_perron, start, end)
        perron_emp_table: dict = {
            "id": "perron_employees", "title": "17. Сотрудники перрон",
            "columns": perron_emp_cols, "rows": perron_emp_rows,
        }
        perron_repeat_table: dict = {
            "id": "perron_repeat_employees", "title": "17.1 Повторяющиеся сотрудники перрон",
            "columns": _perron_repeat_cols,
            "rows": build_perron_repeat_employees_table(df_perron, start, end),
        }
    else:
        avs = _not_uploaded_table("avs_breakdown", "11. Обслуживание ВС",
                                  ["Категория", "Кол-во нарушений"])
        nvz = _not_uploaded_table("nvz_breakdown", "12. Назначение и выполнение задач",
                                  ["Категория", "Кол-во нарушений", "Служба", "Кол-во нарушений (служба)"])
        ets = _not_uploaded_table("ets_breakdown", "13. Эксплуатация ТС",
                                  ["Категория", "Кол-во нарушений", "Служба", "Кол-во нарушений (служба)",
                                   "Типовые нарушения", "Кол-во по службам"])
        tdb = _not_uploaded_table("tdb_breakdown", "14. Трудовая дисциплина и безопасность", _tdb_cols)
        dkv = _not_uploaded_table("dkv_breakdown", "15. Доставка клиентов с/до ВС", _flat_sub_cols)
        ob = _not_uploaded_table("ob_breakdown", "16. Обслуживание багажа", _flat_sub_cols)
        perron_emp_table = _not_uploaded_table("perron_employees", "17. Сотрудники перрон",
                                               _perron_emp_cols_default)
        perron_repeat_table = _not_uploaded_table("perron_repeat_employees",
                                                  "17.1 Повторяющиеся сотрудники перрон",
                                                  _perron_repeat_cols)

    return [
        production_table, violations_appeals_table, avk_dept_table, avk_cat_table,
        *subcat_tables,
        employees_table, repeat_table,
        perron_dept_table, perron_cat_table,
        avs, nvz, ets, tdb, dkv, ob,
        perron_emp_table, perron_repeat_table,
    ]

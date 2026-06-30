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


def read_avk_full(file_obj: BinaryIO) -> pd.DataFrame:
    """
    Read AVK violations file and return DataFrame with
    columns [date, conclusion, department].
    Used by table 2 (conclusion) and table 3 (department).
    """
    raw = pd.read_excel(file_obj, sheet_name=VIOLATIONS_SHEET)
    cols = list(raw.columns)

    date_c = _find_col(cols, "дата")
    conclusion_c = _find_col(cols, "заключен")
    dept_c = _find_col(cols, "подразделен")

    if date_c is None or conclusion_c is None:
        raise ValueError(
            "В файле «Нарушения в АВК» не найдены столбцы «Дата» и/или «Заключение»"
        )

    keep = [date_c, conclusion_c]
    rename = {date_c: "date", conclusion_c: "conclusion"}
    if dept_c is not None:
        keep.append(dept_c)
        rename[dept_c] = "department"

    result = raw[keep].rename(columns=rename)
    result["date"] = pd.to_datetime(result["date"], errors="coerce", dayfirst=True)
    result = result.dropna(subset=["date"]).reset_index(drop=True)
    result["conclusion"] = result["conclusion"].astype(str).str.strip()
    if "department" in result.columns:
        result["department"] = result["department"].astype(str).str.strip()
    else:
        result["department"] = ""
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
    df_appeals: pd.DataFrame | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[dict]:
    """
    Table 3: per-department violation count.
    Departments come from AVK's 'department' column.
    For each department:
      count = AVK rows in period with that department
              + confirmed appeals in period where responsible_services contains the department
    Bottom row: ИТОГО.
    """
    if df_avk is None:
        return []

    in_avk = df_avk[
        (df_avk["date"] >= start) & (df_avk["date"] <= end)
    ]

    # Unique departments from AVK (preserve order by descending count)
    dept_counts_avk = (
        in_avk["department"]
        .replace("nan", pd.NA)
        .dropna()
        .value_counts()
    )
    departments = list(dept_counts_avk.index)

    # Confirmed appeals in period
    confirmed_appeals = None
    if df_appeals is not None:
        in_ap = df_appeals[
            (df_appeals["date"] >= start) & (df_appeals["date"] <= end)
        ]
        confirmed_appeals = in_ap[in_ap["result"] == CONFIRMED_RESULT]

    rows = []
    total = 0
    for dept in departments:
        avk_count = int(dept_counts_avk.get(dept, 0))

        appeals_count = 0
        if confirmed_appeals is not None:
            appeals_count = int(
                confirmed_appeals["responsible_services"].apply(lambda s: dept in s).sum()
            )

        count = avk_count + appeals_count
        total += count
        rows.append({"Служба": dept, "Кол-во нарушений": count})

    rows.append({"Служба": "ИТОГО", "Кол-во нарушений": total})
    return rows


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
            "rows": build_avk_departments_table(df_avk, df_appeals, start, end),
        }
    else:
        avk_dept_table = _not_uploaded_table(
            "avk_departments", "3. Количество нарушений в АВК", dept_cols
        )

    return [production_table, violations_appeals_table, avk_dept_table]

"""Обработка модуля «Отчёт по качеству» — единый набор таблиц без разделения
на разделы Нарушения/Проверки/Мониторинг.

На вход — до шести независимо загружаемых excel-файлов: «Нарушения на
перроне», «Нарушения в АВК» (лист «ТАБЛИЦА» в каждом, с разным регистром
колонки даты — «Дата»/«дата» — и разным набором остальных колонок),
«Проверки GRH» (листы «РПО» и «ФО и СИЗ» — по одному на каждую из таблиц
3 и 4), «Мониторинг LIR/СЗВ» (лист «LIR СЗВ 2026», колонки «Дата», «ФИО
Агента», «Описание причины замечания» — для таблиц 6, 6.1, 6.2) и
«Проверки PAB» (листы «Нарушение ФО, этики», «Оформление РК», « Сверка
данных перед выдачей ПТ» и «Оформление багажа», в каждом — колонки
«Дата», «№ стойки» — для таблиц 7, 8, 9, 10 соответственно, вместе с
«Нарушения в АВК» в каждой из них). Каждая таблица строится из того, что
загружено; если для неё не хватает нужного файла/листа — вместо данных
выводится отметка `NOT_UPLOADED` ("Файл не загружен"), на уровне всей
таблицы (1, 1.1, 2, 2.1, 5, 6, 6.1, 6.2, 7.1, 11) либо на уровне отдельных
ячеек, если в одной таблице разные колонки зависят от разных файлов (3,
4, 7, 8, 9, 10).

Для таблицы 1 нужны дата и категория нарушения; для детализирующих таблиц
(1.1 и 2.1) — также описание, исполнитель и подразделение; для таблицы 2
(только файл «Перрон») — дополнительно подкатегория и причина; для таблиц
3 и 4 — подкатегория и заключение (файл «Перрон») плюс дата из
соответствующего листа файла GRH; для таблицы 5 (только файл «Перрон») —
описание, место, бортовой номер, исполнитель и подразделение; для таблиц
6, 6.1, 6.2 (только файл «Мониторинг LIR/СЗВ») — дата, ФИО агента,
описание причины замечания и (если в файле есть колонка с «рейс» в
названии) № рейса — строка считается замечанием, если в описании причины
не написано «без замечаний»; для таблиц 7, 8, 9, 10 — дата и № стойки из
соответствующего листа файла «Проверки PAB» (кол-во проверок, кол-во
уникальных стоек) плюс категория/подкатегория и заключение из файла
«Нарушения в АВК» (кол-во нарушений: для таблицы 7 — категория =
«Нарушение ФО, этики», для таблицы 8 — подкатегория = «Ручная кладь
оформлена с нарушением», для таблицы 9 — подкатегория = «Проверка данных
перед выдачей ПТ», для таблицы 10 — категория = «Оформление багажа»; во
всех четырёх — заключение = «с виной» либо пусто/не заполнено, см.
`_build_pab_avk_checks_table`); для таблицы 7.1 — подкатегория, заключение
и описание из того же файла «Нарушения в АВК» (по строке на уникальную
подкатегорию в категории «Нарушение ФО, этики»; «Кол-во случаев» — с тем
же условием на заключение, что и в таблице 7; «Типовые нарушения» —
уникальные описания через «; », где варианты, отличающиеся только
пробелами/пунктуацией/опечатками, схлопываются в один текст, см.
`_canonicalize_descriptions`); для таблицы 11 — дата и заключение из
объединённых файлов «Перрон»+«Нарушения в АВК» (кол-во строк с заключением
«с виной» либо пусто/не заполнено, без разбивки по категориям). У таблиц
7, 8, 9, 10 пятая колонка — всегда пустая (без заголовка и без данных),
оставлена для ручных заметок. Строки в детализирующих и списочных
таблицах (1.1, 2.1, 5) сортируются по дате от старых к новым.

ФИО агентов в файле LIR/СЗВ могут заноситься с разным количеством пробелов,
регистром или опечатками — перед подсчётом по сотруднику такие варианты
схлопываются в одно каноническое имя (см. `_canonicalize_agent_names`):
сначала группировка по «очищенному» от лишних пробелов и регистра
варианту, затем — слияние похожих вариантов (опечатки) по строковому
сходству (`difflib`). Строки без ФИО (например, из-за объединённых ячеек
в исходном файле) не отбрасываются из таблицы 6 — «Кол-во проверок» считает
все строки с валидной датой за период независимо от наличия ФИО; такие
строки просто не попадают в таблицы 6.1/6.2, где группировка идёт по
сотруднику. В таблице 6.1 каждая ячейка с числом нарушений сотрудника за
период, если их больше нуля, дополняется в круглых скобках перечислением
через «; » пар «№ рейса Дата» по каждому нарушению (склеенных через
пробел) — см. `build_lir_szv_employee_detail`.

Данные за выбранный период агрегируются по срезам (неделя/месяц/квартал/
год) календарными границами, с обрезкой первого и последнего интервала по
границам периода — например, период 08.06.2026-21.06.2026 со срезом
«неделя» даёт два интервала: 08.06-14.06 и 15.06-21.06. Таблица 6.1 — по
строке на сотрудника, по колонке на тот же набор срезов, что и в таблице 6
(внутри выбранного периода), со значением — кол-во нарушений сотрудника в
этом срезе; таблица 6.2 — топ-10 сотрудников по нарушениям за всю историю
загруженного файла, независимо от выбранного периода.
"""

import difflib
import re
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
DESCRIPTION_SIMILARITY_THRESHOLD = 0.85

FO_ETHICS_CATEGORY = "Нарушение ФО, этики"
PAB_FO_ETHICS_SHEET = "Нарушение ФО, этики"

RK_VIOLATION_SUBCATEGORY = "Ручная кладь оформлена с нарушением"
PAB_RK_SHEET = "Оформление РК"

PT_VIOLATION_SUBCATEGORY = "Проверка данных перед выдачей ПТ"
PAB_PT_SHEET = " Сверка данных перед выдачей ПТ"

BAGGAGE_CATEGORY = "Оформление багажа"
PAB_BAGGAGE_SHEET = "Оформление багажа"

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


def read_pab_checks_sheet(file_obj: BytesIO, sheet_name: str) -> pd.DataFrame | None:
    xl = pd.ExcelFile(file_obj)
    if sheet_name not in xl.sheet_names:
        return None

    df = xl.parse(sheet_name)
    columns = list(df.columns)
    date_col = _find_column(columns, "дата")
    stand_col = _find_column(columns, "№ стойки")
    if date_col is None or stand_col is None:
        raise ValueError(f"На листе «{sheet_name}» файла «Проверки PAB» нет колонок «Дата» и/или «№ стойки»")

    result = df[[date_col, stand_col]].rename(columns={date_col: "date", stand_col: "stand"})
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    result = result.dropna(subset=["date"])
    result["stand"] = result["stand"].apply(lambda v: str(v).strip() if pd.notna(v) else None)
    return result


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


def _canonicalize_values(values: pd.Series, normalize, threshold: float) -> dict[str, str]:
    """Map each distinct value to a canonical display value, merging variants
    that normalize to the same key, or that are close enough (by string
    similarity of their normalized form) to be considered typos of each other."""
    counts = values.value_counts()
    fold_groups: dict[str, list[str]] = {}
    for value in counts.index:
        fold_groups.setdefault(normalize(value), []).append(value)

    fold_keys = list(fold_groups.keys())
    clusters: list[list[str]] = []
    for key in fold_keys:
        match = next(
            (
                cluster
                for cluster in clusters
                if any(
                    difflib.SequenceMatcher(None, key, existing).ratio() >= threshold for existing in cluster
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
        candidates = [value for fold_key in cluster for value in fold_groups[fold_key]]
        canonical = max(candidates, key=lambda v: counts[v])
        for fold_key in cluster:
            for value in fold_groups[fold_key]:
                mapping[value] = canonical
    return mapping


def _canonicalize_agent_names(names: pd.Series) -> dict[str, str]:
    return _canonicalize_values(names, normalize=lambda n: n.casefold(), threshold=AGENT_NAME_SIMILARITY_THRESHOLD)


_PUNCTUATION_RE = re.compile(r"[^\w\s]", re.UNICODE)


def _normalize_description_key(text: str) -> str:
    no_punctuation = _PUNCTUATION_RE.sub("", text)
    return " ".join(no_punctuation.split()).casefold()


def _canonicalize_descriptions(descriptions: pd.Series) -> dict[str, str]:
    return _canonicalize_values(
        descriptions, normalize=_normalize_description_key, threshold=DESCRIPTION_SIMILARITY_THRESHOLD
    )


def read_lir_szv_file(file_obj: BytesIO) -> pd.DataFrame:
    xl = pd.ExcelFile(file_obj)
    if LIR_SZV_SHEET not in xl.sheet_names:
        raise ValueError(f"В файле «Мониторинг LIR/СЗВ» нет листа «{LIR_SZV_SHEET}»")
    df = xl.parse(LIR_SZV_SHEET)
    columns = list(df.columns)

    date_col = _find_column(columns, "дата") or _find_column_contains(columns, "дата")
    agent_col = _find_column_contains(columns, "фио")
    reason_col = _find_column_contains(columns, "причин")
    flight_col = _find_column_contains(columns, "рейс")
    if date_col is None or agent_col is None or reason_col is None:
        raise ValueError(
            "В файле «Мониторинг LIR/СЗВ» нет колонок «Дата», «ФИО Агента» "
            "и/или «Описание причины замечания»"
        )

    keep = [date_col, agent_col, reason_col]
    rename = {date_col: "date", agent_col: "agent_raw", reason_col: "reason_description"}
    if flight_col is not None:
        keep.append(flight_col)
        rename[flight_col] = "flight"

    result = df[keep].rename(columns=rename)
    result["date"] = pd.to_datetime(result["date"], errors="coerce", dayfirst=True)
    result = result.dropna(subset=["date"])

    result["agent_raw"] = result["agent_raw"].apply(_clean_agent_name)

    named = result.dropna(subset=["agent_raw"])
    canonical_map = _canonicalize_agent_names(named["agent_raw"])
    result["agent"] = result["agent_raw"].map(canonical_map)

    result["reason_description"] = result["reason_description"].apply(
        lambda v: str(v).strip() if pd.notna(v) else ""
    )
    result["has_violation"] = result["reason_description"].str.casefold() != NO_VIOLATIONS_TEXT.casefold()
    if "flight" in result.columns:
        result["flight"] = result["flight"].apply(lambda v: str(v).strip() if pd.notna(v) else None)
    else:
        result["flight"] = None
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


def lir_szv_period_labels(start: pd.Timestamp, end: pd.Timestamp, granularity: str) -> list[str]:
    return [_format_period(bucket_start, bucket_end, granularity) for bucket_start, bucket_end in generate_buckets(start, end, granularity)]


def build_lir_szv_employee_detail(
    df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, granularity: str
) -> list[dict]:
    in_period = df[(df["date"] >= start) & (df["date"] <= end) & df["has_violation"]]
    buckets = generate_buckets(start, end, granularity)
    totals = in_period.groupby("agent").size().sort_values(ascending=False)

    rows = []
    for agent in totals.index:
        agent_data = in_period[in_period["agent"] == agent]
        row = {"ФИО Агента": agent}
        for bucket_start, bucket_end in buckets:
            label = _format_period(bucket_start, bucket_end, granularity)
            bucket_rows = agent_data[(agent_data["date"] >= bucket_start) & (agent_data["date"] <= bucket_end)]
            count = len(bucket_rows)
            if count == 0:
                row[label] = 0
            else:
                details = "; ".join(
                    " ".join(part for part in (r["flight"], r["date"].strftime("%d.%m.%Y")) if part)
                    for _, r in bucket_rows.sort_values("date").iterrows()
                )
                row[label] = f"{count} ({details})"
        rows.append(row)
    return rows


def build_lir_szv_top_employees(
    df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, top_n: int = 10
) -> list[dict]:
    violations = df[df["has_violation"]]
    counts = violations.groupby("agent").size().sort_values(ascending=False).head(top_n)

    in_period_agents = set(
        df[(df["date"] >= start) & (df["date"] <= end) & df["has_violation"]]["agent"].dropna()
    )
    return [
        {
            "ФИО Агента": agent,
            "Кол-во нарушений": int(count),
            "За выбранный период": "❗" if agent in in_period_agents else "",
        }
        for agent, count in counts.items()
    ]


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


def _category_violations_filter(df_avk: pd.DataFrame, category: str) -> pd.DataFrame:
    conclusion = df_avk["conclusion"]
    no_fault_recorded = conclusion.isna()
    return df_avk[(df_avk["category"] == category) & ((conclusion == WITH_FAULT_CONCLUSION) | no_fault_recorded)]


def _subcategory_violations_filter(df_avk: pd.DataFrame, subcategory: str) -> pd.DataFrame:
    conclusion = df_avk["conclusion"]
    no_fault_recorded = conclusion.isna()
    return df_avk[(df_avk["subcategory"] == subcategory) & ((conclusion == WITH_FAULT_CONCLUSION) | no_fault_recorded)]


def _build_pab_avk_checks_table(
    violations: pd.DataFrame | None,
    df_pab: pd.DataFrame | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
    granularity: str,
) -> list[dict]:
    """Shared builder for tables 7/8/9: «Кол-во проверок» и «Кол-во уникальных
    стоек» по листу файла «Проверки PAB», «Кол-во нарушений» по уже
    отфильтрованным строкам файла «Нарушения в АВК», с пустой 4-й колонкой."""
    buckets = generate_buckets(start, end, granularity)

    rows = []
    for bucket_start, bucket_end in buckets:
        row = {"Период": _format_period(bucket_start, bucket_end, granularity)}
        if df_pab is None:
            row["Кол-во проверок"] = NOT_UPLOADED
        else:
            in_bucket = df_pab[(df_pab["date"] >= bucket_start) & (df_pab["date"] <= bucket_end)]
            row["Кол-во проверок"] = int(len(in_bucket))
        if violations is None:
            row["Кол-во нарушений"] = NOT_UPLOADED
        else:
            in_bucket = violations[(violations["date"] >= bucket_start) & (violations["date"] <= bucket_end)]
            row["Кол-во нарушений"] = int(len(in_bucket))
        row[""] = ""
        if df_pab is None:
            row["Кол-во уникальных стоек"] = NOT_UPLOADED
        else:
            in_bucket = df_pab[(df_pab["date"] >= bucket_start) & (df_pab["date"] <= bucket_end)]
            row["Кол-во уникальных стоек"] = int(in_bucket["stand"].dropna().nunique())
        rows.append(row)
    return rows


def build_fo_ethics_table(
    df_avk: pd.DataFrame | None,
    df_pab: pd.DataFrame | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
    granularity: str,
) -> list[dict]:
    violations = _category_violations_filter(df_avk, FO_ETHICS_CATEGORY) if df_avk is not None else None
    return _build_pab_avk_checks_table(violations, df_pab, start, end, granularity)


def build_baggage_violations_table(
    df_avk: pd.DataFrame | None,
    df_pab: pd.DataFrame | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
    granularity: str,
) -> list[dict]:
    violations = _category_violations_filter(df_avk, BAGGAGE_CATEGORY) if df_avk is not None else None
    return _build_pab_avk_checks_table(violations, df_pab, start, end, granularity)


def build_rk_violations_table(
    df_avk: pd.DataFrame | None,
    df_pab: pd.DataFrame | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
    granularity: str,
) -> list[dict]:
    violations = _subcategory_violations_filter(df_avk, RK_VIOLATION_SUBCATEGORY) if df_avk is not None else None
    return _build_pab_avk_checks_table(violations, df_pab, start, end, granularity)


def build_pt_violations_table(
    df_avk: pd.DataFrame | None,
    df_pab: pd.DataFrame | None,
    start: pd.Timestamp,
    end: pd.Timestamp,
    granularity: str,
) -> list[dict]:
    violations = _subcategory_violations_filter(df_avk, PT_VIOLATION_SUBCATEGORY) if df_avk is not None else None
    return _build_pab_avk_checks_table(violations, df_pab, start, end, granularity)


def build_fo_ethics_subcategory_table(
    df_avk: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> list[dict]:
    in_period = df_avk[
        (df_avk["date"] >= start) & (df_avk["date"] <= end) & (df_avk["category"] == FO_ETHICS_CATEGORY)
    ]
    conclusion = in_period["conclusion"]
    counted = in_period[(conclusion == WITH_FAULT_CONCLUSION) | conclusion.isna()]

    rows = []
    for subcategory in sorted(in_period["subcategory"].dropna().unique()):
        subset = counted[counted["subcategory"] == subcategory]
        descriptions = subset["description"].dropna()
        canonical_map = _canonicalize_descriptions(descriptions)
        canonical_counts = descriptions.map(canonical_map).value_counts()
        rows.append(
            {
                "Категория нарушения": subcategory,
                "Кол-во случаев": int(len(subset)),
                "Типовые нарушения": "; ".join(canonical_counts.index),
            }
        )
    return rows


def build_relative_violations_table(
    df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, granularity: str
) -> list[dict]:
    conclusion = df["conclusion"]
    no_fault_recorded = conclusion.isna()
    violations = df[(conclusion == WITH_FAULT_CONCLUSION) | no_fault_recorded]
    buckets = generate_buckets(start, end, granularity)

    rows = []
    for bucket_start, bucket_end in buckets:
        in_bucket = violations[(violations["date"] >= bucket_start) & (violations["date"] <= bucket_end)]
        rows.append(
            {
                "Период": _format_period(bucket_start, bucket_end, granularity),
                "Кол-во нарушений": int(len(in_bucket)),
            }
        )
    return rows


def _not_uploaded_table(table_id: str, title: str, columns: list[str]) -> dict:
    return {"id": table_id, "title": title, "columns": columns, "message": NOT_UPLOADED, "rows": []}


def build_quality_tables(
    df_perron: pd.DataFrame | None,
    df_avk: pd.DataFrame | None,
    df_grh_rpo: pd.DataFrame | None,
    df_grh_fo_siz: pd.DataFrame | None,
    df_lir: pd.DataFrame | None,
    df_pab_fo_ethics: pd.DataFrame | None,
    df_pab_rk: pd.DataFrame | None,
    df_pab_pt: pd.DataFrame | None,
    df_pab_baggage: pd.DataFrame | None,
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
    employee_total_columns = ["ФИО Агента", "Кол-во нарушений", "За выбранный период"]
    employee_period_columns = ["ФИО Агента"] + lir_szv_period_labels(start, end, granularity)
    if df_lir is not None:
        lir_table = {
            "id": "lir_szv",
            "title": "6. Мониторинг LIR/СЗВ",
            "columns": lir_columns,
            "rows": build_lir_szv_table(df_lir, start, end, granularity),
        }
        lir_employee_detail_table = {
            "id": "lir_szv_employee_detail",
            "title": "6.1. Нарушения по сотрудникам по периодам",
            "columns": employee_period_columns,
            "rows": build_lir_szv_employee_detail(df_lir, start, end, granularity),
        }
        lir_top_employees_table = {
            "id": "lir_szv_top_employees",
            "title": "6.2. Топ-10 сотрудников по нарушениям за всю историю",
            "columns": employee_total_columns,
            "rows": build_lir_szv_top_employees(df_lir, start, end),
        }
    else:
        lir_table = _not_uploaded_table("lir_szv", "6. Мониторинг LIR/СЗВ", lir_columns)
        lir_employee_detail_table = _not_uploaded_table(
            "lir_szv_employee_detail", "6.1. Нарушения по сотрудникам по периодам", employee_period_columns
        )
        lir_top_employees_table = _not_uploaded_table(
            "lir_szv_top_employees", "6.2. Топ-10 сотрудников по нарушениям за всю историю", employee_total_columns
        )

    pab_checks_columns = ["Период", "Кол-во проверок", "Кол-во нарушений", "", "Кол-во уникальных стоек"]

    fo_ethics_table = {
        "id": "fo_ethics",
        "title": "7. Нарушение ФО, этики",
        "columns": pab_checks_columns,
        "rows": build_fo_ethics_table(df_avk, df_pab_fo_ethics, start, end, granularity),
    }

    fo_ethics_subcategory_columns = ["Категория нарушения", "Кол-во случаев", "Типовые нарушения"]
    if df_avk is not None:
        fo_ethics_subcategory_table = {
            "id": "fo_ethics_subcategory",
            "title": "7.1. Нарушения за период",
            "columns": fo_ethics_subcategory_columns,
            "rows": build_fo_ethics_subcategory_table(df_avk, start, end),
        }
    else:
        fo_ethics_subcategory_table = _not_uploaded_table(
            "fo_ethics_subcategory", "7.1. Нарушения за период", fo_ethics_subcategory_columns
        )

    rk_table = {
        "id": "rk_violations",
        "title": "8. Нарушение правил оформления РК",
        "columns": pab_checks_columns,
        "rows": build_rk_violations_table(df_avk, df_pab_rk, start, end, granularity),
    }

    pt_table = {
        "id": "pt_violations",
        "title": "9. Сверка данных перед выдачей ПТ",
        "columns": pab_checks_columns,
        "rows": build_pt_violations_table(df_avk, df_pab_pt, start, end, granularity),
    }

    baggage_table = {
        "id": "baggage_violations",
        "title": "10. Нарушение правил оформления багажа",
        "columns": pab_checks_columns,
        "rows": build_baggage_violations_table(df_avk, df_pab_baggage, start, end, granularity),
    }

    relative_columns = ["Период", "Кол-во нарушений"]
    if combined is not None:
        relative_table = {
            "id": "relative_violations",
            "title": "11. Относительные показатели по нарушениям на 1000 рейсов",
            "columns": relative_columns,
            "rows": build_relative_violations_table(combined, start, end, granularity),
        }
    else:
        relative_table = _not_uploaded_table(
            "relative_violations", "11. Относительные показатели по нарушениям на 1000 рейсов", relative_columns
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
        fo_ethics_table,
        fo_ethics_subcategory_table,
        rk_table,
        pt_table,
        baggage_table,
        relative_table,
    ]

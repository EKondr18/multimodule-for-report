"""Обработка модуля «Добавление комментариев по багажу».

Объединяет накопительный csv «Норматив выдачи багажа» (date, company,
bag_status, flight) с выгрузкой «События по выдаче» (excel с комментариями
по рейсам), сопоставляя по дате рейса и номеру рейса. Номера рейсов в двух
источниках пишутся по-разному («ДР 794» и «ДР794»), поэтому сопоставление
идёт по нормализованному ключу (без пробелов, в верхнем регистре).
"""

import re
from io import BytesIO

import pandas as pd

NORM_COLUMNS = ["date", "company", "bag_status", "flight"]
OUTPUT_COLUMNS = NORM_COLUMNS + ["comment"]

EVENTS_DATE_COL = "Дата рейса"
EVENTS_FLIGHT_COL = "Номер рейса"
EVENTS_COMMENT_COL = "Комментарий"


def _normalize_flight_key(flight: str) -> str:
    return re.sub(r"\s+", "", str(flight)).upper()


def read_norm_file(file_obj: BytesIO) -> pd.DataFrame:
    df = pd.read_csv(file_obj)
    missing = set(NORM_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"В csv-файле нормативов нет колонок: {', '.join(sorted(missing))}")
    return df[NORM_COLUMNS].copy()


def read_events_file(file_obj: BytesIO) -> pd.DataFrame:
    df = pd.read_excel(file_obj)
    required = {EVENTS_DATE_COL, EVENTS_FLIGHT_COL, EVENTS_COMMENT_COL}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"В excel-файле событий нет колонок: {', '.join(sorted(missing))}")

    events = df[[EVENTS_DATE_COL, EVENTS_FLIGHT_COL, EVENTS_COMMENT_COL]].copy()
    events = events.dropna(subset=[EVENTS_DATE_COL, EVENTS_FLIGHT_COL])
    events[EVENTS_COMMENT_COL] = (
        events[EVENTS_COMMENT_COL]
        .fillna("СОБЫТИЕ БЕЗ ОПИСАНИЯ")
        .astype(str)
        .str.strip()
        .replace("", "СОБЫТИЕ БЕЗ ОПИСАНИЯ")
    )
    events["event_date"] = pd.to_datetime(events[EVENTS_DATE_COL], dayfirst=True).dt.strftime("%Y-%m-%d")
    events["flight_key"] = events[EVENTS_FLIGHT_COL].map(_normalize_flight_key)

    grouped = (
        events.groupby(["event_date", "flight_key"])[EVENTS_COMMENT_COL]
        .apply(lambda comments: ", ".join(comments.astype(str)))
        .reset_index()
        .rename(columns={EVENTS_COMMENT_COL: "comment"})
    )
    return grouped


def merge_comments(df_norm: pd.DataFrame, df_events: pd.DataFrame) -> pd.DataFrame:
    df = df_norm.copy()
    df["flight_key"] = df["flight"].map(_normalize_flight_key)

    merged = df.merge(
        df_events,
        left_on=["date", "flight_key"],
        right_on=["event_date", "flight_key"],
        how="left",
    )
    merged["comment"] = merged["comment"].fillna("")
    return merged[OUTPUT_COLUMNS]


# --- TBS ---
#
# В TBS нет накопительного норматива — берём список рейсов из выгрузки
# «прилёт» и подтягиваем к нему комментарии по багажу. Комментарии — свободный
# текст вида «2 м/б», «1 м/б с повреждением», «3 м/б с доступом к содержимому»
# (встречаются варианты без пробела «1м/б» и с опечаткой «м/г» вместо «м/б»).
# Одна строка может содержать сразу несколько мест с разной классификацией
# («1 м/б с повреждением, 2 м/б с доступом к содержимому») — каждое число
# разбирается по контексту до следующего числа. Если в куске текста нет
# явного «доступ», место по умолчанию считается повреждённым (в т.ч. для
# голых чисел и формулировок вроде «мокрое»/«деформирована»). Если в одном
# куске упомянуты оба признака («с доступом к содержимому, с повреждением»),
# количество добавляется в обе колонки.

TBS_FLIGHTS_DATETIME_COL = "Дата/Время рейса"
TBS_FLIGHTS_FLIGHT_COL = "Номер рейса"

TBS_OUTPUT_COLUMNS = [
    "Дата рейса",
    "Номер рейса",
    "Багаж с повреждением",
    "Багаж с признаками доступа к содержимому",
]

_PIECE_COUNT_RE = re.compile(r"(\d+)\s*(?:м\s*/\s*[бг]|мест[оа]\w*)", re.IGNORECASE)
_ULD_CODE_RE = re.compile(r"\b[A-ZА-Я]{2,4}\d{4,6}\b", re.IGNORECASE)


def parse_comment(comment: object) -> tuple[int, int]:
    """Возвращает (кол-во мест с повреждением, кол-во мест с доступом к содержимому)."""
    text = str(comment)
    damage = 0
    access = 0

    matches = list(_PIECE_COUNT_RE.finditer(text))
    if matches:
        for i, m in enumerate(matches):
            qty = int(m.group(1))
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            context = text[start:end].lower()
            has_access = "доступ" in context
            has_damage = ("повреждени" in context) or (not has_access)
            if has_access:
                access += qty
            if has_damage:
                damage += qty
        return damage, access

    # Комментарии без «N м/б» (например, «СП с повреждением. AKE10933. ...») —
    # считаем количество мест по числу перечисленных номеров контейнеров/ULD.
    uld_codes = _ULD_CODE_RE.findall(text)
    if uld_codes:
        qty = len(uld_codes)
        if "доступ" in text.lower():
            access += qty
        else:
            damage += qty

    return damage, access


def read_tbs_flights_file(file_obj: BytesIO) -> pd.DataFrame:
    df = pd.read_excel(file_obj)
    required = {TBS_FLIGHTS_DATETIME_COL, TBS_FLIGHTS_FLIGHT_COL}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"В excel-файле рейсов нет колонок: {', '.join(sorted(missing))}")

    flights = df[[TBS_FLIGHTS_DATETIME_COL, TBS_FLIGHTS_FLIGHT_COL]].copy()
    flights["flight_date"] = pd.to_datetime(flights[TBS_FLIGHTS_DATETIME_COL], dayfirst=True).dt.strftime(
        "%Y-%m-%d"
    )
    flights["flight_key"] = flights[TBS_FLIGHTS_FLIGHT_COL].map(_normalize_flight_key)
    return flights[["flight_date", "flight_key", TBS_FLIGHTS_FLIGHT_COL]].rename(
        columns={TBS_FLIGHTS_FLIGHT_COL: "flight_number"}
    )


def read_tbs_events_file(file_obj: BytesIO) -> pd.DataFrame:
    df = pd.read_excel(file_obj)
    required = {EVENTS_DATE_COL, EVENTS_FLIGHT_COL, EVENTS_COMMENT_COL}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"В excel-файле событий нет колонок: {', '.join(sorted(missing))}")

    events = df[[EVENTS_DATE_COL, EVENTS_FLIGHT_COL, EVENTS_COMMENT_COL]].copy()
    events = events.dropna(subset=[EVENTS_COMMENT_COL])
    events["event_date"] = pd.to_datetime(events[EVENTS_DATE_COL], dayfirst=True).dt.strftime("%Y-%m-%d")
    events["flight_key"] = events[EVENTS_FLIGHT_COL].map(_normalize_flight_key)

    counts = events[EVENTS_COMMENT_COL].map(parse_comment)
    events["damaged_count"] = counts.map(lambda t: t[0])
    events["access_count"] = counts.map(lambda t: t[1])

    grouped = (
        events.groupby(["event_date", "flight_key"])[["damaged_count", "access_count"]]
        .sum()
        .reset_index()
    )
    return grouped


def merge_tbs(df_flights: pd.DataFrame, df_events: pd.DataFrame) -> pd.DataFrame:
    merged = df_flights.merge(
        df_events,
        left_on=["flight_date", "flight_key"],
        right_on=["event_date", "flight_key"],
        how="left",
    )
    merged["damaged_count"] = merged["damaged_count"].fillna(0).astype(int)
    merged["access_count"] = merged["access_count"].fillna(0).astype(int)

    merged = merged.rename(
        columns={
            "flight_date": "Дата рейса",
            "flight_number": "Номер рейса",
            "damaged_count": "Багаж с повреждением",
            "access_count": "Багаж с признаками доступа к содержимому",
        }
    )
    return merged[TBS_OUTPUT_COLUMNS]

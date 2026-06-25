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
    events = events.dropna(subset=[EVENTS_COMMENT_COL])
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

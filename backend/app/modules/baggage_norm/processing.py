"""Обработка выгрузки BI МАВ по обработке багажа («Норматив выдачи багажа»).

Логика 1:1 повторяет исходный код (определение авиакомпании по номеру рейса,
расчёт статуса выдачи багажа, объединение с архивом и дедупликация). Изменена
только реализация: вместо `DataFrame.apply` по строкам — векторизованные
операции pandas, а словарь авиакомпаний строится один раз при импорте модуля,
а не при каждом вызове функции.
"""

from io import BytesIO

import numpy as np
import pandas as pd

HEADER_ROWS_TO_SKIP = 8

COLUMN_NAMES = [
    "date", "flight", "type", "route", "mc", "lent_num", "arrive_runway",
    "bag_waight", "mc_arrive", "hatch_open", "err_hatch_open",
    "beg_unload_spo", "end_unload_spo", "beg_unload_sobgp", "end_unload_sobgp",
    "end_unload_tgo", "err_end_unload", "violation_standart", "time_beg_lenta",
    "time_end_lenta", "violation_first_bag", "violation_last_bag",
    "deliver_1_beg", "deliver_1_end", "deliver_2_beg", "deliver_2_end",
    "deliver_3_beg", "deliver_3_end", "senior_loader",
]

DATALENS_COLUMNS = ["date", "company", "bag_status", "flight"]

# Порядок словаря важен: при пересекающихся префиксах (например, "VSV" есть и
# у AJET, и у SCAT Airlines) побеждает авиакомпания, объявленная раньше — как
# в исходном коде.
AIRLINE_PREFIXES = {
    "КРАСАВИА": ["KI", "SSJ", "ЭК", "КЯ"],
    "Aero Nomad": ["КГ", "KA", "ANK"],
    "AJET": ["VF", "VSV"],
    "Armenia Airways": ["6A", "AMW", "ЕП"],
    "Asia Union Airlines": ["7Q", "AUV"],
    "ATA Airlines": ["I3", "TBZ"],
    "Avia Traffic Company": ["AVJ", "YK", "ТФ"],
    "AZAL": ["AHY", "J2"],
    "CONVIASA": ["V0", "VCV"],
    "flydubai": ["FZ", "FDB"],
    "FLYNAS COMPANY": ["KNE", "XY"],
    "FLYONE Armenia": ["3F", "FIE", "УР"],
    "GEORGIAN AIRWAYS": ["AZO", "TGZ", "ЖГ"],
    "Iran Airtour": ["B9", "IRB"],
    "Iraqi Airways": ["IA", "IAW"],
    "Meraj Air": ["JI", "MRJ"],
    "Nesma Airlines": ["NE", "NMA"],
    "Nouvelair Tunisie": ["BJ", "LBT"],
    "Pegasus": ["PC", "PGT"],
    "Qanot Sharq": ["HH", "QNT"],
    "Red Sea": ["4S", "RSX", "UJ"],
    "Red Wings": ["RWZ", "ИН", "РВЗ"],
    "SCAT Airlines": ["DV", "VSV"],
    "Shirak Avia": ["SHS", "ЮБГ"],
    "Somon Air": ["SZ", "SMR"],
    "Tashkent Air": ["TSK", "U7"],
    "Turkish Airlines": ["THY", "TK", "ТХЫ"],
    "UZBEKISTAN AIRWAYS": ["UZB", "ХИ"],
    "Северо-Запад": ["0E", "NWC", "НВЦ"],
    "Сибирь": ["S7", "SBI", "С7", "СБИ"],
    "Северсталь": ["D2", "SSF", "ССФ"],
    "АЗУР эйр": ["AZV", "АЗЖ"],
    "Ай Флай": ["ФЛ", "РСЫ"],
    "Азимут": ["А4", "АЗО"],
    "Алроса": ["DRU", "ЯМ"],
    "Аэрофлот": ["AFL", "АФЛ", "СУ"],
    "Белавиа": ["В2", "BRU"],
    "Вологодское АП": ["ВГ", "ЖГЖ"],
    "Газпром авиа": ["ГЗП", "4G", "GZP"],
    "Победа": ["PBD", "ДР", "ПБД"],
    "Правительство Венесуэлы": ["YV"],
    "Россия": ["СДМ", "ФВ", "FV"],
    "Руслайн": ["РГ", "РЛУ", "RLU"],
    "Смартавиа": ["5Н", "AUL", "5N", "АУЛ"],
    "Уральские Авиалинии": ["SVR", "U6", "СЖР", "У6"],
    "ЮВТ АЭРО": ["UVT", "ДРУ", "УЖТ", "ЮВ"],
    "Ютэйр": ["UTA", "УТА", "ЮТ", "UT"],
    "Якутия": ["ОП", "СЫЛ", "ЯК"],
    "Hayways": ["Y5", "HYY"],
    "Авиастар-Ту": ["ТУП", "ЦТ", "4B", "TUP"],
    "Чартер": ["ГЛЬ", "GLX", "UK"],
    "TRANSAVIAEXPORT": ["TXC"],
    "Летные проверки и системы": ["LST", "LTS", "ЛТС"],
    "АВИАКОН ЦИТОТРАНС": ["РЦ", "ZR", "AZS", "АЗС"],
}

# Плоский список (префикс, авиакомпания) в исходном порядке приоритета —
# строится один раз при импорте, чтобы не пересобирать словарь на каждой строке.
_PREFIX_LOOKUP: list[tuple[str, str]] = [
    (prefix.upper(), airline)
    for airline, prefixes in AIRLINE_PREFIXES.items()
    for prefix in prefixes
]


def get_airline_by_flight(flight_number: str) -> str:
    flight_upper = flight_number.upper()
    for prefix, airline in _PREFIX_LOOKUP:
        if flight_upper.startswith(prefix):
            return airline
    return "Не найдено"


def assign_airlines(flight_series: pd.Series) -> pd.Series:
    """Та же логика, что get_airline_by_flight, но определяется один раз на
    каждое уникальное значение рейса, а не на каждую строку."""
    unique_flights = flight_series.unique()
    mapping = {flight: get_airline_by_flight(flight) for flight in unique_flights}
    return flight_series.map(mapping)


def calculate_baggage_status(df: pd.DataFrame) -> pd.Series:
    mc_arrive = df["mc_arrive"]
    time_end_lenta = df["time_end_lenta"]
    violation_last_bag = df["violation_last_bag"]
    lent_num = df["lent_num"]

    # mc_arrive/time_end_lenta хранят то Timestamp, то sentinel -1 (после
    # fillna), поэтому сравнение ">" считаем только там, где оба валидны —
    # иначе pandas не может сравнить Timestamp с int.
    marks_present = (mc_arrive != -1) & (time_end_lenta != -1)
    later_than_arrival = pd.Series(False, index=df.index)
    later_than_arrival[marks_present] = (
        time_end_lenta[marks_present] > mc_arrive[marks_present]
    )
    has_marks = marks_present & later_than_arrival

    incorrect = (
        (mc_arrive == -1) | (time_end_lenta == -1) | (marks_present & ~later_than_arrival)
    ) & (lent_num != 0)
    within_30 = (violation_last_bag == 0) & has_marks & (lent_num != 0)
    within_30_40 = (violation_last_bag >= 1) & (violation_last_bag <= 10) & has_marks & (lent_num != 0)
    over_40 = (violation_last_bag > 10) & (lent_num != 0) & has_marks

    return pd.Series(
        np.select(
            [incorrect, within_30, within_30_40, over_40],
            [
                "Некорректно проставлены отметки",
                "Выдача до 30 минут",
                "Выдача от 30 до 40 минут",
                "Выдача более 40 минут",
            ],
            default="Не определено",
        ),
        index=df.index,
    )


def read_weekly_excel(file_obj: BytesIO) -> pd.DataFrame:
    """Читает выгрузку BI МАВ за произвольный период. Не зависит от имени
    файла — важна только структура (8 строк шапки, фиксированный набор
    колонок), как в исходной выгрузке."""
    df = pd.read_excel(file_obj, skiprows=HEADER_ROWS_TO_SKIP, header=None)
    df = df.iloc[:, : len(COLUMN_NAMES)]
    df.columns = COLUMN_NAMES

    df["date"] = pd.to_datetime(df["date"], format="%d.%m.%y")
    df["mc_arrive"] = df["mc_arrive"].fillna(-1)
    df["time_end_lenta"] = df["time_end_lenta"].fillna(-1)
    df["lent_num"] = df["lent_num"].fillna(0)
    df["violation_last_bag"] = df["violation_last_bag"].fillna(0)

    df["company"] = assign_airlines(df["flight"])
    df["bag_status"] = calculate_baggage_status(df)
    return df


def merge_with_master(df_master: pd.DataFrame, df_new: pd.DataFrame) -> pd.DataFrame:
    combined = pd.concat([df_master, df_new], ignore_index=True)
    combined["date"] = pd.to_datetime(combined["date"])
    combined = combined.drop_duplicates(["date", "flight", "mc"])
    return combined


def derive_datalens(df_master: pd.DataFrame) -> pd.DataFrame:
    return df_master[DATALENS_COLUMNS]


def empty_master() -> pd.DataFrame:
    return pd.DataFrame(columns=COLUMN_NAMES + ["company", "bag_status"])

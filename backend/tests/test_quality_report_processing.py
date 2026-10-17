"""Характеризационные тесты для app/modules/quality_report/processing.py.

Тесты фиксируют ТЕКУЩЕЕ поведение на маленьких синтетических данных.
Спорные места помечены `FLAG (for human review)` и НЕ исправлены.
"""

from io import BytesIO

import pandas as pd

from app.modules.quality_report import processing as qr
from tests.helpers import make_xlsx

T = pd.Timestamp
JAN = (T("2026-01-01"), T("2026-01-31"))
JAN_FEB = (T("2026-01-01"), T("2026-02-04"))


def _violations(rows):
    """Таблица в форме, которую отдаёт read_violations_file (после нормализации)."""
    cols = ["date", "category", "subcategory", "reason", "description",
            "executor", "department", "conclusion", "place", "tail_number"]
    df = pd.DataFrame(rows, columns=cols)
    df["date"] = pd.to_datetime(df["date"])
    return df


# ---------------------------------------------------------------------------
# _canonicalize_values (через обёртки для агентов и описаний)
# ---------------------------------------------------------------------------

def test_canonicalize_agent_names_merges_case_spaces_and_typos():
    names = pd.Series(
        ["Петров Пётр"] * 3
        + ["петров пётр"]
        + ["Петров  Пётр"]        # двойной пробел -> после _clean_agent_name одинаково,
                                   # здесь проверяем уже очищенные значения
        + ["Сидоров"] * 2
        + ["Сидорова"]           # опечатка в окончании
        + ["Козлов Игорь"]        # ни с кем не похож
    )
    mapping = qr._canonicalize_agent_names(names)
    assert mapping["петров пётр"] == "Петров Пётр"
    assert mapping["Петров  Пётр"] == "Петров Пётр"
    assert mapping["Сидорова"] == "Сидоров"
    assert mapping["Козлов Игорь"] == "Козлов Игорь"


def test_canonicalize_agent_names_is_order_sensitive_to_candidate_counts():
    # Канон — самый частый вариант. При равенстве счётчиков побеждает
    # первый встреченный (поведение max()).
    names = pd.Series(["Иванов Иван"] * 2 + ["иванов иван"])
    assert qr._canonicalize_agent_names(names) == {
        "Иванов Иван": "Иванов Иван",
        "иванов иван": "Иванов Иван",
    }


def test_canonicalize_descriptions_ignores_punctuation_and_case():
    descs = pd.Series(
        ["Багаж не принят, рейс 123."] * 1
        + ["багаж не принят рейс 123"] * 2   # самый частый вариант -> канон
        + ["Опоздание на посадку"]
        + ["Опоздание на посадку!!"]
        + ["Опоздание на посадку в автобус"]  # другая фраза — не сливается
    )
    mapping = qr._canonicalize_descriptions(descs)
    assert mapping["Багаж не принят, рейс 123."] == "багаж не принят рейс 123"
    assert mapping["Опоздание на посадку!!"] == "Опоздание на посадку"
    assert mapping["Опоздание на посадку в автобус"] == "Опоздание на посадку в автобус"


# ---------------------------------------------------------------------------
# LIR/СЗВ reader + tables 6, 6.1
# ---------------------------------------------------------------------------

# Даты в dd.mm.yyyy: читатель LIR парсит с dayfirst=True, поэтому ISO-строки
# ("2026-01-05") переставляются местами — см. test_lir_iso_string_dates_are_day_first_swapped.
LIR_ROWS = pd.DataFrame({
    "Дата": ["05.01.2026", "06.01.2026", "20.01.2026", "03.02.2026", "04.02.2026"],
    "ФИО Агента": ["Иванов Иван", "Иванов  Иван", "иванов иван", "Петров", None],
    "Описание причины замечания": ["без замечаний", "Опоздание", "Нарушение", None, "Нарушение"],
    "№ рейса": ["SU1", "SU2", "SU3", None, None],
})


def _lir():
    return qr.read_lir_szv_file(BytesIO(make_xlsx({"LIR СЗВ 2026": LIR_ROWS})))


def test_lir_reader_canonicalizes_agents_and_flags_violations():
    df = _lir()
    # Строки без ФИО остаются в таблице (agent == NaN)
    assert len(df) == 5
    assert df["agent"].tolist()[:3] == ["Иванов Иван", "Иванов Иван", "Иванов Иван"]
    assert pd.isna(df["agent"].iloc[4])
    # «без замечаний» и пустое описание — оба не нарушение
    assert df["has_violation"].tolist() == [False, True, True, False, True]


def test_lir_iso_string_dates_are_parsed_correctly():
    # read_lir_szv_file парсит ISO-строки («2026-01-05») без перестановки
    # дня/месяца — _parse_date_dayfirst_safe распознаёт однозначный ISO-вид
    # и не применяет к нему dayfirst=True (который нужен только для дат
    # вида «05.01.2026»). Реальные excel-даты (не текст) не затронуты.
    iso = pd.DataFrame({
        "Дата": ["2026-01-05", "2026-01-20"],
        "ФИО Агента": ["Иванов", "Иванов"],
        "Описание причины замечания": ["Нарушение", "Нарушение"],
    })
    df = qr.read_lir_szv_file(BytesIO(make_xlsx({"LIR СЗВ 2026": iso})))
    assert df["date"].tolist() == [T("2026-01-05"), T("2026-01-20")]


def test_lir_empty_reason_does_not_count_as_violation():
    # Пустая/NaN «Описание причины замечания» — это отсутствие записи, а не
    # нарушение; has_violation=False, как и для явного «без замечаний».
    df = _lir()
    assert bool(df.loc[3, "has_violation"]) is False
    assert df.loc[3, "reason_description"] == ""


def test_build_lir_szv_table_month_counts_checks_and_violations():
    df = _lir()
    rows = qr.build_lir_szv_table(df, *JAN, "month")
    assert rows == [{"Период": "Январь 2026", "Кол-во проверок": 3, "Кол-во замечаний": 2}]


def test_build_lir_szv_table_quarter_spans_whole_period():
    df = _lir()
    rows = qr.build_lir_szv_table(df, *JAN_FEB, "quarter")
    assert rows == [{"Период": "1 квартал 2026", "Кол-во проверок": 5, "Кол-во замечаний": 3}]


def test_build_lir_szv_employee_detail_formats_flight_and_date():
    df = _lir()
    rows = qr.build_lir_szv_employee_detail(df, *JAN_FEB, "month")
    # Сортировка по убыванию количества; агент без ФИО не попадает в таблицу.
    # У Петрова единственная запись (03.02.2026) — пустое описание, с фиксом
    # не считается нарушением, поэтому Петров вообще не попадает в таблицу.
    assert rows == [
        {"ФИО Агента": "Иванов Иван", "Январь 2026": "2 (SU2 06.01.2026; SU3 20.01.2026)",
         "Февраль 2026": 0},
    ]


def test_build_lir_szv_top_employees_marks_in_period():
    # Аналогично: у Петрова после фикса пустого описания не остаётся ни
    # одного нарушения за всю историю файла, поэтому он не попадает в топ.
    df = _lir()
    rows = qr.build_lir_szv_top_employees(df, *JAN)
    assert rows == [
        {"ФИО Агента": "Иванов Иван", "Кол-во нарушений": 2, "За выбранный период": "❗"},
    ]


# ---------------------------------------------------------------------------
# Period buckets
# ---------------------------------------------------------------------------

def test_week_buckets_split_period_on_calendar_weeks_from_start():
    assert qr.generate_buckets(T("2026-06-08"), T("2026-06-21"), "week") == [
        (T("2026-06-08"), T("2026-06-14")),
        (T("2026-06-15"), T("2026-06-21")),
    ]


def test_month_quarter_year_buckets_clip_partial_periods():
    assert qr.generate_buckets(T("2026-01-15"), T("2026-03-02"), "month") == [
        (T("2026-01-15"), T("2026-01-31")),
        (T("2026-02-01"), T("2026-02-28")),
        (T("2026-03-01"), T("2026-03-02")),
    ]
    assert qr.generate_buckets(T("2026-02-10"), T("2026-08-03"), "quarter") == [
        (T("2026-02-10"), T("2026-03-31")),
        (T("2026-04-01"), T("2026-06-30")),
        (T("2026-07-01"), T("2026-08-03")),
    ]
    assert qr.generate_buckets(T("2025-06-01"), T("2026-02-03"), "year") == [
        (T("2025-06-01"), T("2025-12-31")),
        (T("2026-01-01"), T("2026-02-03")),
    ]


# ---------------------------------------------------------------------------
# Table 2: installation reason classification
# ---------------------------------------------------------------------------

def test_classify_reason_maps_known_phrases():
    assert qr._classify_reason("Несвоевременное торможение КВС") == qr.REASON_KVS_BRAKING
    assert qr._classify_reason("Невозможно оценить (вне ракурса СОК)") == qr.REASON_OUT_OF_VIEW
    assert qr._classify_reason("Вина АООПО") == qr.REASON_AOOPO
    assert qr._classify_reason("Что-то непонятное") == qr.REASON_AOOPO  # по умолчанию
    assert qr._classify_reason(None) is None


def test_classify_reason_substring_sok_false_positive():
    # FLAG (for human review): проверка «сок» — подстрока, поэтому любое слово,
    # где она встречается («высокая», «соки»), уходит в «вне ракурса».
    assert qr._classify_reason("Высокая скорость") == qr.REASON_OUT_OF_VIEW


def test_installation_table_counts_by_reason_bucket_per_month():
    def row(date, sub, reason):
        return {"date": T(date), "category": qr.INSTALLATION_CATEGORY, "subcategory": sub,
                "reason": reason, "description": "", "executor": "", "department": "",
                "conclusion": "с виной"}

    df = pd.DataFrame([
        row("2026-01-05", qr.INSTALLATION_SUBCATEGORY, "Несвоевременное торможение КВС"),
        row("2026-01-06", qr.INSTALLATION_SUBCATEGORY, "Вина АООПО"),
        row("2026-01-07", qr.INSTALLATION_SUBCATEGORY, "Прочее"),        # -> AOOPO
        row("2026-01-08", "Другая подкатегория", "Вина АООПО"),          # мимо
        row("2026-02-01", qr.INSTALLATION_SUBCATEGORY, "Невозможно оценить (вне ракурса СОК)"),
    ])
    rows = qr.build_installation_table(df, *JAN_FEB, "month")
    assert rows == [
        {"Период": "Январь 2026", qr.REASON_KVS_BRAKING: 1,
         qr.REASON_OUT_OF_VIEW: 0, qr.REASON_AOOPO: 2},
        {"Период": "Февраль 2026", qr.REASON_KVS_BRAKING: 0,
         qr.REASON_OUT_OF_VIEW: 1, qr.REASON_AOOPO: 0},
    ]


# ---------------------------------------------------------------------------
# Tables 3/4: monitoring (RPO / ФО и СИЗ) with NOT_UPLOADED handling
# ---------------------------------------------------------------------------

def test_monitoring_table_counts_checks_and_complaints_with_missing_sources():
    perron = _violations([
        ["2026-01-05", "x", qr.RPO_SUBCATEGORY, "", "", "", "", "с виной", "", ""],
        ["2026-01-06", "x", qr.RPO_SUBCATEGORY, "", "", "", "", "без вины", "", ""],
        ["2026-02-01", "x", qr.RPO_SUBCATEGORY, "", "", "", "", "с виной", "", ""],
        ["2026-02-02", "x", "Другое", "", "", "", "", "с виной", "", ""],
    ])
    checks = pd.DataFrame({"date": pd.to_datetime(["2026-01-02", "2026-01-03"])})

    rows = qr.build_monitoring_table(checks, perron, qr._rpo_complaints_filter, *JAN_FEB, "month")
    assert rows == [
        {"Период": "Январь 2026", "Кол-во проверок": 2, "Кол-во замечаний": 1},
        {"Период": "Февраль 2026", "Кол-во проверок": 0, "Кол-во замечаний": 1},
    ]

    missing = qr.build_monitoring_table(None, None, qr._rpo_complaints_filter, *JAN, "month")
    assert missing == [{"Период": "Январь 2026", "Кол-во проверок": qr.NOT_UPLOADED,
                        "Кол-во замечаний": qr.NOT_UPLOADED}]


# ---------------------------------------------------------------------------
# Tables 7-10: PAB checks vs AVK violations
# ---------------------------------------------------------------------------

def test_rk_table_counts_fault_or_blank_conclusion_and_unique_stands():
    avk = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]),
        "conclusion": ["с виной", None, "без вины", "с виной"],
        "category": ["Регистрация"] * 4,
        "subcategory": [qr.RK_VIOLATION_SUBCATEGORY, qr.RK_VIOLATION_SUBCATEGORY,
                        qr.RK_VIOLATION_SUBCATEGORY, "Другая"],
        "department": [""] * 4, "executor": [""] * 4, "description": [""] * 4,
    })
    pab = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-05", "2026-01-05", "2026-01-06", "2026-01-07"]),
        "stand": ["1", "1", None, "2"],
    })
    rows = qr.build_rk_violations_table(avk, pab, *JAN, "month")
    assert rows == [{
        "Период": "Январь 2026",
        "Кол-во проверок": 4,              # все строки листа проверок
        "Кол-во нарушений": 2,             # «с виной» + пусто (без «без вины» и без подкатегории)
        "": "",                            # пустая колонка для ручных заметок
        "Кол-во уникальных стоек": 2,      # «1» и «2»; пустая стойка не считается
    }]


def test_pab_tables_mark_missing_sheet_as_not_uploaded():
    rows = qr.build_fo_ethics_table(None, None, *JAN, "month")
    assert rows[0]["Кол-во проверок"] == qr.NOT_UPLOADED
    assert rows[0]["Кол-во нарушений"] == qr.NOT_UPLOADED
    assert rows[0]["Кол-во уникальных стоек"] == qr.NOT_UPLOADED


def test_fo_ethics_subcategory_table_canonical_descriptions_and_blank_counts():
    avk = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08",
                                "2026-01-09", "2026-01-10"]),
        "category": [qr.FO_ETHICS_CATEGORY] * 6,
        "subcategory": ["Фразеология", "Фразеология", "Фразеология", "Фразеология",
                        "Внешний вид", "Внешний вид"],
        "conclusion": ["с виной", "с виной", None, "без вины", "без вины", "без вины"],
        "description": ["Использовал жаргон!", "Использовал жаргон.", "Использовал жаргон.",
                        "Не по форме", "Форма", "Форма"],
        "executor": [""] * 6, "department": [""] * 6,
    })
    rows = qr.build_fo_ethics_subcategory_table(avk, *JAN)
    assert rows == [
        {"Категория нарушения": "Внешний вид", "Кол-во случаев": 0, "Типовые нарушения": ""},
        {"Категория нарушения": "Фразеология", "Кол-во случаев": 3,
         "Типовые нарушения": "Использовал жаргон."},
    ]


# ---------------------------------------------------------------------------
# Safety table place formatting
# ---------------------------------------------------------------------------

def test_format_place_normalizes_float_stand_numbers_and_tail():
    assert qr._format_place("12.0", "RA-123") == "МС12 RA-123"
    assert qr._format_place("12", None) == "МС12"
    assert qr._format_place("Перрон", None) == "Перрон"
    assert qr._format_place(None, "RA-2") == "RA-2"
    assert qr._format_place(None, None) == ""


def test_build_quality_tables_contract_with_no_inputs():
    tables = qr.build_quality_tables(
        None, None, None, None, None, None, None, None, None, *JAN, "month",
    )
    ids = [t["id"] for t in tables]
    assert ids[0] == "alcohol"
    assert "installation" in ids
    assert "rpo_checks" in ids
    # Без входных файлов все таблицы помечены «не загружен» или пустые
    # Отсутствующий источник помечен либо на уровне таблицы (message), либо
    # в каждой ячейке (таблицы с мониторингом и PAB). Данных быть не должно.
    for table in tables:
        if table.get("message") == qr.NOT_UPLOADED:
            assert table["rows"] == [], table["id"]
            continue
        for row in table["rows"]:
            for key, value in row.items():
                # "" — пустая ручная колонка таблиц 7-10, её не проверяем
                if key not in ("Период", ""):
                    assert value == qr.NOT_UPLOADED, (table["id"], key, value)

"""Характеризационные тесты для app/modules/month_report/processing.py.

Тесты фиксируют ТЕКУЩЕЕ поведение расчётов на маленьких синтетических
таблицах. Если при рефакторинге какая-то цифра изменилась — тест упадёт.
Места, где поведение выглядит спорным, помечены комментарием
`FLAG (for human review)` и НЕ исправлены.
"""

import pandas as pd

from app.modules.month_report import processing as mr

T = pd.Timestamp
JAN = (T("2026-01-01"), T("2026-01-31"))
JAN_FEB = (T("2026-01-01"), T("2026-02-28"))


def _avk(rows):
    """AVK-таблица в форме, которую отдаёт read_avk_full."""
    df = pd.DataFrame(rows, columns=["date", "conclusion", "department", "category",
                                     "subcategory", "executor"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def _perron(rows):
    """Перронная таблица в форме, которую отдаёт _dedup_and_shape_perron."""
    df = pd.DataFrame(rows, columns=["date", "conclusion", "department", "category",
                                     "subcategory", "executor"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def _appeals(rows):
    df = pd.DataFrame(rows, columns=["date", "result", "appeal_type", "status",
                                     "requestor", "requestor_detail",
                                     "claimed_amount", "accepted_amount"])
    df["date"] = pd.to_datetime(df["date"])
    df["responsible_services"] = [frozenset()] * len(df)
    return df


# ---------------------------------------------------------------------------
# Fuzzy employee-name grouping (_group_employees)
# ---------------------------------------------------------------------------

def test_group_employees_merges_case_whitespace_and_typos():
    counts = pd.Series({
        "Петров Пётр": 5,
        "Петров Петр": 2,        # ё -> е, похоже по строке
        "Сидоров Сергей": 4,
        "Сидоров Сергей ": 1,    # хвостовой пробел — та же нормализованная строка
        "Козлов Игорь": 3,
        "Козлова Игоря": 1,      # опечатка в окончании
        "Иванов": 1,             # ни с кем не похож
    })
    assert mr._group_employees(counts) == {
        "Петров Пётр": "Петров Пётр",
        "Петров Петр": "Петров Пётр",
        "Сидоров Сергей": "Сидоров Сергей",
        "Сидоров Сергей ": "Сидоров Сергей",
        "Козлов Игорь": "Козлов Игорь",
        "Козлова Игоря": "Козлов Игорь",
        "Иванов": "Иванов",
    }


def test_group_employees_canonical_name_is_most_frequent_variant():
    counts = pd.Series({"Смирнова А.": 1, "Смирнова А": 7})
    mapping = mr._group_employees(counts)
    assert mapping == {"Смирнова А.": "Смирнова А", "Смирнова А": "Смирнова А"}


def test_group_employees_higher_threshold_keeps_near_names_apart():
    counts = pd.Series({"Петров Пётр": 5, "Петров Петр": 2, "Козлов Игорь": 3, "Козлова Игоря": 1})
    mapping = mr._group_employees(counts, threshold=0.95)
    assert mapping["Петров Петр"] == "Петров Петр"
    assert mapping["Козлова Игоря"] == "Козлова Игоря"


def test_group_employees_empty_name_is_left_alone():
    counts = pd.Series({"": 2, "Иванов": 1})
    assert mr._group_employees(counts) == {"": "", "Иванов": "Иванов"}


# ---------------------------------------------------------------------------
# Table 2: violations + appeals by month
# ---------------------------------------------------------------------------

def test_violations_appeals_monthly_counts_and_exclusions():
    perron = _perron([
        ["2026-01-05", "с виной", "ДСТ", "Регистрация", "", "e1"],
        ["2026-01-06", "без вины", "ДСТ", "Регистрация", "", "e2"],
        ["2026-02-01", "с виной", "ДСТ", "Посадка", "", "e3"],
        ["2026-02-03", "с виной", "ДСТ", "Посадка", "", "e4"],
        ["2026-02-04", "с виной", "ДСТ", "Посадка", "", "e5"],
    ])
    avk = _avk([
        ["2026-01-10", "с виной", "ДСТ", "Регистрация", "", "a"],
        ["2026-01-10", "с виной", "ДСТ", "Регистрация", "", "a"],
        ["2026-01-10", "с виной", "ДСТ", "Регистрация", "", "a"],
        ["2026-01-10", "с виной", "ДСТ", "Регистрация", "", "a"],
        ["2026-01-11", "с виной", "ДСТ", "Посадка", "", "b"],
    ])
    appeals = _appeals([
        ["2026-01-03", "Подтверждено", "Жалоба", "Закрыто", "ЮТэйр", "ЮТэйр", 0, 0],
        ["2026-01-04", "Подтверждено", "Благодарность", "Закрыто", "Победа", "Победа", 0, 0],
        ["2026-01-05", "Отказано", "Жалоба", "Отменено", "Победа", "Победа", 0, 0],
        ["2026-01-06", "Подтверждено", "Исходящее", "Закрыто", "Победа", "Победа", 0, 0],
    ])
    rows = mr.build_violations_appeals_table(perron, avk, appeals, *JAN_FEB, "month")
    assert rows == [
        # 1 (перрон) + 5 (АВК) с виной + 3 подтверждённых обращения
        {"Период": "Январь 2026", mr.COL_COMBINED: 9, mr.COL_APPEALS_NO_THANKS: 2},
        # 3 (перрон) с виной, обращений в феврале нет
        {"Период": "Февраль 2026", mr.COL_COMBINED: 3, mr.COL_APPEALS_NO_THANKS: 0},
    ]


def test_violations_appeals_not_uploaded_markers():
    appeals = _appeals([["2026-01-03", "Подтверждено", "Жалоба", "Закрыто", "ЮТэйр", "ЮТэйр", 0, 0]])
    # Ни нарушений, ни обращений — оба отмечены «не загружен»
    none_rows = mr.build_violations_appeals_table(None, None, None, *JAN, "month")
    assert none_rows == [{"Период": "Январь 2026", mr.COL_COMBINED: mr.NOT_UPLOADED,
                          mr.COL_APPEALS_NO_THANKS: mr.NOT_UPLOADED}]
    # Только обращения: сводная колонка считается по обращениям, а не «не загружен»
    only_appeals = mr.build_violations_appeals_table(None, None, appeals, *JAN, "month")
    assert only_appeals == [{"Период": "Январь 2026", mr.COL_COMBINED: 1, mr.COL_APPEALS_NO_THANKS: 1}]


# ---------------------------------------------------------------------------
# Tables 3 and 10: department breakdowns
# ---------------------------------------------------------------------------

def test_avk_departments_ignores_nan_and_sorts_desc_with_total():
    avk = _avk([
        ["2026-01-10", "с виной", "ДСТ", "x", "", ""],
        ["2026-01-11", "с виной", "ДСТ", "x", "", ""],
        ["2026-01-12", "с виной", "ДСТ", "x", "", ""],
        ["2026-01-13", "с виной", "Цех", "x", "", ""],
        ["2026-01-14", "с виной", "nan", "x", "", ""],     # строковый 'nan' отбрасывается
        ["2026-01-15", "без вины", "Цех", "x", "", ""],    # не «с виной»
    ])
    assert mr.build_avk_departments_table(avk, *JAN) == [
        {"Служба": "ДСТ", "Кол-во нарушений": 3},
        {"Служба": "Цех", "Кол-во нарушений": 1},
        {"Служба": "ИТОГО", "Кол-во нарушений": 4},
    ]


def test_perron_departments_merges_sst_and_spt_into_dst():
    perron = _perron([
        ["2026-01-05", "с виной", "ССТ", "Регистрация", "", ""],
        ["2026-01-06", "с виной", "СПТ", "Регистрация", "", ""],
        ["2026-01-07", "с виной", "ДСТ", "Регистрация", "", ""],
        ["2026-01-08", "с виной", "ОПЕР", "Регистрация", "", ""],
    ])
    assert mr.build_perron_departments_table(perron, *JAN) == [
        {"Служба": "ДСТ", "Кол-во нарушений": 3},
        {"Служба": "ОПЕР", "Кол-во нарушений": 1},
        {"Служба": "ИТОГО", "Кол-во нарушений": 4},
    ]


def test_perron_departments_tdb_categories_come_from_tdb_frame():
    tdb_cat = "Техника безопасности охраны труда"
    perron = _perron([
        ["2026-01-05", "с виной", "ОПЕР", tdb_cat, "", "e1"],     # заменяется версией из tdb
        ["2026-01-06", "с виной", "ДСТ", "Регистрация", "", "e2"],  # стандартная категория
    ])
    perron_tdb = _perron([
        ["2026-01-05", "с виной", "ДСТ", tdb_cat, "", "e1"],
        ["2026-01-05", "с виной", "ДСТ", tdb_cat, "", "e9"],       # второй исполнитель, тот же день
    ])
    rows = mr.build_perron_departments_table(perron, *JAN, df_perron_tdb=perron_tdb)
    assert rows == [
        {"Служба": "ДСТ", "Кол-во нарушений": 3},
        {"Служба": "ИТОГО", "Кол-во нарушений": 3},
    ]


# ---------------------------------------------------------------------------
# Table 4: AVK categories (normalized matching)
# ---------------------------------------------------------------------------

def test_avk_categories_normalized_matching_and_group_order():
    avk = _avk([
        ["2026-01-05", "с виной", "x", "Регистрация", "", ""],
        ["2026-01-06", "с виной", "x", "регистрация ", "", ""],        # регистр/пробел
        ["2026-01-07", "с виной", "x", "Нарушения ФО/этики", "", ""],  # «/» как в списке
        ["2026-01-08", "с виной", "x", "Нарушение ФО,этики", "", ""],  # «,» без пробела
        ["2026-01-09", "с виной", "x", "Заполнение_документации", "", ""],  # «_» -> пробел
        ["2026-01-10", "с виной", "x", "Неизвестная категория", "", ""],    # не попадает никуда
        ["2026-01-11", "без вины", "x", "Посадка", "", ""],                 # не «с виной»
    ])
    rows = mr.build_avk_categories_table(avk, *JAN)
    got = {r["Категория"]: r["Кол-во нарушений"] for r in rows}
    assert got["Регистрация"] == 2
    assert got["Нарушение ФО/этики"] == 2
    assert got["Трудовая дисциплина и безопасность"] == 1
    assert got["Посадка"] == 0
    # Порядок строк — порядок _CATEGORY_GROUPS
    assert [r["Категория"] for r in rows] == [label for label, _ in mr._CATEGORY_GROUPS]


def test_avk_categories_has_no_total_row_despite_docstring():
    # FLAG (for human review): docstring build_avk_categories_table говорит
    # «Bottom row: ИТОГО», но функция ИТОГО не добавляет (total считается и
    # не используется). Тест фиксирует текущее поведение — строки ИТОГО нет.
    avk = _avk([["2026-01-05", "с виной", "x", "Регистрация", "", ""]])
    labels = [r["Категория"] for r in mr.build_avk_categories_table(avk, *JAN)]
    assert "ИТОГО" not in labels


# ---------------------------------------------------------------------------
# Table 9: employees (fuzzy-merged) with previous-month context
# ---------------------------------------------------------------------------

def test_avk_employees_threshold_merge_departments_and_prev_months():
    avk = _avk([
        # текущий месяц (январь 2026)
        ["2026-01-05", "с виной", "ДСТ", "x", "", "Иванов Иван"],
        ["2026-01-06", "с виной", "ДСТ", "x", "", "Иванов Иван"],
        ["2026-01-07", "с виной", "ДСТ", "x", "", "Иванов  иван"],   # схлопывается в «Иванов Иван»
        ["2026-01-08", "с виной", "Цех", "x", "", "Сидоров"],
        ["2026-01-09", "с виной", "Цех", "x", "", "Сидоров"],
        ["2026-01-10", "с виной", "Цех", "x", "", "Сидоров"],
        ["2026-01-11", "с виной", "ДСТ", "x", "", "Петров"],         # 2 < порога в 3
        ["2026-01-12", "с виной", "ДСТ", "x", "", "Петров"],
        # декабрь 2025 (предыдущий месяц) и ноябрь 2025
        ["2025-12-03", "с виной", "ДСТ", "x", "", "Иванов Иван"],
        ["2025-11-03", "с виной", "ДСТ", "x", "", "Иванов Иван"],
        ["2025-11-04", "с виной", "ДСТ", "x", "", "Иванов Иван"],
    ])
    rows, columns = mr.build_avk_employees_table(avk, *JAN)
    assert columns == ["Сотрудник", "Подразделение",
                       mr._COL_2M, mr._COL_1M, mr._COL_CUR]
    # Сортировка по подразделению (ДСТ < Цех), затем по убыванию количества
    assert rows == [
        {"Сотрудник": "Иванов Иван", "Подразделение": "ДСТ",
         mr._COL_2M: 2, mr._COL_1M: 1, mr._COL_CUR: 3},
        {"Сотрудник": "Сидоров", "Подразделение": "Цех",
         mr._COL_2M: 0, mr._COL_1M: 0, mr._COL_CUR: 3},
    ]


def test_prev_month_range_wraps_year_boundary():
    assert mr._prev_month_range(T("2026-01-01"), 1) == (T("2025-12-01"), T("2025-12-31"))
    assert mr._prev_month_range(T("2026-01-15"), 2) == (T("2025-11-01"), T("2025-11-30"))


# ---------------------------------------------------------------------------
# Tables 11-13: perron categories
# ---------------------------------------------------------------------------

def test_avs_catch_all_bucket_is_never_filled():
    # FLAG (for human review): в build_avs_table строки предварительно
    # фильтруются по _AVS_FILE_VALUES, поэтому ветка «Другое» (catch-all)
    # недостижима — строка «Другое» всегда 0. Тест фиксирует это поведение.
    perron = _perron([
        ["2026-01-05", "с виной", "ДСТ", "Внешний осмотр ВС", "", ""],
        ["2026-01-06", "с виной", "ДСТ", "Что-то совсем другое", "", ""],
    ])
    result = mr.build_avs_table(perron, *JAN)
    counts = {r["Категория"]: r["Кол-во нарушений"] for r in result["rows"]}
    assert counts["Внешний осмотр ВС"] == 1
    assert counts["Другое"] == 0


def test_nvz_table_groups_by_category_with_department_details():
    perron = _perron([
        ["2026-01-05", "с виной", "ДСТ", "Взаимодействие между подразделениями", "", ""],
        ["2026-01-06", "с виной", "ССТ", "Взаимодействие между подразделениями", "", ""],
        ["2026-01-07", "с виной", "ОПЕР", "Своевременность назначения и выполнения задач", "", ""],
        ["2026-01-08", "без вины", "ОПЕР", "Своевременность назначения и выполнения задач", "", ""],
    ])
    result = mr.build_nvz_table(perron, *JAN)
    groups = {g["Категория"]: g for g in result["row_groups"]}
    assert groups["Взаимодействие между подразделениями"]["Кол-во нарушений"] == 2
    assert groups["Взаимодействие между подразделениями"]["details"] == [
        {"Служба": "ДСТ", "Кол-во нарушений (служба)": 2},  # ССТ слит в ДСТ
    ]
    assert groups["Своевременность назначения и выполнения задач"]["Кол-во нарушений"] == 1


# ---------------------------------------------------------------------------
# Tables 18-20: appeals
# ---------------------------------------------------------------------------

def test_appeals_type_filters_cancelled_and_internal_requestors():
    appeals = _appeals([
        ["2026-01-03", "Подтверждено", "Жалоба", "Закрыто", "ЮТэйр", "ЮТэйр", 0, 0],
        ["2026-01-04", "Подтверждено", "Благодарность", "Закрыто", "UTG", "", 0, 0],  # UTG -> мимо
        ["2026-01-05", "Отказано", "Жалоба", "Отменено", "Победа", "", 0, 0],        # отменено
        ["2026-01-06", "Подтверждено", "Претензия", "Закрыто", "Сотрудник", "", 0, 0],  # мимо
        ["2026-01-07", "Подтверждено", "Претензия", "Закрыто", "Победа", "", 0, 0],
    ])
    result = mr.build_appeals_type_table(appeals, *JAN)
    counts = {r["Тип обращения"]: r["Кол-во"] for r in result["rows"]}
    assert counts["Жалоба"] == 1
    assert counts["Претензия"] == 1
    assert counts["Благодарность"] == 0
    assert list(counts) == mr._APPEAL_TYPE_GROUPS


def test_requestors_excludes_excluded_types_and_counts_detail():
    appeals = _appeals([
        ["2026-01-03", "Подтверждено", "Жалоба", "Закрыто", "ЮТэйр", "ЮТэйр", 0, 0],
        ["2026-01-04", "Подтверждено", "Благодарность", "Закрыто", "ЮТэйр", "Победа", 0, 0],  # мимо
        ["2026-01-05", "Подтверждено", "Жалоба", "Отменено", "ЮТэйр", "QR", 0, 0],          # мимо
        ["2026-01-06", "Подтверждено", "Жалоба", "Закрыто", "ЮТэйр", "Азимут", 0, 0],
    ])
    result = mr.build_requestors_table(appeals, *JAN)
    counts = {r["Заявитель"]: r["Кол-во"] for r in result["rows"]}
    assert counts == {"ЮТэйр": 1, "QR": 0, "Победа": 0, "Россия": 0,
                      "Обратная связь": 0, "Uzbekistan Airways": 0, "Азимут": 1}


def test_claims_sums_amounts_with_filters_and_rounding():
    appeals = _appeals([
        ["2026-01-03", "Подтверждено", "Жалоба", "Закрыто", "ЮТэйр", "", 100.25, 20.10],
        ["2026-01-05", "Подтверждено", "Жалоба", "Закрыто", "Победа", "", 50.5, 0.0],
        ["2026-01-06", "Подтверждено", "Жалоба", "Отменено", "Победа", "", 999.0, 999.0],
        ["2026-01-07", "Подтверждено", "Жалоба", "Закрыто", "UTG", "", 999.0, 999.0],
    ])
    result = mr.build_claims_table(appeals, *JAN)
    assert result["rows"] == [{"Заявленная сумма": 150.75, "Принятая сумма": 20.1}]


# ---------------------------------------------------------------------------
# Period helpers and the top-level contract
# ---------------------------------------------------------------------------

def test_month_buckets_start_at_calendar_month_start_not_requested_start():
    # FLAG (for human review): первый интервал начинается с 1-го числа месяца,
    # а не с start (_month_buckets: start.replace(day=1)). Конец обрезается по end.
    assert mr._month_buckets(T("2026-01-15"), T("2026-03-02")) == [
        (T("2026-01-01"), T("2026-01-31")),
        (T("2026-02-01"), T("2026-02-28")),
        (T("2026-03-01"), T("2026-03-02")),
    ]


def test_violations_appeals_counts_days_before_requested_start_in_first_bucket():
    # FLAG (for human review): следствие предыдущего теста — в таблице 2
    # (единственной, которая использует бакеты) нарушения за 1–14 января
    # попадают в «Январь», хотя период начинается 15 января. Таблицы 3–20
    # используют start/end напрямую и этой ошибки не имеют.
    perron = _perron([
        ["2026-01-05", "с виной", "ДСТ", "Регистрация", "", "e1"],   # до начала периода
        ["2026-01-20", "с виной", "ДСТ", "Регистрация", "", "e2"],
    ])
    rows = mr.build_violations_appeals_table(perron, None, None, T("2026-01-15"), T("2026-01-31"), "month")
    assert rows == [{"Период": "Январь 2026", mr.COL_COMBINED: 2, mr.COL_APPEALS_NO_THANKS: mr.NOT_UPLOADED}]


def test_quarter_and_year_buckets_also_start_on_period_boundary():
    # FLAG (for human review): то же для кварталов и годов — первый интервал
    # начинается с 1-го числа квартала / 1 января, а не с start.
    assert mr._quarter_buckets(T("2026-02-10"), T("2026-08-03")) == [
        (T("2026-01-01"), T("2026-03-31")),
        (T("2026-04-01"), T("2026-06-30")),
        (T("2026-07-01"), T("2026-08-03")),
    ]
    assert mr._year_buckets(T("2025-06-01"), T("2026-02-03")) == [
        (T("2025-01-01"), T("2025-12-31")),
        (T("2026-01-01"), T("2026-02-03")),
    ]


def test_build_month_tables_contract_with_no_inputs():
    tables = mr.build_month_tables(None, None, None, None, *JAN)
    assert [t["id"] for t in tables] == [
        "production_indicators", "violations_appeals", "avk_departments", "avk_categories",
        "registration_subcat", "baggage_subcat", "fo_ethics_subcat", "boarding_subcat",
        "avk_employees", "avk_repeat_employees",
        "perron_departments", "perron_categories",
        "avs_breakdown", "nvz_breakdown", "ets_breakdown", "tdb_breakdown",
        "dkv_breakdown", "ob_breakdown",
        "perron_employees", "perron_repeat_employees",
        "appeals_type", "requestors", "claims",
    ]
    # Всё, что не загружено, помечено одинаково
    not_uploaded = [t for t in tables if t.get("message") == mr.NOT_UPLOADED]
    assert len(not_uploaded) == len(tables) - 1  # все, кроме violations_appeals
    violations = tables[1]
    assert violations["rows"][0][mr.COL_COMBINED] == mr.NOT_UPLOADED


def test_production_table_marks_missing_metrics():
    data = {"Рейсы": 10, "Пассажиры": None, "Багаж": 3}
    assert mr.build_production_table(data) == [
        {"Рейсы": 10, "Пассажиры": mr.NOT_UPLOADED, "Багаж": 3,
         "Груз": mr.NOT_UPLOADED, "Почта": mr.NOT_UPLOADED},
    ]

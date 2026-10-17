"""Характеризационные тесты чистой логики слияния архива baggage_norm
(app/modules/baggage_norm/processing.py: merge_with_master, derive_datalens,
calculate_baggage_status). Сетевых вызовов нет."""

import pandas as pd

from app.modules.baggage_norm import processing as bn

T = pd.Timestamp


def _frame(rows):
    """Минимальный кадр в форме, которую отдаёт read_weekly_excel."""
    df = pd.DataFrame(rows, columns=["date", "flight", "mc", "bag_waight"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def test_merge_into_empty_master_dedups_on_date_flight_mc():
    new = _frame([
        ["2026-01-30", "SU100", "A", 10],
        ["2026-01-30", "SU100", "A", 99],   # тот же ключ -> отбрасывается
        ["2026-01-31", "SU100", "A", 20],
    ])
    out = bn.merge_with_master(bn.empty_master(), new)
    assert len(out) == 2
    assert out["bag_waight"].tolist() == [10, 20]


def test_remerging_the_same_upload_is_idempotent():
    new = _frame([
        ["2026-01-30", "SU100", "A", 10],
        ["2026-01-31", "SU200", "B", 20],
    ])
    once = bn.merge_with_master(bn.empty_master(), new)
    twice = bn.merge_with_master(once, new)
    pd.testing.assert_frame_equal(once, twice)


def test_overlapping_week_adds_only_new_keys_and_keeps_sorted_order():
    master = _frame([
        ["2026-01-29", "SU1", "A", 1],
        ["2026-01-30", "SU2", "B", 2],
    ])
    week = _frame([
        ["2026-01-30", "SU2", "B", 2],   # уже есть
        ["2026-01-31", "SU3", "C", 3],   # новое
    ])
    out = bn.merge_with_master(master, week)
    assert out[["date", "flight", "mc"]].values.tolist() == [
        [T("2026-01-29"), "SU1", "A"],
        [T("2026-01-30"), "SU2", "B"],
        [T("2026-01-31"), "SU3", "C"],
    ]


def test_master_row_wins_over_new_row_with_same_key():
    # FLAG (for human review): при совпадении ключа (date, flight, mc)
    # drop_duplicates оставляет первую строку — из архива. Новая выгрузка
    # с исправленным значением молча игнорируется. Фиксируем как есть.
    master = _frame([["2026-01-30", "SU2", "B", 2]])
    correction = _frame([["2026-01-30", "SU2", "B", 777]])
    out = bn.merge_with_master(master, correction)
    assert out["bag_waight"].tolist() == [2]


def test_master_rows_outside_new_period_are_untouched():
    master = _frame([
        ["2026-01-02", "SU9", "Z", 5],
        ["2026-01-30", "SU2", "B", 2],
    ])
    week = _frame([["2026-01-30", "SU7", "Q", 7]])
    out = bn.merge_with_master(master, week)
    assert len(out) == 3
    assert out.iloc[0]["flight"] == "SU9"


def test_derive_datalens_selects_expected_columns():
    df = pd.DataFrame({
        "date": [T("2026-01-30")], "company": ["Победа"], "bag_status": ["Выдача до 30 минут"],
        "flight": ["PBD1"], "mc": ["A"],
    })
    out = bn.derive_datalens(df)
    assert list(out.columns) == bn.DATALENS_COLUMNS


def test_airline_lookup_uses_first_matching_prefix_in_declaration_order():
    assert bn.get_airline_by_flight("pbd123") == "Победа"           # регистр не важен
    assert bn.get_airline_by_flight("VSV100") == "AJET"             # VSV есть у AJET раньше SCAT
    assert bn.get_airline_by_flight("ZZZ1") == "Не найдено"


def test_baggage_status_buckets():
    df = pd.DataFrame({
        "mc_arrive": [pd.Timestamp("2026-01-30 10:00"), pd.Timestamp("2026-01-30 10:00"), -1],
        "time_end_lenta": [pd.Timestamp("2026-01-30 10:20"), pd.Timestamp("2026-01-30 11:30"), 5],
        "violation_last_bag": [0, 5, 0],
        "lent_num": [1, 1, 1],
    })
    status = bn.calculate_baggage_status(df).tolist()
    assert status == [
        "Выдача до 30 минут",
        "Выдача от 30 до 40 минут",
        "Некорректно проставлены отметки",
    ]

"""Некорректный ввод на трёх эндпоинтах: нет обязательных полей, не тот тип
файла, пустой или битый файл. Ожидаем клиентскую ошибку (400/422) с
понятным текстом, а не 500 с трассировкой.

Где текущее поведение расходится с ожидаемым, стоит TODO-комментарий; сам
роутер при этом НЕ меняется — тест фиксирует, что реально возвращается."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import XLSX_MIME, make_xlsx

# Не поднимаем исключения из эндпоинта: нас интересует HTTP-ответ.
client = TestClient(app, raise_server_exceptions=False)

QR = "/api/quality-report/summary"
MR = "/api/month-report/summary"
BC = "/api/baggage-comments/process"

QR_DATES = {"start_date": "2026-01-01", "end_date": "2026-01-31", "granularity": "month"}
MR_DATES = {"start_date": "2026-01-01", "end_date": "2026-01-31", "granularity": "month"}

PERRON_OK = pd.DataFrame({
    "Дата": ["2026-01-05"],
    "Категория": ["Регистрация"],
    "Заключение": ["с виной"],
    "Подразделение": ["ДСТ"],
    "Описание": ["d"],
    "Исполнитель": ["e"],
})
PERRON_BYTES = make_xlsx({"ТАБЛИЦА": PERRON_OK})
XLSX = ("perron.xlsx", PERRON_BYTES, XLSX_MIME)


def _assert_clean_client_error(response, status: int):
    assert response.status_code == status, response.text
    body = response.text
    assert "Traceback" not in body
    assert "detail" in response.json()


# ---------------------------------------------------------------------------
# /api/quality-report/summary
# ---------------------------------------------------------------------------

def test_quality_missing_required_form_fields_is_422_validation_error():
    # FastAPI отдаёт 422 с перечислением полей, а не 400. Это клиентская
    # ошибка и без трассировки — фиксируем текущий статус.
    response = client.post(QR, data={"granularity": "month"}, files={"perron_file": XLSX})
    assert response.status_code == 422
    fields = {tuple(err["loc"]) for err in response.json()["detail"]}
    assert ("body", "start_date") in fields
    assert ("body", "end_date") in fields


def test_quality_wrong_file_extension_is_400():
    response = client.post(QR, data=QR_DATES, files={"perron_file": ("perron.txt", PERRON_BYTES)})
    _assert_clean_client_error(response, 400)
    assert "ожидается excel-файл" in response.json()["detail"]


def test_quality_start_after_end_is_400():
    response = client.post(QR, data={**QR_DATES, "start_date": "2026-02-01"}, files={"perron_file": XLSX})
    _assert_clean_client_error(response, 400)


def test_quality_unparseable_date_is_400():
    response = client.post(QR, data={**QR_DATES, "start_date": "not-a-date"}, files={"perron_file": XLSX})
    _assert_clean_client_error(response, 400)
    assert "Некорректная дата" in response.json()["detail"]


def test_quality_unknown_granularity_is_400():
    response = client.post(QR, data={**QR_DATES, "granularity": "decade"}, files={"perron_file": XLSX})
    _assert_clean_client_error(response, 400)


def test_quality_empty_start_date_is_silently_accepted_with_200():
    # TODO: should be 400 (пустая дата -> NaT), currently 200 with empty tables.
    # Сам роутер не меняем; фиксируем текущий ответ.
    response = client.post(QR, data={**QR_DATES, "start_date": ""}, files={"perron_file": XLSX})
    assert response.status_code == 200
    assert response.json()["tables"]


@pytest.mark.parametrize("name, payload", [
    ("corrupt bytes", b"PK\x03\x04 not really a zip"),
    ("zero-byte file", b""),
    ("plain text dressed as xlsx", "Дата;Категория\n2026-01-05;x\n".encode("utf-8")),
])
def test_quality_corrupt_or_empty_perron_file_is_400(name, payload):
    response = client.post(QR, data=QR_DATES, files={"perron_file": ("p.xlsx", payload, XLSX_MIME)})
    _assert_clean_client_error(response, 400)
    assert "Не удалось разобрать файл" in response.json()["detail"] or "Excel" in response.json()["detail"], name


def test_quality_missing_required_sheet_is_400():
    wrong_sheet = make_xlsx({"Лист1": PERRON_OK})
    response = client.post(QR, data=QR_DATES, files={"perron_file": ("p.xlsx", wrong_sheet, XLSX_MIME)})
    _assert_clean_client_error(response, 400)
    assert "ТАБЛИЦА" in response.json()["detail"]


def test_quality_missing_required_columns_is_400():
    no_category = make_xlsx({"ТАБЛИЦА": PERRON_OK.drop(columns=["Категория"])})
    response = client.post(QR, data=QR_DATES, files={"perron_file": ("p.xlsx", no_category, XLSX_MIME)})
    _assert_clean_client_error(response, 400)
    assert "Категория" in response.json()["detail"]


@pytest.mark.parametrize("field", ["lir_file", "pab_file", "grh_file"])
def test_quality_corrupt_secondary_files_are_400(field):
    response = client.post(QR, data=QR_DATES, files={field: ("x.xlsx", b"junk", XLSX_MIME)})
    _assert_clean_client_error(response, 400)


# ---------------------------------------------------------------------------
# /api/month-report/summary
# ---------------------------------------------------------------------------

def test_month_missing_required_form_fields_is_422_validation_error():
    response = client.post(MR, data={"granularity": "month"}, files={"perron_file": XLSX})
    assert response.status_code == 422


def test_month_unknown_granularity_is_400():
    response = client.post(MR, data={**MR_DATES, "granularity": "week"}, files={"perron_file": XLSX})
    _assert_clean_client_error(response, 400)
    assert "Неизвестный временной срез" in response.json()["detail"]


def test_month_start_after_end_is_400():
    response = client.post(MR, data={**MR_DATES, "start_date": "2026-03-01"}, files={"perron_file": XLSX})
    _assert_clean_client_error(response, 400)


def test_month_wrong_extension_is_400_but_message_is_double_wrapped():
    # TODO: should be a clean 400 "«Нарушения на перроне» — ожидается excel-файл",
    # currently the HTTPException is raised inside the try block and caught by the
    # generic `except Exception`, so the text becomes "Не удалось разобрать файл: 400: ...".
    response = client.post(MR, data=MR_DATES, files={"perron_file": ("perron.csv", PERRON_BYTES)})
    _assert_clean_client_error(response, 400)
    detail = response.json()["detail"]
    assert detail.startswith("Не удалось разобрать файл: 400:")
    assert "ожидается excel-файл" in detail


@pytest.mark.parametrize("payload", [b"junk", b""])
def test_month_corrupt_or_empty_file_is_400(payload):
    response = client.post(MR, data=MR_DATES, files={"avk_file": ("a.xlsx", payload, XLSX_MIME)})
    _assert_clean_client_error(response, 400)


def test_month_missing_sheet_is_400():
    response = client.post(MR, data=MR_DATES,
                           files={"perron_file": ("p.xlsx", make_xlsx({"Other": PERRON_OK}), XLSX_MIME)})
    _assert_clean_client_error(response, 400)


def test_month_appeals_without_required_columns_is_400():
    appeals = make_xlsx({"Экспорт": pd.DataFrame({"Что-то": ["x"]})})
    response = client.post(MR, data=MR_DATES, files={"appeals_file": ("a.xlsx", appeals, XLSX_MIME)})
    _assert_clean_client_error(response, 400)


def test_month_production_file_without_header_row_is_400():
    prod = make_xlsx({"Производственный отчет": pd.DataFrame({"x": [1]})})
    response = client.post(MR, data=MR_DATES, files={"production_file": ("p.xlsx", prod, XLSX_MIME)})
    _assert_clean_client_error(response, 400)


# ---------------------------------------------------------------------------
# /api/baggage-comments/process
# ---------------------------------------------------------------------------

NORM_CSV = "date,company,bag_status,flight\n2026-01-05,Победа,Выдача до 30 минут,PBD1\n".encode("utf-8")
EVENTS_XLSX = make_xlsx({"Sheet1": pd.DataFrame({
    "Дата рейса": ["05.01.2026"], "Номер рейса": ["PBD 1"], "Комментарий": ["2 м/б"],
})})


def test_baggage_comments_missing_file_field_is_422():
    response = client.post(BC, data={"station": "vko"}, files={"events_file": ("e.xlsx", EVENTS_XLSX, XLSX_MIME)})
    assert response.status_code == 422


def test_baggage_comments_unknown_station_is_400():
    response = client.post(BC, data={"station": "xyz"}, files={
        "norm_file": ("n.csv", NORM_CSV, "text/csv"),
        "events_file": ("e.xlsx", EVENTS_XLSX, XLSX_MIME),
    })
    _assert_clean_client_error(response, 400)


def test_baggage_comments_vko_wrong_norm_extension_is_400():
    response = client.post(BC, data={"station": "vko"}, files={
        "norm_file": ("n.xlsx", NORM_CSV, XLSX_MIME),
        "events_file": ("e.xlsx", EVENTS_XLSX, XLSX_MIME),
    })
    _assert_clean_client_error(response, 400)
    assert "csv-файл" in response.json()["detail"]


def test_baggage_comments_vko_missing_norm_columns_is_400():
    response = client.post(BC, data={"station": "vko"}, files={
        "norm_file": ("n.csv", b"date,flight\n2026-01-05,PBD1\n", "text/csv"),
        "events_file": ("e.xlsx", EVENTS_XLSX, XLSX_MIME),
    })
    _assert_clean_client_error(response, 400)
    assert "company" in response.json()["detail"]


@pytest.mark.parametrize("norm_bytes", [b"", b"\xff\xfe\x00garbage\n\n"])
def test_baggage_comments_vko_empty_or_binary_csv_is_400(norm_bytes):
    response = client.post(BC, data={"station": "vko"}, files={
        "norm_file": ("n.csv", norm_bytes, "text/csv"),
        "events_file": ("e.xlsx", EVENTS_XLSX, XLSX_MIME),
    })
    _assert_clean_client_error(response, 400)


def test_baggage_comments_vko_corrupt_events_xlsx_is_400():
    response = client.post(BC, data={"station": "vko"}, files={
        "norm_file": ("n.csv", NORM_CSV, "text/csv"),
        "events_file": ("e.xlsx", b"junk", XLSX_MIME),
    })
    _assert_clean_client_error(response, 400)


def test_baggage_comments_tbs_csv_instead_of_excel_is_400():
    response = client.post(BC, data={"station": "tbs"}, files={
        "norm_file": ("n.csv", NORM_CSV, "text/csv"),
        "events_file": ("e.xlsx", EVENTS_XLSX, XLSX_MIME),
    })
    _assert_clean_client_error(response, 400)


@pytest.mark.parametrize("norm_bytes, events_bytes", [
    (b"junk", EVENTS_XLSX),
    (b"", b""),
])
def test_baggage_comments_tbs_corrupt_or_empty_files_are_400(norm_bytes, events_bytes):
    response = client.post(BC, data={"station": "tbs"}, files={
        "norm_file": ("n.xlsx", norm_bytes, XLSX_MIME),
        "events_file": ("e.xlsx", events_bytes, XLSX_MIME),
    })
    _assert_clean_client_error(response, 400)

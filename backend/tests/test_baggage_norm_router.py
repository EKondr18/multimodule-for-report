"""Тесты загрузки еженедельной выгрузки baggage_norm через роутер
(app/modules/baggage_norm/router.py) поверх FakeRepo (tests/fakes.py).

Покрывают: повторную загрузку той же выгрузки (нет дублей), выгрузку через
границу месяцев (разбиение по файлам YYYY-MM.csv) и повтор записи при
конфликте версий (409) без потери данных."""

from io import BytesIO

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from github import GithubException

from app.main import app
from app.modules.baggage_norm import processing as bn
from app.modules.baggage_norm import router as bnr
from tests.helpers import XLSX_MIME, make_weekly_xlsx

client = TestClient(app, raise_server_exceptions=False)

MASTER_JAN = f"{bnr.MASTER_DIR}/2026-01.csv"
MASTER_FEB = f"{bnr.MASTER_DIR}/2026-02.csv"
DATALENS_JAN = f"{bnr.DATALENS_DIR}/2026-01.csv"
DATALENS_FEB = f"{bnr.DATALENS_DIR}/2026-02.csv"

WEEK_JAN = [
    ("30.01.26", "SU100", "A1"),
    ("31.01.26", "SU200", "A2"),
]
WEEK_CROSS_MONTH = [
    ("30.01.26", "SU100", "A1"),
    ("31.01.26", "SU200", "A2"),
    ("01.02.26", "SU300", "B1"),
    ("02.02.26", "SU400", "B2"),
]


def upload(rows):
    return client.post(
        "/api/baggage-norm/process",
        files={"file": ("week.xlsx", make_weekly_xlsx(rows), XLSX_MIME)},
    )


def read_csv(text: str) -> pd.DataFrame:
    return pd.read_csv(BytesIO(text.encode("utf-8")))


# ---------------------------------------------------------------------------
# (a) повторная загрузка той же выгрузки
# ---------------------------------------------------------------------------

def test_uploading_the_same_week_twice_does_not_duplicate_rows(fake_repo):
    first = upload(WEEK_JAN)
    assert first.status_code == 200
    master_after_first = fake_repo.text(MASTER_JAN)
    datalens_after_first = fake_repo.text(DATALENS_JAN)

    second = upload(WEEK_JAN)
    assert second.status_code == 200
    assert fake_repo.text(MASTER_JAN) == master_after_first
    assert fake_repo.text(DATALENS_JAN) == datalens_after_first
    assert len(read_csv(fake_repo.text(MASTER_JAN))) == 2
    assert len(read_csv(fake_repo.text(DATALENS_JAN))) == 2


def test_response_reports_upload_size_even_when_nothing_new(fake_repo):
    # FLAG (for human review): поле "added" — это len(df_new), а не число
    # реально добавленных строк; повторная загрузка тоже даёт added=2.
    upload(WEEK_JAN)
    body = upload(WEEK_JAN).json()
    assert body == {"added": 2, "months": "2026-01"}


# ---------------------------------------------------------------------------
# (b) выгрузка через границу двух месяцев
# ---------------------------------------------------------------------------

def test_upload_spanning_two_months_is_split_into_monthly_files(fake_repo):
    response = upload(WEEK_CROSS_MONTH)
    assert response.status_code == 200
    assert response.json() == {"added": 4, "months": "2026-01, 2026-02"}

    assert set(fake_repo.files) == {MASTER_JAN, MASTER_FEB, DATALENS_JAN, DATALENS_FEB}
    jan = read_csv(fake_repo.text(MASTER_JAN))
    feb = read_csv(fake_repo.text(MASTER_FEB))
    assert jan["mc"].tolist() == ["A1", "A2"]
    assert feb["mc"].tolist() == ["B1", "B2"]
    assert jan["date"].tolist() == ["2026-01-30", "2026-01-31"]
    assert feb["date"].tolist() == ["2026-02-01", "2026-02-02"]

    dl_feb = read_csv(fake_repo.text(DATALENS_FEB))
    assert dl_feb.columns.tolist() == bn.DATALENS_COLUMNS
    assert dl_feb["flight"].tolist() == ["SU300", "SU400"]


# ---------------------------------------------------------------------------
# (c) конфликт версий (409) — повтор на актуальных данных
# ---------------------------------------------------------------------------

def _concurrent_csv(existing_text: str, extra_rows) -> str:
    """CSV, который записал бы «другой писатель»: старые данные + свои строки."""
    existing = read_csv(existing_text)
    existing["date"] = pd.to_datetime(existing["date"])
    extra = bn.read_weekly_excel(BytesIO(make_weekly_xlsx(extra_rows)))
    return bn.merge_with_master(existing, extra).to_csv(index=False)


def test_conflict_409_on_master_write_is_retried_and_keeps_concurrent_rows(fake_repo):
    upload(WEEK_JAN)  # в архиве уже A1, A2
    concurrent_rows = [("29.01.26", "SU500", "C1")]
    fired = {"done": False}

    def concurrent_writer(repo, path):
        # Сразу перед нашей записью master другой писатель дописывает C1
        # и меняет sha — наша запись получит 409.
        if path == MASTER_JAN and not fired["done"]:
            fired["done"] = True
            repo.put(path, _concurrent_csv(repo.text(path), concurrent_rows))

    fake_repo.on_update = concurrent_writer

    response = upload([("31.01.26", "SU700", "B9")])
    assert response.status_code == 200

    master_writes = [call for call in fake_repo.update_calls if call[0] == MASTER_JAN]
    assert len(master_writes) == 2, "первая попытка должна упасть на 409, вторая — пройти"

    mcs = sorted(read_csv(fake_repo.text(MASTER_JAN))["mc"].tolist())
    assert mcs == ["A1", "A2", "B9", "C1"], "строки конкурентного писателя не должны потеряться"


def test_persistent_conflicts_give_up_after_five_attempts(fake_repo):
    upload(WEEK_JAN)
    before = fake_repo.text(MASTER_JAN)

    def always_conflict(repo, path):
        if path == MASTER_JAN:
            repo.put(path, repo.text(path))  # меняем sha, содержимое прежнее

    fake_repo.on_update = always_conflict
    fake_repo.update_calls.clear()

    df_new = bn.read_weekly_excel(BytesIO(make_weekly_xlsx([("31.01.26", "SU700", "B9")])))
    with pytest.raises(GithubException):
        bnr._process_month_sync("2026-01", df_new, "msg", None, None)

    assert len([c for c in fake_repo.update_calls if c[0] == MASTER_JAN]) == 5
    assert fake_repo.text(MASTER_JAN) == before, "при полном провале ничего не записано"


def test_non_conflict_github_error_is_not_retried(fake_repo):
    upload(WEEK_JAN)

    def server_error(repo, path):
        if path == MASTER_JAN:
            raise GithubException(500, {"message": "boom"}, None)

    fake_repo.on_update = server_error
    fake_repo.update_calls.clear()

    df_new = bn.read_weekly_excel(BytesIO(make_weekly_xlsx([("31.01.26", "SU700", "B9")])))
    with pytest.raises(GithubException):
        bnr._process_month_sync("2026-01", df_new, "msg", None, None)
    assert len([c for c in fake_repo.update_calls if c[0] == MASTER_JAN]) == 1


def test_router_returns_500_when_conflicts_are_exhausted_and_writes_nothing(fake_repo):
    upload(WEEK_JAN)
    before_master = fake_repo.text(MASTER_JAN)
    before_datalens = fake_repo.text(DATALENS_JAN)

    def always_conflict(repo, path):
        if path == MASTER_JAN:
            repo.put(path, repo.text(path))

    fake_repo.on_update = always_conflict
    # FLAG (for human review): после исчерпания попыток исключение уходит из
    # asyncio.gather необработанным -> 500 без понятного сообщения. Данные
    # не испорчены (ничего не записано), но клиенту стоит ретраить.
    response = upload([("31.01.26", "SU700", "B9")])
    assert response.status_code == 500
    assert fake_repo.text(MASTER_JAN) == before_master
    assert fake_repo.text(DATALENS_JAN) == before_datalens

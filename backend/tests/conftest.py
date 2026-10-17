import pytest

from app.core import github_storage
from app.core import request_cache
from tests.fakes import FakeRepo


@pytest.fixture
def fake_repo(monkeypatch) -> FakeRepo:
    """Подменяет клиент GitHub: реальные функции github_storage работают
    поверх FakeRepo (сетевых вызовов нет, токен не нужен)."""
    repo = FakeRepo()
    monkeypatch.setattr(github_storage, "_repo", lambda: repo)
    return repo


@pytest.fixture(autouse=True)
def _reset_request_cache():
    # request_cache — модульное состояние (кэш результатов + in-flight futures);
    # без сброса результаты одного теста попадали бы в другой.
    request_cache._completed.clear()
    request_cache._inflight.clear()
    yield
    request_cache._completed.clear()
    request_cache._inflight.clear()

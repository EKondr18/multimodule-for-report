import pytest

from app.core import request_cache


@pytest.fixture(autouse=True)
def _reset_request_cache():
    # request_cache — модульное состояние (кэш результатов + in-flight futures);
    # без сброса результаты одного теста попадали бы в другой.
    request_cache._completed.clear()
    request_cache._inflight.clear()
    yield
    request_cache._completed.clear()
    request_cache._inflight.clear()

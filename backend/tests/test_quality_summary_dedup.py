"""Защита от «штормa» повторных запросов на /api/quality-report/summary.

Фронтенд повторяет один и тот же POST до 10 раз; app/core/request_cache.py
должен схлопнуть одновременные одинаковые запросы в ОДНО вычисление.
Тест подменяет тяжёлую функцию build_quality_tables на медленную и считает
вызовы, а также проверяет, что время ожидания близко к одному вычислению."""

import asyncio
import time

import httpx
import pandas as pd
import pytest

from app.main import app
from app.modules.quality_report import processing as qr_processing
from tests.helpers import XLSX_MIME, make_xlsx

DELAY_SECONDS = 1.0
CONCURRENT_REQUESTS = 5

PERRON = pd.DataFrame({
    "Дата": ["2026-01-05"],
    "Категория": ["Регистрация"],
    "Заключение": ["с виной"],
    "Описание": ["d"],
    "Исполнитель": ["e"],
    "Подразделение": ["ДСТ"],
})


def _form(marker: str):
    """Одинаковые файлы для всех параллельных попыток; marker меняет содержимое
    между тестами, чтобы ключи кэша не пересекались."""
    perron = PERRON.assign(Описание=marker)
    data = {"start_date": "2026-01-01", "end_date": "2026-01-31", "granularity": "month"}
    files = {"perron_file": ("perron.xlsx", make_xlsx({"ТАБЛИЦА": perron}), XLSX_MIME)}
    return data, files


@pytest.fixture
def slow_builder(monkeypatch):
    """Подменяем build_quality_tables: считаем вызовы и имитируем долгое вычисление.
    Патчим атрибут модуля — _build_summary импортирует его при каждом вызове."""
    calls = {"n": 0}
    real = qr_processing.build_quality_tables

    def slow(*args, **kwargs):
        calls["n"] += 1
        time.sleep(DELAY_SECONDS)  # выполняется в потоке (asyncio.to_thread)
        return real(*args, **kwargs)

    monkeypatch.setattr(qr_processing, "build_quality_tables", slow)
    return calls


@pytest.mark.asyncio
async def test_identical_concurrent_requests_compute_once(slow_builder):
    data, files = _form("concurrent")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        started = time.perf_counter()
        responses = await _post_many_with_files(client, data, files, CONCURRENT_REQUESTS)
        elapsed = time.perf_counter() - started

    assert all(r.status_code == 200 for r in responses), [r.status_code for r in responses]
    assert slow_builder["n"] == 1, "вычисление должно выполниться один раз"
    # Последовательно было бы ~N * DELAY; при дедупликации ~DELAY.
    assert elapsed < DELAY_SECONDS * 2.5, f"слишком долго: {elapsed:.2f}s"
    bodies = {r.text for r in responses}
    assert len(bodies) == 1, "все попытки получают один и тот же результат"


@pytest.mark.asyncio
async def test_request_after_completion_is_served_from_cache(slow_builder):
    data, files = _form("cached")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await _post_many_with_files(client, data, files, 1)
        second = await _post_many_with_files(client, data, files, 1)
    assert first[0].status_code == second[0].status_code == 200
    assert slow_builder["n"] == 1


@pytest.mark.asyncio
async def test_different_file_content_is_not_deduplicated(slow_builder):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        data_a, files_a = _form("variant-a")
        data_b, files_b = _form("variant-b")
        responses = await asyncio.gather(
            _post_many_with_files(client, data_a, files_a, 1),
            _post_many_with_files(client, data_b, files_b, 1),
        )
    assert all(r[0].status_code == 200 for r in responses)
    assert slow_builder["n"] == 2, "разные файлы — разные ключи кэша"


async def _post_many_with_files(client, data, files, count):
    """Каждый запрос получает свежий набор байтов файлов."""
    async def one():
        fresh = {name: (fname, content, mime) for name, (fname, content, mime) in files.items()}
        return await client.post("/api/quality-report/summary", data=data, files=fresh)

    return await asyncio.gather(*[one() for _ in range(count)])

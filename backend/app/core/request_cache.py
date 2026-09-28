"""Дедупликация и кэш повторяющихся тяжёлых запросов.

Фронтенд при "просыпающемся" Render (`fetchWithWakeup`, см.
frontend/src/api/base.ts) при обрыве соединения повторяет ОДИН И ТОТ ЖЕ
запрос (те же файлы, те же параметры) до 10 раз подряд. Гейтвей Render
обрывает соединение с клиентом примерно на 30-40 секунде, если сервер не
успел ответить — но сам процесс на сервере при этом не обязательно
прерывается и может продолжать досчитывать тот же запрос в фоне. Без
дедупликации это превращается в самоподдерживающуюся карусель: каждая
новая попытка запускает то же тяжёлое вычисление заново, не давая
предыдущей попытке спокойно доработать и вернуть результат — итоговый
ответ может не приходить очень долго, хотя каждое отдельное вычисление
само по себе укладывается в разумное время.

dedup(key, compute) — если вычисление с таким key уже идёт (это и есть
повторная попытка), просто дожидается ЕГО результата вместо того, чтобы
считать всё заново; если результат уже посчитан недавно — отдаёт его
без пересчёта вовсе.

ВАЖНО: compute должен быть async и не блокировать event loop надолго
(тяжёлую синхронную работу — через asyncio.to_thread) — иначе event loop
не сможет параллельно принять и обработать повторную попытку, пока не
закончит первую, и весь смысл дедупликации теряется.
"""

import asyncio
import time
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")

_MAX_ENTRIES = 32
_TTL_SECONDS = 600.0

_completed: dict[str, tuple[float, object]] = {}
_inflight: dict[str, "asyncio.Future[object]"] = {}


async def dedup(key: str, compute: Callable[[], Awaitable[T]]) -> T:
    now = time.monotonic()

    cached = _completed.get(key)
    if cached is not None and now - cached[0] < _TTL_SECONDS:
        return cached[1]  # type: ignore[return-value]

    existing = _inflight.get(key)
    if existing is not None:
        return await existing  # type: ignore[return-value]

    future: "asyncio.Future[object]" = asyncio.get_event_loop().create_future()
    _inflight[key] = future
    try:
        result = await compute()
        future.set_result(result)
        _completed[key] = (time.monotonic(), result)
        if len(_completed) > _MAX_ENTRIES:
            oldest_key = min(_completed, key=lambda k: _completed[k][0])
            del _completed[oldest_key]
        return result
    except Exception as exc:
        future.set_exception(exc)
        # Если параллельных ожидающих этого же ключа нет, exception на
        # future никто не заберёт через await — без этой строки asyncio
        # при сборке мусора шумит "Future exception was never retrieved".
        # Сам вызов .exception() ничего не потребляет — конкурентные
        # await existing по-прежнему получат то же исключение.
        future.exception()
        raise
    finally:
        _inflight.pop(key, None)

"""Простой "общий секрет" между фронтендом (Vercel) и бэкендом (Render).

Это НЕ настоящая аутентификация — секрет попадает во фронтенд-бандл и
виден любому, кто открыл легитимный сайт и посмотрел devtools. Цель —
только отсечь ботов/скан(н)еры, которые находят публичный URL Render и
дёргают API напрямую, не проходя через сайт.

Если переменная окружения APP_SHARED_SECRET не задана — проверка
полностью отключена (no-op), чтобы не ломать локальную разработку и не
ломать прод до того, как секрет будет явно выставлен в Render. В этом
случае при старте приложения выводится предупреждение в лог.
"""

import logging
import os

logger = logging.getLogger(__name__)

HEADER_NAME = "X-App-Secret"

APP_SHARED_SECRET = os.environ.get("APP_SHARED_SECRET", "")

# Пути, которые не требуют заголовка — keep-alive cron пингует /api/health*
# без каких-либо заголовков.
EXEMPT_PATH_PREFIXES = ("/api/health",)

if not APP_SHARED_SECRET:
    logger.warning(
        "APP_SHARED_SECRET не задан — проверка X-App-Secret отключена "
        "(no-op). Это нормально локально, но на проде стоит задать "
        "переменную окружения, чтобы отсечь ботов, дёргающих API напрямую."
    )


def is_exempt(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in EXEMPT_PATH_PREFIXES)


def is_valid(header_value: str | None) -> bool:
    """True, если запрос можно пропустить: секрет не настроен (no-op) или
    заголовок совпадает с настроенным значением."""
    if not APP_SHARED_SECRET:
        return True
    return header_value == APP_SHARED_SECRET

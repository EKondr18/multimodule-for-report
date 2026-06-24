from app.main import app

# Точка входа для Vercel Python runtime: достаточно экспортировать ASGI-приложение
# под именем `app`, остальную маршрутизацию (включая /api/baggage-norm/...)
# делает сам FastAPI — Vercel лишь проксирует все запросы в эту функцию (см. vercel.json).
__all__ = ["app"]

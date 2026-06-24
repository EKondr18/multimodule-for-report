# Мультимодульная система обработки данных для отчётов

Веб-приложение со вкладками. Каждая вкладка — отдельный модуль обработки
csv/excel-выгрузок: загрузка файла → обработка → пополнение общего файла
(хранится в `data/<модуль>/...` в этом репозитории) либо генерация таблицы
для копирования.

## Структура

```
backend/            # FastAPI — общий для всех модулей
  app/
    core/            # общая инфраструктура (запись/чтение файлов в GitHub)
    modules/
      baggage_norm/  # модуль 1: «Норматив выдачи багажа»
frontend/            # React + TS + Vite — общий UI, вкладки
  src/
    tabs.ts          # реестр вкладок — новый модуль добавляется одной строкой
    pages/           # страница на каждый модуль
data/
  baggage_norm/      # данные модуля «Норматив выдачи багажа» (master.csv, datalens.csv)
docker-compose.yml
```

## Модуль 1 — «Норматив выдачи багажа»

Вход: еженедельная выгрузка BI МАВ по обработке багажа (xlsx, структура
фиксирована — 8 строк шапки + 29 колонок; имя файла не важно).

Обработка (см. `backend/app/modules/baggage_norm/processing.py`):
1. Определение авиакомпании по префиксу номера рейса.
2. Расчёт статуса выдачи багажа (до 30 мин / 30–40 мин / более 40 мин /
   некорректные отметки / не определено).
3. Объединение с архивом `data/baggage_norm/master.csv`, дедупликация по
   `(date, flight, mc)`.
4. Обновлённый архив и производный 4-колоночный файл (`date, company,
   bag_status, flight`) — `data/baggage_norm/datalens.csv` — коммитятся
   обратно в репозиторий через GitHub API при каждой загрузке.

Пользователю отдаётся `datalens.csv` для DataLens — с предпросмотром,
динамическими фильтрами по колонкам и кнопкой скачивания csv.

## Запуск локально

```bash
export GITHUB_TOKEN=<токен с правом записи в репозиторий>
docker compose up --build
```

- Backend: http://localhost:8000/docs
- Frontend: http://localhost:5173

### Переменные окружения backend

| Переменная | Назначение | По умолчанию |
|---|---|---|
| `GITHUB_TOKEN` | токен с правом записи в репозиторий (обязателен) | — |
| `GITHUB_REPO` | `owner/repo`, куда писать данные | `EKondr18/multimodule-for-report` |
| `GITHUB_BRANCH` | ветка для коммитов с данными | `main` |

## Разработка без Docker

```bash
# backend
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload

# frontend
cd frontend && npm install && npm run dev
```

## Деплой на Vercel (два отдельных проекта)

**Backend** (`backend/`):
1. New Project → импортировать этот репозиторий → **Root Directory** = `backend`.
2. Vercel сам распознает `api/index.py` (serverless-функция, экспортирует FastAPI-приложение)
   и `vercel.json` (роутит все пути в эту функцию — маршрутизацией внутри занимается FastAPI).
3. Settings → Environment Variables → добавить `GITHUB_TOKEN`, `GITHUB_REPO`, `GITHUB_BRANCH`.
4. Deploy. Получите URL вида `https://<backend-project>.vercel.app`.

**Frontend** (`frontend/`):
1. New Project → тот же репозиторий → **Root Directory** = `frontend`.
2. Framework Preset — Vite (определится автоматически).
3. Settings → Environment Variables → `VITE_API_BASE_URL` = URL backend-проекта из шага выше
   (без слэша на конце, например `https://reports-backend.vercel.app`).
4. Deploy.

Локально `VITE_API_BASE_URL` не нужен — Vite dev-сервер проксирует `/api/*` на
`http://localhost:8000` (см. `vite.config.ts`), это покрывает запуск через
`docker compose` или `npm run dev`.

## Известное ограничение

Запись файлов идёт через GitHub Contents API. Поле `content` в ответе этого
API пустое для файлов больше ~1 МБ — для таких файлов чтение автоматически
переключается на Git Blobs API (см. `backend/app/core/github_storage.py`),
у которого лимит — 100 МБ. Если архив вырастет за этот предел, нужно будет
переходить на Git LFS.

Backend развёрнут на always-on хостинге (Render/аналог), поэтому жёсткого
лимита времени на запрос, характерного для serverless-функций (как на
Vercel Hobby — 10 сек), здесь нет.

from fastapi import FastAPI, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.shared_secret import HEADER_NAME, is_exempt, is_valid
from app.modules.baggage_comments.router import router as baggage_comments_router
from app.modules.baggage_norm.router import router as baggage_norm_router
from app.modules.month_report.router import router as month_report_router
from app.modules.quality_report.router import router as quality_report_router

app = FastAPI(title="Отчёты — мультимодульное приложение")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def shared_secret_middleware(request: Request, call_next):
    """Боты/скан(н)еры, нашедшие публичный URL Render, не проходят через
    фронтенд и не знают заголовка X-App-Secret — см.
    app/core/shared_secret.py. Не настоящая аутентификация, а именно
    отсечение такого трафика; /api/health* исключён, чтобы keep-alive
    cron-пинги (без заголовка) продолжали работать."""
    if is_exempt(request.url.path):
        return await call_next(request)
    if not is_valid(request.headers.get(HEADER_NAME)):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)

app.include_router(baggage_norm_router)
app.include_router(baggage_comments_router)
app.include_router(quality_report_router)
app.include_router(month_report_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/health/echo-json")
async def health_echo_json(payload: dict):
    """Диагностика: простой POST с JSON-телом, без файлов и без multipart —
    проверяет, доходит ли вообще POST-запрос с телом до кода, если это не
    file-upload. GitHub API здесь не вызывается ни разу."""
    print(f"[health/echo-json] received: {payload}", flush=True)
    return {"status": "ok", "received": payload}


@app.post("/api/health/echo-file")
async def health_echo_file(file: UploadFile):
    """Диагностика: минимальный file-upload эндпоинт (multipart/form-data),
    без какой-либо бизнес-логики и без обращений к GitHub — изолирует,
    зависает ли сам приём/разбор multipart-тела на этом хостинге."""
    import time

    t0 = time.perf_counter()
    raw = await file.read()
    print(f"[health/echo-file] received {len(raw)} bytes in {time.perf_counter() - t0:.2f}s", flush=True)
    return {"status": "ok", "size": len(raw)}


@app.get("/api/health/github")
def health_github():
    """Диагностика: проверяет только доступность GitHub API (без остальной
    бизнес-логики) с явным коротким таймаутом — чтобы понять, не в этом ли
    причина зависаний /process (там таймаут по умолчанию мог быть больше,
    чем терпит шлюз Render, из-за чего исключение никогда не долетало до
    логов — соединение обрывалось раньше)."""
    import time

    from github import Github

    from app.config import GITHUB_BRANCH, GITHUB_REPO, GITHUB_TOKEN

    t0 = time.perf_counter()
    try:
        repo = Github(GITHUB_TOKEN, timeout=8).get_repo(GITHUB_REPO)
        commit = repo.get_branch(GITHUB_BRANCH).commit.sha
        return {
            "status": "ok",
            "repo": repo.full_name,
            "branch_head_sha": commit,
            "elapsed_seconds": round(time.perf_counter() - t0, 2),
        }
    except Exception as exc:
        return {
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_seconds": round(time.perf_counter() - t0, 2),
        }

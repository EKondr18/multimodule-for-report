from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

app.include_router(baggage_norm_router)
app.include_router(baggage_comments_router)
app.include_router(quality_report_router)
app.include_router(month_report_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


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

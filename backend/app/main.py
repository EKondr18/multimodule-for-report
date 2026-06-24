from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.modules.baggage_norm.router import router as baggage_norm_router

app = FastAPI(title="Отчёты — мультимодульное приложение")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(baggage_norm_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}

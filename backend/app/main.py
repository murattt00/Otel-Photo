"""
FastAPI uygulamasinin giris noktasi.

Calistirma (backend/ klasorunden, venv aktifken):
    uvicorn app.main:app --reload

Ardindan tarayicidan:
    http://localhost:8000/         -> API calisiyor mesaji
    http://localhost:8000/docs     -> otomatik interaktif API dokumantasyonu (Swagger UI)
    http://localhost:8000/health   -> sunucu saglik kontrolu
    http://localhost:8000/health/db-> veritabani baglanti kontrolu
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routers import (
    customers,
    health,
    kiosk,
    operator,
    orders,
    photographers,
    photos,
    products,
)
from app.worker import start_worker, stop_worker


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Uygulama acilirken foto isleme worker'ini baslat, kapanirken durdur.
    start_worker()
    yield
    stop_worker()


app = FastAPI(
    title="Otel Foto Sistemi API",
    description="Otel fotografcilari icin yuz tanima tabanli foto yonetim ve siparis sistemi.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(photographers.router)
app.include_router(photos.router)
app.include_router(customers.router)
app.include_router(kiosk.router)
app.include_router(products.router)
app.include_router(orders.router)
app.include_router(operator.router)


@app.get("/", tags=["genel"])
def root():
    """Kok endpoint: API'nin ayakta oldugunu dogrulamak icin."""
    return {"mesaj": "Otel Foto Sistemi API calisiyor.", "dokumantasyon": "/docs"}

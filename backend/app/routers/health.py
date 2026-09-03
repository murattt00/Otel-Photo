"""
Saglik kontrol (health check) endpointleri.

Sistemin ayakta olup olmadigini ve veritabanina baglanip baglanamadigini
kontrol etmek icin kullanilir. Tarayicidan /docs uzerinden test edilebilir.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter(prefix="/health", tags=["saglik"])


@router.get("")
def health():
    """Sunucu ayakta mi? (Veritabanina bakmaz.)"""
    return {"durum": "ok"}


@router.get("/db")
def health_db(db: Session = Depends(get_db)):
    """Veritabani baglantisi calisiyor mu? Basit bir SELECT 1 dener."""
    try:
        db.execute(text("SELECT 1"))
        return {"durum": "ok", "veritabani": "baglandi"}
    except Exception as e:  # noqa: BLE001 -- kullaniciya net hata gostermek istiyoruz
        return {"durum": "hata", "veritabani": "baglanamadi", "detay": str(e)}

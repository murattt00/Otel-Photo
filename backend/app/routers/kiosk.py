"""
Kiosk (musteri) endpointleri.

Akis:
- GET  /kiosk        -> kiosk arayuz sayfasi (static/index.html)
- GET  /kiosk/info   -> otel adi gibi arayuz bilgileri
- POST /kiosk/scan   -> webcam yakalamasini alir, yuzu tanir, eslesen musterinin
                        (filigranli) fotograflarini dondurur. YENI musteri ACMAZ (salt-okunur).
"""
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import settings
from app.database import get_db
from app.services.face_service import detect_faces_bytes
from app.services.matching_service import find_best_customer
from app.services.settings_service import otel_adi

router = APIRouter(prefix="/kiosk", tags=["kiosk"])

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@router.get("")
def kiosk_page():
    """Kiosk arayuz sayfasini dondurur."""
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/info")
def kiosk_info():
    """Arayuzun ihtiyac duydugu marka bilgileri."""
    return {"hotel_name": otel_adi()}


def _customer_photos(db: Session, customer_id: int) -> list[models.Photo]:
    return (
        db.query(models.Photo)
        .join(models.Face, models.Face.photo_id == models.Photo.id)
        .filter(models.Face.customer_id == customer_id)
        .distinct()
        .order_by(models.Photo.id)
        .all()
    )


@router.get("/by-email", response_model=schemas.KioskScanResult)
def by_email(email: str, db: Session = Depends(get_db)):
    """E-posta ile giris: bu e-postayla verilmis en son siparisin musterisini bulur ve o
    musterinin fotolarini dondurur. (Yuz taramaya alternatif kimlik.)"""
    order = (
        db.query(models.Order)
        .filter(models.Order.email == email)
        .order_by(models.Order.created_at.desc())
        .first()
    )
    if order is None:
        return schemas.KioskScanResult(
            eslesme=False,
            sebep="musteri_bulunamadi",
            mesaj="Bu e-posta ile kayitli siparis bulunamadi. Yuz taramayi deneyebilirsiniz.",
        )

    photos = _customer_photos(db, order.customer_id)
    return schemas.KioskScanResult(
        eslesme=True,
        musteri_id=order.customer_id,
        mesaj=f"{len(photos)} fotograf bulundu.",
        fotolar=[
            schemas.KioskPhoto(id=p.id, url=f"/photos/{p.id}/image?filigran=true") for p in photos
        ],
    )


@router.post("/scan", response_model=schemas.KioskScanResult)
def scan(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Webcam karesinden musteriyi tanir ve fotograflarini dondurur."""
    content = file.file.read()
    faces = detect_faces_bytes(content, apply_filter=False)

    if not faces:
        return schemas.KioskScanResult(
            eslesme=False,
            sebep="yuz_bulunamadi",
            mesaj="Yuz algilanamadi. Lutfen yuzunuzu kameraya yaklastirip tekrar deneyin.",
        )

    # Ekrana en yakin (en buyuk) yuzu al -- musterinin kendisi oldugu varsayimi
    best = max(
        faces,
        key=lambda f: (f.bbox["x2"] - f.bbox["x1"]) * (f.bbox["y2"] - f.bbox["y1"]),
    )

    customer, score = find_best_customer(db, best.embedding)
    if customer is None:
        return schemas.KioskScanResult(
            eslesme=False,
            sebep="musteri_bulunamadi",
            benzerlik=round(score, 3),
            mesaj="Size ait fotograf bulunamadi. Lutfen tekrar deneyin veya gorevliye danisin.",
        )

    photos = (
        db.query(models.Photo)
        .join(models.Face, models.Face.photo_id == models.Photo.id)
        .filter(models.Face.customer_id == customer.id)
        .distinct()
        .order_by(models.Photo.id)
        .all()
    )

    return schemas.KioskScanResult(
        eslesme=True,
        musteri_id=customer.id,
        benzerlik=round(score, 3),
        mesaj=f"{len(photos)} fotograf bulundu.",
        fotolar=[
            schemas.KioskPhoto(id=p.id, url=f"/photos/{p.id}/image?filigran=true")
            for p in photos
        ],
    )

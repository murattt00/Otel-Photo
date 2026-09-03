"""
Musteri (yuz grubu / klasor) goruntuleme endpointleri.

Bir Customer, ayni kisiye ait fotograflarin toplandigi mantiksal klasordur (musteri_XXX).
Bir fotoda birden fazla yuz olabildigi icin, bir foto birden fazla musteride gorunebilir.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/customers", tags=["musteriler"])


@router.get("", response_model=list[schemas.CustomerOut])
def list_customers(db: Session = Depends(get_db)):
    """Tum musteri klasorlerini, her birindeki farkli foto sayisiyla listeler."""
    # Musteri basina distinct foto sayisi (ayni fotoda ayni kisinin 2 yuzu olmaz ama garanti)
    counts = (
        db.query(
            models.Face.customer_id,
            func.count(func.distinct(models.Face.photo_id)).label("foto_sayisi"),
        )
        .group_by(models.Face.customer_id)
        .all()
    )
    count_map = {cid: n for cid, n in counts}

    customers = db.query(models.Customer).order_by(models.Customer.folder_code).all()
    return [
        schemas.CustomerOut(
            id=c.id,
            folder_code=c.folder_code,
            is_active=c.is_active,
            foto_sayisi=count_map.get(c.id, 0),
        )
        for c in customers
    ]


@router.get("/{customer_id}/photos", response_model=list[schemas.PhotoOut])
def customer_photos(customer_id: int, db: Session = Depends(get_db)):
    """Bir musteri klasorundeki fotograflari listeler."""
    customer = db.get(models.Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Musteri bulunamadi.")

    photos = (
        db.query(models.Photo)
        .join(models.Face, models.Face.photo_id == models.Photo.id)
        .filter(models.Face.customer_id == customer_id)
        .distinct()
        .order_by(models.Photo.id)
        .all()
    )
    return photos

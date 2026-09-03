"""
Fotografci yonetimi endpointleri.

Yukleme sirasinda operator, listeden bir fotografci secer; o partideki tum fotolar
o fotografciya (Photo.uploaded_by_id) yazilir ve satis geliri ona sayilir.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(prefix="/photographers", tags=["fotografcilar"])


@router.post("", response_model=schemas.PhotographerOut, status_code=201)
def create_photographer(data: schemas.PhotographerCreate, db: Session = Depends(get_db)):
    """Yeni fotografci ekler."""
    exists = db.query(models.Photographer).filter_by(username=data.username).first()
    if exists:
        raise HTTPException(status_code=400, detail="Bu kullanici adi zaten kayitli.")
    photographer = models.Photographer(name=data.name, username=data.username)
    db.add(photographer)
    db.commit()
    db.refresh(photographer)
    return photographer


@router.get("", response_model=list[schemas.PhotographerOut])
def list_photographers(db: Session = Depends(get_db)):
    """Tum fotografcilari listeler (yukleme ekranindaki secim listesi icin)."""
    return db.query(models.Photographer).order_by(models.Photographer.name).all()

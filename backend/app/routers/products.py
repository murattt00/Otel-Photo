"""
Urun / albuw turu yonetimi (operator tarafi).

Operator burada satis secenekleri tanimlar: "5'lik Albuw / 300TL / 5 foto",
"10'luk Paket / 500TL / 10 foto", "Serbest Secim / ... / sinirsiz" gibi.
Musteri kioskta (Asama 2C) bu aktif urunlerden sececek.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services.auth_service import require_operator

router = APIRouter(prefix="/products", tags=["urunler"])


@router.post("", response_model=schemas.ProductOut, status_code=201, dependencies=[Depends(require_operator)])
def create_product(data: schemas.ProductCreate, db: Session = Depends(get_db)):
    """Yeni urun/albuw turu ekler."""
    product = models.Product(**data.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.get("", response_model=list[schemas.ProductOut])
def list_products(sadece_aktif: bool = False, db: Session = Depends(get_db)):
    """Urunleri listeler. sadece_aktif=True ise sadece aktif olanlar (kiosk icin)."""
    query = db.query(models.Product)
    if sadece_aktif:
        query = query.filter(models.Product.is_active.is_(True))
    return query.order_by(models.Product.id).all()


@router.patch("/{product_id}", response_model=schemas.ProductOut, dependencies=[Depends(require_operator)])
def update_product(product_id: int, data: schemas.ProductUpdate, db: Session = Depends(get_db)):
    """Urunu gunceller (sadece gonderilen alanlar)."""
    product = db.get(models.Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Urun bulunamadi.")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}", status_code=204, dependencies=[Depends(require_operator)])
def delete_product(product_id: int, db: Session = Depends(get_db)):
    """Urunu siler."""
    product = db.get(models.Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Urun bulunamadi.")
    db.delete(product)
    db.commit()

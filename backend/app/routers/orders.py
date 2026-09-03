"""
Siparis (sepet) endpointleri.

- POST   /orders            -> kioskta musteri sepeti onaylayinca cagrilir; siparis olusur (status=yeni)
- GET    /orders            -> operator gelen siparisleri gorur (status filtresi opsiyonel)
- GET    /orders/{id}       -> siparis detayi (fotolar + notlar)
- PATCH  /orders/{id}/status-> operator durumu gunceller (yeni -> hazir -> teslim)

Onemli: satilan her foto, cekildigi fotografciya (Photo.uploaded_by_id) baglidir; bu sayede
"fotografci basina satis" raporu OrderItem -> Photo -> Photographer zinciriyle cikarilabilir.
"""
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import settings
from app.database import get_db
from app.services import delivery
from app.services.order_export import export_order, order_folder
from app.services.auth_service import is_logged_in, require_operator

router = APIRouter(prefix="/orders", tags=["siparisler"])

GECERLI_DURUMLAR = {"yeni", "hazir", "teslim"}


def _validate_product_and_photos(db: Session, product_id: int | None, items) -> None:
    """Urun (varsa) + kapasite + fotograflarin varligini dogrular; hatada HTTPException atar."""
    if not items:
        raise HTTPException(status_code=400, detail="Sepette en az bir fotograf olmali.")

    if product_id is not None:
        product = db.get(models.Product, product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="Secilen urun bulunamadi.")
        # Sabit albuw: TAM olarak photo_count kadar foto olmali (ne az ne fazla).
        # Serbest urun (photo_count=None): sinir yok.
        if product.photo_count is not None and len(items) != product.photo_count:
            raise HTTPException(
                status_code=400,
                detail=f"'{product.name}' tam {product.photo_count} foto icermeli; "
                f"{len(items)} foto secildi.",
            )

    photo_ids = [it.photo_id for it in items]
    bulunan = db.query(models.Photo.id).filter(models.Photo.id.in_(photo_ids)).count()
    if bulunan != len(set(photo_ids)):
        raise HTTPException(status_code=400, detail="Bazi fotograflar bulunamadi.")


def _order_total(order: models.Order) -> float | None:
    """Siparis toplam fiyati. Serbest urun (photo_count=None) -> foto basi fiyat x foto sayisi;
    sabit albuw -> urunun sabit fiyati."""
    if order.product is None:
        return None
    if order.product.photo_count is None:  # serbest / foto basi
        return round(order.product.price * len(order.items), 2)
    return order.product.price


def _serialize(order: models.Order) -> schemas.OrderOut:
    """Order ORM nesnesini, operatorun ihtiyac duydugu turetilmis alanlarla birlikte cikartir."""
    return schemas.OrderOut(
        id=order.id,
        customer_id=order.customer_id,
        customer_folder=order.customer.folder_code if order.customer else None,
        product_id=order.product_id,
        product_name=order.product.name if order.product else None,
        email=order.email,
        status=order.status,
        note=order.note,
        created_at=order.created_at,
        revised=order.revised_at is not None,
        foto_sayisi=len(order.items),
        toplam_fiyat=_order_total(order),
        items=[
            schemas.OrderItemOut(
                id=it.id, photo_id=it.photo_id, note=it.note, edited=bool(it.edited_path)
            )
            for it in sorted(order.items, key=lambda x: x.id)
        ],
    )


@router.post("", response_model=schemas.OrderOut, status_code=201)
def create_order(
    data: schemas.OrderCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Sepeti siparise cevirir (kiosk onayi). Siparis, editorun calismasi icin arka planda
    'siparis_XXXX' klasoru olarak da yazilir."""
    customer = db.get(models.Customer, data.customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Musteri bulunamadi.")

    _validate_product_and_photos(db, data.product_id, data.items)

    order = models.Order(
        customer_id=data.customer_id,
        product_id=data.product_id,
        email=data.email,
        note=data.note,
        status="yeni",
        items=[models.OrderItem(photo_id=it.photo_id, note=it.note) for it in data.items],
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    background.add_task(export_order, order.id)  # siparis klasorunu arka planda olustur
    return _serialize(order)


@router.get("", response_model=list[schemas.OrderOut])
def list_orders(
    request: Request,
    status: str | None = None,
    customer_id: int | None = None,
    email: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Siparisleri listeler (en yeni ustte). limit/offset ile sayfalama (operator icin).

    GUVENLIK: kiosk bu ucu SADECE kendi musterisi icin cagirir (?customer_id=... veya
    ?email=...). Filtresiz cagri = TUM otelin siparisleri + e-postalari demektir; bu yuzden
    filtre yoksa operator girisi sarttir.
    """
    if customer_id is None and not email and not is_logged_in(request, db):
        raise HTTPException(
            status_code=401,
            detail="Tum siparisleri listelemek icin operator girisi gerekli.",
        )

    query = db.query(models.Order)
    if status:
        query = query.filter(models.Order.status == status)
    if customer_id is not None:
        query = query.filter(models.Order.customer_id == customer_id)
    if email:
        query = query.filter(models.Order.email == email)
    # Yeni sekmesinde: once duzenlenmis (revised) olanlar dikkat ceksin, sonra en yeni
    query = query.order_by(models.Order.created_at.desc())
    if offset:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)
    return [_serialize(o) for o in query.all()]


@router.get("/sayilar", dependencies=[Depends(require_operator)])
def order_counts(db: Session = Depends(get_db)):
    """Sekme rozetleri + sayfalama icin durum bazli siparis sayilari."""
    rows = db.query(models.Order.status, func.count()).group_by(models.Order.status).all()
    sayim = {s: n for s, n in rows}
    return {
        "yeni": sayim.get("yeni", 0),
        "hazir": sayim.get("hazir", 0),
        "toplam": sum(sayim.values()),
    }


@router.get("/{order_id}", response_model=schemas.OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    """Tek bir siparisin detayi."""
    order = db.get(models.Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Siparis bulunamadi.")
    return _serialize(order)


@router.patch("/{order_id}", response_model=schemas.OrderOut)
def update_order(
    order_id: int,
    data: schemas.OrderUpdate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Mevcut bir siparisi (sepeti) gunceller. Sadece 'yeni' durumdakiler duzenlenebilir;
    operator 'hazir'/'teslim' yaptiysa degistirilemez (409)."""
    order = db.get(models.Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Siparis bulunamadi.")

    _validate_product_and_photos(db, data.product_id, data.items)

    order.product_id = data.product_id
    order.email = data.email
    order.note = data.note
    # Eski kalemleri sil, yenilerini ekle (cascade delete-orphan)
    for it in list(order.items):
        db.delete(it)
    db.flush()
    for it in data.items:
        order.items.append(models.OrderItem(photo_id=it.photo_id, note=it.note))

    # Musteri duzenledi -> siparis "yeni" sekmesine geri duser + "duzenlendi" isaretlenir.
    # (Operator hazir yapmis olsa bile tekrar bakmasi gerekir.)
    order.status = "yeni"
    order.revised_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(order)
    background.add_task(export_order, order.id)  # klasoru guncelle (eksik fotolari ekler)
    return _serialize(order)


@router.patch("/{order_id}/status", response_model=schemas.OrderOut, dependencies=[Depends(require_operator)])
def update_status(order_id: int, data: schemas.OrderStatusUpdate, db: Session = Depends(get_db)):
    """Operator siparis durumunu gunceller."""
    if data.status not in GECERLI_DURUMLAR:
        raise HTTPException(
            status_code=400, detail=f"Gecersiz durum. Gecerli: {', '.join(GECERLI_DURUMLAR)}"
        )
    order = db.get(models.Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Siparis bulunamadi.")
    order.status = data.status
    db.commit()
    db.refresh(order)
    return _serialize(order)


# ---- Photoshop / duzenlenmis versiyon + teslim paketi ----

@router.post("/{order_id}/items/{item_id}/edited", response_model=schemas.OrderOut, dependencies=[Depends(require_operator)])
def upload_edited(
    order_id: int,
    item_id: int,
    file: UploadFile = File(..., description="Photoshop'lu (duzenlenmis) foto"),
    db: Session = Depends(get_db),
):
    """Operator, bir siparis fotosunun photoshop'lu halini yukler.

    Dosya siparis klasorune (siparis_XXXX/NN_fotoX.ext) yazilir -- yani editorun elle
    duzenledigi yerle AYNI yere. Orijinal (Photo.stored_path) degismez. Boylece ister
    panelden yuklensin ister klasorde duzenlensin, teslim paketi tek kaynaktan uretilir."""
    item = db.get(models.OrderItem, item_id)
    if item is None or item.order_id != order_id:
        raise HTTPException(status_code=404, detail="Siparis kalemi bulunamadi.")

    ext = Path(file.filename or "").suffix.lower()
    if ext not in settings.ALLOWED_IMAGE_EXTS:
        raise HTTPException(status_code=400, detail="Sadece jpg/jpeg/png yuklenebilir.")

    # Dosya DOGRUDAN siparis klasorune yazilir: teslim paketinin tek kaynagi orasi
    # (bkz. services/delivery.py). Ayri bir "edited" klasorune yazilsaydi panelden
    # yuklenen duzenleme musteriye hic gitmezdi.
    order_items = sorted(
        db.query(models.OrderItem).filter(models.OrderItem.order_id == order_id).all(),
        key=lambda x: x.id,
    )
    sira = next((i for i, x in enumerate(order_items, 1) if x.id == item_id), 1)
    klasor = order_folder(order_id)
    klasor.mkdir(parents=True, exist_ok=True)
    dst = klasor / f"{sira:02d}_foto{item.photo_id}{ext}"
    with open(dst, "wb") as f:
        shutil.copyfileobj(file.file, f)
    item.edited_path = str(dst)
    db.commit()

    order = db.get(models.Order, order_id)
    return _serialize(order)


@router.get("/items/{item_id}/edited-image", dependencies=[Depends(require_operator)])
def edited_image(item_id: int, db: Session = Depends(get_db)):
    """Bir siparis kaleminin duzenlenmis (photoshop'lu) gorselini dondurur."""
    item = db.get(models.OrderItem, item_id)
    if item is None or not item.edited_path or not os.path.exists(item.edited_path):
        raise HTTPException(status_code=404, detail="Duzenlenmis versiyon yok.")
    return FileResponse(item.edited_path, media_type="image/jpeg")


@router.post("/{order_id}/export", dependencies=[Depends(require_operator)])
def export_order_folder(order_id: int, db: Session = Depends(get_db)):
    """Siparisin 'siparis_XXXX' klasorunu (yeniden) olusturur. Editorun makinesine paylasilan
    ORDERS_EXPORT_DIR altina yazar. Var olan (duzenlenmis) dosyalari ezmez."""
    order = db.get(models.Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Siparis bulunamadi.")
    path = export_order(order_id)
    return {"klasor": path, "mesaj": "Siparis klasoru olusturuldu/guncellendi."}



@router.post("/{order_id}/gonderime-hazirla", dependencies=[Depends(require_operator)])
def gonderime_hazirla(order_id: int, db: Session = Depends(get_db)):
    """Siparisi gonderime hazirlar: siparis_XXXX klasorunu zip'leyip GONDERILECEK_DIR'e koyar.

    Teslimatin tek kaynagi siparis klasorudur -- editor orada ne biraktiysa pakete o girer
    (bkz. services/delivery.py). Operator olusan zip'i alip istedigi yolla gonderir:
    mail eki, WeTransfer, TransferNow... Sistem gondermez, sadece paketi hazirlar.
    """
    order = db.get(models.Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Siparis bulunamadi.")

    sonuc = delivery.paket_hazirla(db, order)
    if not sonuc.get("hazir"):
        raise HTTPException(status_code=400, detail=sonuc.get("mesaj", "Paket hazirlanamadi."))
    return sonuc


@router.get("/{order_id}/paket", dependencies=[Depends(require_operator)])
def paket_indir(order_id: int, db: Session = Depends(get_db)):
    """Hazirlanmis gonderim zip'ini tarayiciya indirir (operator maile ek yapmak isterse)."""
    zip_yolu = delivery.paket_yolu(order_id)
    if not zip_yolu.exists():
        raise HTTPException(status_code=404, detail="Once 'Gonderime Hazirla'ya basin.")
    return FileResponse(zip_yolu, media_type="application/zip", filename=zip_yolu.name)

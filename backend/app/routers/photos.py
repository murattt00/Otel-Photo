"""
Fotograf yukleme ve listeleme endpointleri.

Yukleme akisi:
1. Operator listeden fotografciyi secer (photographer_id) ve o karttaki fotolari yukler.
2. Fotolar diske (data/raw_uploads) kaydedilir, veritabaninda Photo kaydi acilir (is_processed=False).
3. Yuz tespiti + siniflandirma ARKA PLANDA calisir (istek beklemez).
4. Sonuclar /customers ve /photos uzerinden takip edilebilir.
"""
import os
import shutil
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import settings
from app.database import get_db
from app.services import images
from app.services.settings_service import klasor
from app.services.auth_service import is_logged_in, require_operator

router = APIRouter(prefix="/photos", tags=["fotograflar"])

_MAX_BYTES = settings.MAX_UPLOAD_MB * 1024 * 1024


def _is_allowed_image(filename: str) -> bool:
    return Path(filename).suffix.lower() in settings.ALLOWED_IMAGE_EXTS


@router.post("/upload", response_model=schemas.UploadResult, dependencies=[Depends(require_operator)])
def upload_photos(
    photographer_id: int = Form(..., description="Fotolari ceken fotografcinin id'si"),
    files: list[UploadFile] = File(..., description="Yuklenecek fotograflar"),
    db: Session = Depends(get_db),
):
    """Bir fotografciya ait bir grup fotografi yukler.

    Dosyalar diske kaydedilir ve DB'ye status='pending' olarak yazilir; ANINDA doner.
    Yuz tanima/siniflandirma isini kalici worker (app/worker.py) sirayla arka planda yapar.
    """
    photographer = db.get(models.Photographer, photographer_id)
    if photographer is None:
        raise HTTPException(status_code=404, detail="Fotografci bulunamadi.")

    yukleme_dir = klasor("yukleme_klasoru")
    yukleme_dir.mkdir(parents=True, exist_ok=True)

    created_ids: list[int] = []
    skipped: list[str] = []
    for upload in files:
        # A3 — dosya dogrulama: tur
        if not _is_allowed_image(upload.filename or ""):
            skipped.append(upload.filename or "(isimsiz)")
            continue

        # Once kayit ac (id almak icin), sonra dosyayi id-onekli isimle diske AKIT (bellege
        # tumunu almadan -- buyuk dosyalar icin onemli).
        photo = models.Photo(
            filename=upload.filename,
            stored_path="",
            uploaded_by_id=photographer_id,
            status="pending",
            is_processed=False,
        )
        db.add(photo)
        db.flush()

        dst = yukleme_dir / f"{photo.id}_{upload.filename}"
        with open(dst, "wb") as f:
            shutil.copyfileobj(upload.file, f)

        # A3 — boyut dogrulama (yazdiktan sonra; guvenli): asilirsa sil + kaydi geri al
        if dst.stat().st_size > _MAX_BYTES:
            dst.unlink(missing_ok=True)
            db.delete(photo)
            db.flush()
            skipped.append(f"{upload.filename} (>{settings.MAX_UPLOAD_MB}MB)")
            continue

        photo.stored_path = str(dst)
        created_ids.append(photo.id)

    db.commit()

    return schemas.UploadResult(
        yuklenen=len(created_ids),
        atlanan=len(skipped),
        atlanan_dosyalar=skipped[:20],
        foto_idleri=created_ids,
        mesaj="Fotograflar alindi. Yuz tanima arka planda sirayla isleniyor; durumu /photos/durum'dan takip edin.",
    )


@router.post("/ingest", response_model=schemas.IngestResult, dependencies=[Depends(require_operator)])
def ingest_folder(data: schemas.IngestRequest, db: Session = Depends(get_db)):
    """Sunucudaki bir klasordeki fotograflari YERINDE isler (kopyalamadan).

    Buyuk partiler icin: operator hafiza kartini sunucudaki bir klasore kopyalar, o klasorun
    tam yolunu verir. Sistem klasoru (alt klasorler dahil) tarar, gecerli fotolari kuyruga
    ekler. Dosyalar oldugu yerde kalir (60 GB'i HTTP ile gondermeye gerek kalmaz).
    """
    photographer = db.get(models.Photographer, data.photographer_id)
    if photographer is None:
        raise HTTPException(status_code=404, detail="Fotografci bulunamadi.")

    root = Path(data.folder)
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail="Klasor bulunamadi veya klasor degil.")

    eklenen = 0
    atlanan = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if not _is_allowed_image(path.name):
            continue  # foto olmayanlari sessizce atla
        try:
            if path.stat().st_size > _MAX_BYTES:
                atlanan += 1
                continue
        except OSError:
            atlanan += 1
            continue
        db.add(
            models.Photo(
                filename=path.name,
                stored_path=str(path),  # YERINDE referans, kopya yok
                uploaded_by_id=data.photographer_id,
                status="pending",
                is_processed=False,
            )
        )
        eklenen += 1

    db.commit()
    return schemas.IngestResult(
        bulunan=eklenen + atlanan,
        eklenen=eklenen,
        atlanan=atlanan,
        mesaj=f"{eklenen} fotograf kuyruga eklendi, arka planda isleniyor. {atlanan} dosya atlandi.",
    )


@router.get("/durum", dependencies=[Depends(require_operator)])
def processing_status(db: Session = Depends(get_db)):
    """Isleme kuyrugu ozeti: kac foto bekliyor/isleniyor/bitti/hatali."""
    rows = db.query(models.Photo.status, func.count()).group_by(models.Photo.status).all()
    sayim = {s: n for s, n in rows}
    return {
        "pending": sayim.get("pending", 0),
        "processing": sayim.get("processing", 0),
        "done": sayim.get("done", 0),
        "error": sayim.get("error", 0),
        "toplam": sum(sayim.values()),
    }


@router.post("/tekrar-dene", dependencies=[Depends(require_operator)])
def hatali_fotolari_tekrar_dene(db: Session = Depends(get_db)):
    """status='error' fotolari tekrar kuyruga alir (pending yapar).

    Neden gerekli: worker sadece 'pending' fotolari isler. Bir foto (gecici DB hatasi,
    bozuk dosya, disk sorunu) 'error'a dustugunde kendiliginden bir daha denenmiyordu ve
    o fotonun yuzleri hicbir musteriye girmiyordu -- sessiz veri kaybi. Bu uc, operatorun
    tek tikla hepsini yeniden denemesini saglar.
    """
    sayi = (
        db.query(models.Photo)
        .filter(models.Photo.status == "error")
        .update({"status": "pending", "error": None}, synchronize_session=False)
    )
    db.commit()
    return {"tekrar_kuyruga_alinan": sayi}


@router.get("", response_model=list[schemas.PhotoOut], dependencies=[Depends(require_operator)])
def list_photos(db: Session = Depends(get_db)):
    """Tum fotograflari listeler (islenme durumu dahil)."""
    return db.query(models.Photo).order_by(models.Photo.id).all()


@router.get("/{photo_id}/image")
def photo_image(
    photo_id: int,
    request: Request,
    filigran: bool = True,
    boyut: str = "galeri",
    db: Session = Depends(get_db),
):
    """Fotografin gorselini dondurur. Turevler ONBELLEKLENIR (Faz C2): orijinal her istekte
    yeniden decode/filigran edilmez, hazir onbellek dosyasi servis edilir.

    - filigran=True, boyut=galeri -> filigranli 1400px (kiosk galeri) [onbellek]
    - filigran=True, boyut=tam    -> filigranli tam boyut (lightbox)   [onbellek, ilk acilista uretilir]
    - filigran=False, boyut=galeri-> filigransiz 1000px (operator onizleme) [onbellek]
    - filigran=False, boyut=tam   -> orijinal dosya (baski icin)
    """
    # GUVENLIK: filigranli surumler kiosk icin aciktir (musteri onlari zaten gorecek),
    # ama FILIGRANSIZ orijinal satilabilir uruntur -- sadece giris yapmis operator alabilir.
    if not filigran and not is_logged_in(request, db):
        raise HTTPException(status_code=401, detail="Filigransiz gorsel icin operator girisi gerekli.")

    photo = db.get(models.Photo, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Fotograf bulunamadi.")

    if filigran and boyut == "tam":
        path = images.full_path(photo.stored_path, photo.id)
    elif filigran:
        path = images.gallery_path(photo.stored_path, photo.id)
    elif boyut == "galeri":
        path = images.operator_preview_path(photo.stored_path, photo.id)
    else:
        path = photo.stored_path  # orijinal, tam boyut

    return FileResponse(path, media_type="image/jpeg")

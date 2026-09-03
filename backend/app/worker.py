"""
Arka plan foto isleme worker'i (kalici kuyruk).

Neden: FastAPI BackgroundTasks kalici degildi -- sunucu yeniden baslarsa yarim kalan isler
kaybolurdu ve es zamanli calisan gorevler yaris hatalarina yol acabilirdi.

Bunun yerine: uygulama basladiginda tek bir worker thread'i baslar. Surekli olarak
status='pending' fotograflari SIRAYLA (tek elden) isler:
- Yeniden baslamaya dayaniklidir (isler DB'de 'pending' olarak bekler).
- Sirali oldugu icin eslestirme yaris hatasi olusmaz.
- Bir foto hata verirse status='error' + mesaj yazilir, diger fotolar etkilenmez.

Foto claim'i FOR UPDATE SKIP LOCKED ile yapilir; ileride birden fazla worker calissa bile
ayni fotoyu iki worker almaz.
"""
import logging
import threading

from sqlalchemy import select

from app import models
from app.database import SessionLocal
from app.services.face_service import get_model
from app.services.processing import process_photo

log = logging.getLogger("foto-worker")

_stop = threading.Event()
_thread: threading.Thread | None = None
_POLL_SECONDS = 2.0


def _claim_next() -> int | None:
    """Siradaki bekleyen fotoyu 'processing' yapip id'sini dondurur (yoksa None)."""
    db = SessionLocal()
    try:
        photo = db.execute(
            select(models.Photo)
            .where(models.Photo.status == "pending")
            .order_by(models.Photo.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).scalars().first()
        if photo is None:
            return None
        photo.status = "processing"
        db.commit()
        return photo.id
    finally:
        db.close()


def _process(photo_id: int) -> None:
    db = SessionLocal()
    try:
        photo = db.get(models.Photo, photo_id)
        if photo is None:
            return
        try:
            n = process_photo(db, photo)
            db.commit()
            log.info("Foto islendi id=%s (%s yuz)", photo_id, n)
        except Exception as e:  # noqa: BLE001
            db.rollback()
            photo = db.get(models.Photo, photo_id)
            if photo is not None:
                photo.status = "error"
                photo.error = str(e)[:500]
                db.commit()
            log.exception("Foto islenemedi id=%s", photo_id)
    finally:
        db.close()


def _loop() -> None:
    log.info("Worker basladi")
    try:
        get_model()  # modeli onceden yukle (ilk foto beklemesin)
    except Exception:  # noqa: BLE001
        log.exception("Model on-yukleme hatasi (isleme sirasinda tekrar denenecek)")
    while not _stop.is_set():
        try:
            photo_id = _claim_next()
        except Exception:  # noqa: BLE001 -- DB gecici hatasi worker'i oldurmesin
            log.exception("Kuyruk okuma hatasi")
            _stop.wait(_POLL_SECONDS)
            continue
        if photo_id is None:
            _stop.wait(_POLL_SECONDS)  # is yok, biraz bekle
            continue
        _process(photo_id)
    log.info("Worker durdu")


def start_worker() -> None:
    """Uygulama basladiginda cagrilir."""
    global _thread
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="foto-worker", daemon=True)
    _thread.start()


def stop_worker() -> None:
    """Uygulama kapanirken cagrilir."""
    _stop.set()

"""
Tek bir fotografin islenmesi: yuz tespiti -> musteri eslestirme -> Face kaydi.

Onceki classification.py'nin yerini alir. Iki onemli olcek degisikligi:
- Fiziksel klasor KOPYALAMASI YOK (depolama sismesin). Musteri-foto iliskisi sadece Face
  tablosunda tutulur; kiosk/operator bu iliskiden okur.
- Eslestirme artimli centroid kullanir (matching_service), tum yuzleri tekrar okumaz.

Bu fonksiyon arka plan worker'i (app/worker.py) tarafindan, foto basina bir kez cagrilir.
"""
from sqlalchemy.orm import Session

from app import models
from app.services import images
from app.services.face_service import detect_faces
from app.services.matching_service import find_or_create_customer


def process_photo(db: Session, photo: models.Photo) -> int:
    """Bir fotografi isler: yuzleri bulur, musterilere atar, Face kayitlarini olusturur.

    Donen: tespit edilen (filtreyi gecen) yuz sayisi. Durum/commit cagiran worker'da yonetilir.
    """
    faces = detect_faces(photo.stored_path)
    for det in faces:
        customer, _score = find_or_create_customer(db, det.embedding)
        db.add(
            models.Face(
                photo_id=photo.id,
                customer_id=customer.id,
                embedding=det.embedding.tobytes(),
                det_score=det.det_score,
                bbox=det.bbox,
            )
        )
        db.flush()  # sonraki yuz, bu yuzun actigi/guncelledigi musteriyi gorebilsin

    # Kiosk'ta gosterilecek fotolar icin galeri onbellegini simdiden uret (yuz varsa)
    if faces:
        images.ensure_gallery_cache(photo.stored_path, photo.id)

    photo.status = "done"
    photo.is_processed = True
    photo.error = None
    return len(faces)

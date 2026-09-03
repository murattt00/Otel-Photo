"""
Eslestirme servisi: bir yuz embedding'ini dogru musteri klasorune (Customer) atar.

Prototipteki (scripts/test_face_clustering.py) mantik buraya tasindi, ama artik bellek
yerine VERITABANI uzerinden calisiyor ve SADECE SON `MATCH_WINDOW_DAYS` gunune bakiyor:

- Son 14 gunde kaydedilmis, aktif musterilerin yuz embedding'lerini al
- Her musteri icin centroid (ortalama embedding) hesapla
- Yeni yuzle en yuksek cosine benzerligini bul
- Esik (SIMILARITY_THRESHOLD) gecen en iyi musteriye ata; hicbiri gecmiyorsa yeni musteri ac

Not: 14 gun penceresi hem prototipin istegini karsilar hem de ilerde otomatik veri silme
(KVKK) icin dogal bir sinir olur.
"""
from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy.orm import Session

from app import models
from app.config import settings


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def _embedding_from_bytes(raw: bytes) -> np.ndarray:
    return np.frombuffer(raw, dtype=np.float32)


def _next_folder_code(db: Session) -> str:
    """Siradaki musteri_XXX kodunu uretir (mevcut en buyuk numaranin bir fazlasi)."""
    codes = [c[0] for c in db.query(models.Customer.folder_code).all()]
    nums = [
        int(code.split("_")[1])
        for code in codes
        if code.startswith("musteri_") and code.split("_")[1].isdigit()
    ]
    nxt = (max(nums) + 1) if nums else 1
    return f"musteri_{nxt:03d}"


def _active_customers(db: Session) -> list[models.Customer]:
    """Son ESLESTIRME penceresinde (updated_at) aktif olan, centroid'i olan musterileri getirir.

    Artik her musterinin centroid'i Customer satirinda saklandigi icin tum yuzleri tekrar
    okumaya gerek yok -- sadece ~birkac bin musteri satiri yuklenir (olcek dostu).
    NOT: Veri silinmiyor; 14 gunluk pencere sadece kimlerle karsilastirilacagini sinirlar.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.MATCH_WINDOW_DAYS)
    return (
        db.query(models.Customer)
        .filter(
            models.Customer.is_active.is_(True),
            models.Customer.centroid.isnot(None),
            models.Customer.updated_at >= cutoff,
        )
        .all()
    )


def _best_match(customers: list[models.Customer], embedding: np.ndarray) -> tuple[models.Customer | None, float]:
    """Verilen embedding'e en yakin musteriyi ve skorunu bulur (esik uygulamaz)."""
    best = None
    best_score = -1.0
    for c in customers:
        score = _cosine_similarity(embedding, _embedding_from_bytes(c.centroid))
        if score > best_score:
            best_score = score
            best = c
    return best, best_score


def _update_centroid(customer: models.Customer, embedding: np.ndarray) -> None:
    """Musterinin centroid'ini yeni yuzle artimli gunceller (tum yuzleri tekrar okumadan)."""
    old = _embedding_from_bytes(customer.centroid)
    n = customer.face_count or 0
    new = (old * n + embedding) / (n + 1)
    customer.centroid = new.astype(np.float32).tobytes()
    customer.face_count = n + 1


def find_or_create_customer(db: Session, embedding: np.ndarray) -> tuple[models.Customer, float]:
    """Verilen embedding'i mevcut bir musteriye eslestirir (ve centroid'ini gunceller) ya da
    yeni musteri olusturur. Yukleme/siniflandirma icin. Donen: (musteri, benzerlik_skoru)."""
    customers = _active_customers(db)
    best, best_score = _best_match(customers, embedding)

    if best is not None and best_score >= settings.SIMILARITY_THRESHOLD:
        _update_centroid(best, embedding)
        return best, best_score

    # Esigi gecen yok -> yeni musteri (ilk yuz = centroid)
    customer = models.Customer(
        folder_code=_next_folder_code(db),
        centroid=embedding.astype(np.float32).tobytes(),
        face_count=1,
    )
    db.add(customer)
    db.flush()  # id'yi al
    return customer, best_score


def find_best_customer(db: Session, embedding: np.ndarray) -> tuple[models.Customer | None, float]:
    """SALT-OKUNUR: embedding'e uyan mevcut musteriyi bulur, YENI musteri ACMAZ, centroid
    guncellemez. Kiosk taramasi icin. Esigi gecen yoksa (None, skor) doner."""
    customers = _active_customers(db)
    best, best_score = _best_match(customers, embedding)

    if best is not None and best_score >= settings.SIMILARITY_THRESHOLD:
        return best, best_score
    return None, best_score

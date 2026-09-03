"""
Onbellekli gorsel servisi (Faz C2).

Amac: kiosk galerisine her istekte 15 MB'lik orijinali decode edip filigran basmak yerine,
turevleri BIR KEZ uretip diske onbelleklemek, sonra hazir dosyayi servis etmek. Olcekte
CPU ve bant genisligi tasarrufu saglar.

Turevler (data/cache/ altinda):
- {id}_gal.jpg  : filigranli, max 1400px  -> kiosk galeri + lightbox kucuk hali
- {id}_full.jpg : filigranli, tam boyut   -> lightbox "tam" (istege bagli, ilk acilista uretilir)
- {id}_op.jpg   : filigransiz, max 1000px  -> operator siparis onizlemesi

Not: HOTEL_NAME degisirse filigranli onbellekler (gal/full) bayatlar; o durumda cache klasoru
temizlenmeli (basit cozum). Ilerde dosya adina otel adi hash'i eklenebilir.
"""
from pathlib import Path

from app.config import settings
from app.services.settings_service import otel_adi
from app.services.watermark import resized_jpeg, watermark_image

_GALLERY_MAX = 1400
_PREVIEW_MAX = 1000


def _cache_path(photo_id: int, kind: str) -> Path:
    return settings.CACHE_DIR / f"{photo_id}_{kind}.jpg"


def _ensure(path: Path, generate) -> Path:
    """path yoksa generate() ile bytes uretip yazar; her durumda path'i dondurur."""
    if not path.exists() or path.stat().st_size == 0:
        settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(generate())
    return path


def gallery_path(stored_path: str, photo_id: int) -> Path:
    """Filigranli galeri turevi (max 1400px)."""
    return _ensure(
        _cache_path(photo_id, "gal"),
        lambda: watermark_image(stored_path, otel_adi(), max_size=_GALLERY_MAX),
    )


def full_path(stored_path: str, photo_id: int) -> Path:
    """Filigranli tam boyut turevi (lightbox)."""
    return _ensure(
        _cache_path(photo_id, "full"),
        lambda: watermark_image(stored_path, otel_adi(), max_size=None),
    )


def operator_preview_path(stored_path: str, photo_id: int) -> Path:
    """Filigransiz kucuk operator onizlemesi (max 1000px)."""
    return _ensure(
        _cache_path(photo_id, "op"),
        lambda: resized_jpeg(stored_path, _PREVIEW_MAX),
    )


def ensure_gallery_cache(stored_path: str, photo_id: int) -> None:
    """Isleme sirasinda (worker) galeri turevini onceden uretir; hata islemeyi bozmaz."""
    try:
        gallery_path(stored_path, photo_id)
    except Exception:  # noqa: BLE001
        pass

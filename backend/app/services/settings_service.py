"""
Calisirken degistirilebilen klasor ayarlari (operator panelinden yonetilir).

Oncelik sirasi:  DB (app_settings)  >  .env  >  kod icindeki varsayilan

ONEMLI -- YOLLAR SUNUCUNUN GOZUNDEN:
Girilen yol SUNUCUDA cozulur, operatorun kendi bilgisayarinda degil. Operator ayri bir
makinedeyse "D:\\Siparisler" yazmak SUNUCUNUN D diskini gosterir. Editorun makinesindeki bir
klasor hedefleniyorsa UNC yolu kullanilmali:  \\\\EDITOR-PC\\Siparisler
(Tarayici guvenlik nedeniyle gercek klasor yolu veremez -- bu yuzden "klasore gozat" penceresi
yok, yol elle yazilir. Kaydetmeden once yazilabilirlik test edilir.)

Not: Ayarlar bellekte de tutulur (_cache). Boylece order_folder()/paket_yolu() gibi sik
cagrilan yardimcilar her seferinde DB'ye gitmez. Ayar degisince cache tazelenir.
"""
import os
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app import models
from app.config import settings

# Ayarlanabilir klasorler: anahtar -> varsayilan yol.
# Kullaniciya gosterilen etiket/aciklama metinleri UI tarafindadir (operator.html
# icindeki KLASOR_META). Boylece bu dosya ASCII kalir -- proje konvansiyonu.
KLASORLER: dict[str, Path] = {
    "siparis_klasoru": settings.ORDERS_EXPORT_DIR,
    "gonderilecek_klasoru": settings.GONDERILECEK_DIR,
    "yukleme_klasoru": settings.RAW_UPLOADS_DIR,
}

_cache: dict[str, str] = {}
_cache_dolu = False


def _cache_yukle(db: Session) -> None:
    """DB'deki tum ayarlari bellege okur. (_cache sozlugu yerinde guncellenir.)"""
    global _cache_dolu
    _cache.clear()
    for row in db.query(models.AppSetting).all():
        _cache[row.key] = row.value
    _cache_dolu = True


def _cache_gerekiyorsa_yukle() -> None:
    """Cache bos ise DB'den doldurur (kendi kisa oturumunu acar)."""
    global _cache_dolu
    if _cache_dolu:
        return
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        _cache_yukle(db)
    finally:
        db.close()


def klasor(anahtar: str) -> Path:
    """Ayarli klasor yolunu dondurur (DB > .env/varsayilan)."""
    if anahtar not in KLASORLER:
        raise KeyError(anahtar)
    _cache_gerekiyorsa_yukle()
    deger = _cache.get(anahtar)
    return Path(deger) if deger else KLASORLER[anahtar]


# --- Metin ayarlari (klasor olmayanlar) ---
OTEL_ADI_ANAHTAR = "otel_adi"


def otel_adi() -> str:
    """Kiosk basliginda ve filigranda kullanilan otel adi (DB > .env > varsayilan)."""
    _cache_gerekiyorsa_yukle()
    return _cache.get(OTEL_ADI_ANAHTAR) or settings.HOTEL_NAME


def otel_adi_ayarla(db: Session, ad: str) -> dict:
    """Otel adini kaydeder ve FILIGRANLI onbellegi temizler.

    Onbellek temizligi sart: {id}_gal.jpg / {id}_full.jpg dosyalarinin uzerinde ESKI otel
    adi yazili. Silinmezse kiosk eski ismi gostermeye devam eder. Filigransiz operator
    onizlemesi ({id}_op.jpg) etkilenmez, o durur.
    """
    ad = (ad or "").strip()
    if not ad:
        return {"gecerli": False, "mesaj": "Otel adi bos olamaz."}
    if len(ad) > 60:
        return {"gecerli": False, "mesaj": "Otel adi en fazla 60 karakter olabilir."}

    kayit = db.get(models.AppSetting, OTEL_ADI_ANAHTAR)
    if kayit is None:
        db.add(models.AppSetting(key=OTEL_ADI_ANAHTAR, value=ad))
    else:
        kayit.value = ad
    db.commit()
    _cache_yukle(db)

    silinen = _filigran_onbellegini_temizle()
    return {
        "gecerli": True,
        "mesaj": "Otel adi guncellendi.",
        "otel_adi": ad,
        "silinen_onbellek": silinen,
    }


def _filigran_onbellegini_temizle() -> int:
    """Filigranli turevleri (_gal / _full) siler. Sonraki istekte yeni isimle uretilirler."""
    silinen = 0
    cache = settings.CACHE_DIR
    if not cache.exists():
        return 0
    for f in cache.glob("*.jpg"):
        if f.stem.endswith("_gal") or f.stem.endswith("_full"):
            try:
                f.unlink()
                silinen += 1
            except OSError:
                pass
    return silinen


def dogrula(yol: str) -> dict:
    """Yolu kaydetmeden once test eder: olusturulabiliyor mu, yazilabiliyor mu?"""
    if not yol or not yol.strip():
        return {"gecerli": False, "mesaj": "Yol bos olamaz."}

    p = Path(yol.strip())
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return {"gecerli": False, "mesaj": f"Klasor olusturulamadi: {e}"}

    # Gercekten yazilabiliyor mu? (ag paylasiminda klasor gorunur ama yazilamaz olabilir)
    deneme = p / f".yazma_testi_{uuid.uuid4().hex[:8]}"
    try:
        deneme.write_text("test", encoding="utf-8")
        deneme.unlink()
    except OSError as e:
        return {"gecerli": False, "mesaj": f"Klasor var ama YAZILAMIYOR: {e}"}

    return {"gecerli": True, "mesaj": "Klasor erisilebilir ve yazilabilir."}


def durum(anahtar: str) -> dict:
    """Bir klasor ayarinin panelde gosterilecek tam durumu."""
    varsayilan = KLASORLER[anahtar]
    yol = klasor(anahtar)
    _cache_gerekiyorsa_yukle()
    var = yol.exists()
    return {
        "anahtar": anahtar,
        "yol": str(yol),
        "varsayilan": str(varsayilan),
        "ozel": anahtar in _cache,          # operator degistirmis mi
        "mevcut": var,                       # klasor diskte var mi
        "yazilabilir": bool(var and os.access(yol, os.W_OK)),
    }


def tum_durumlar() -> list[dict]:
    return [durum(a) for a in KLASORLER]


def ayarla(db: Session, anahtar: str, yol: str) -> dict:
    """Klasor ayarini kaydeder (once dogrular). Gecersizse kaydetmez."""
    if anahtar not in KLASORLER:
        return {"gecerli": False, "mesaj": "Bilinmeyen ayar."}

    sonuc = dogrula(yol)
    if not sonuc["gecerli"]:
        return sonuc

    temiz = str(Path(yol.strip()))
    kayit = db.get(models.AppSetting, anahtar)
    if kayit is None:
        db.add(models.AppSetting(key=anahtar, value=temiz))
    else:
        kayit.value = temiz
    db.commit()
    _cache_yukle(db)
    return {"gecerli": True, "mesaj": "Kaydedildi.", "durum": durum(anahtar)}


def sifirla(db: Session, anahtar: str) -> dict:
    """Ayari siler -> tekrar .env/varsayilan degere doner."""
    kayit = db.get(models.AppSetting, anahtar)
    if kayit is not None:
        db.delete(kayit)
        db.commit()
    _cache_yukle(db)
    return {"gecerli": True, "mesaj": "Varsayilana donduruldu.", "durum": durum(anahtar)}

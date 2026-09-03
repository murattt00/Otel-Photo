"""
Uygulama ayarlari.

DATABASE_URL gibi degerler backend/.env dosyasindan okunur. Ekstra bir bagimlilik
(pydantic-settings, python-dotenv) gerektirmemek icin .env'i kendimiz cok basit sekilde
parse ediyoruz.
"""
import os
from pathlib import Path

# .../backend/app/config.py -> .../backend
BACKEND_DIR = Path(__file__).resolve().parent.parent
# .../otel-foto-sistemi
PROJECT_DIR = BACKEND_DIR.parent
ENV_FILE = BACKEND_DIR / ".env"


def _load_env(path: Path) -> None:
    """Basit .env yukleyici (KEY=VALUE satirlari). Zaten tanimli ortam
    degiskenlerini EZMEZ (setdefault), boylece gercek ortam degiskenleri onceliklidir."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_env(ENV_FILE)


class Settings:
    # --- Veritabani ---
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "")

    # --- Marka / kiosk ---
    # Otel adi: kiosk basligi ve filigranda kullanilir. .env'e HOTEL_NAME yazarak degistirilebilir.
    HOTEL_NAME: str = os.environ.get("HOTEL_NAME", "OTEL ADI")

    # --- Operator girisi ---
    # Ilk aciliste DB'ye yazilan kurulum sifresi. Sonrasinda sifre PANELDEN degistirilir
    # (DB'de hash'li tutulur), bu deger artik kullanilmaz. Varsayilan kaldigi surece
    # operator panelinde "sifrenizi degistirin" uyarisi gorunur.
    OPERATOR_INITIAL_PASSWORD: str = os.environ.get("OPERATOR_INITIAL_PASSWORD", "otel123")
    # Oturum suresi: bir vardiyayi rahat kapsasin, ertesi gun tekrar giris istesin.
    SESSION_HOURS: int = int(os.environ.get("SESSION_HOURS", "12"))

    # --- Yukleme kurallari ---
    MAX_UPLOAD_MB: int = int(os.environ.get("MAX_UPLOAD_MB", "60"))  # tek foto ust siniri
    ALLOWED_IMAGE_EXTS: tuple[str, ...] = (".jpg", ".jpeg", ".png")

    # --- Veri klasorleri ---
    DATA_DIR: Path = PROJECT_DIR / "data"
    RAW_UPLOADS_DIR: Path = DATA_DIR / "raw_uploads"
    # Onbellek: filigranli galeri/tam ve filigransiz operator onizlemeleri burada tutulur
    # (orijinali her istekte decode + filigran basmamak icin). Otel adi degisince
    # settings_service otomatik temizler.
    CACHE_DIR: Path = DATA_DIR / "cache"
    # KALDIRILDI (kullanilmiyorlardi, 2026-09-03):
    #   CUSTOMER_FOLDERS_DIR -- fiziksel musteri klasoru kopyalama Faz C1'de kaldirildi;
    #                           musteri-foto iliskisi artik sadece Face tablosunda.
    #   DEBUG_OUTPUT_DIR     -- prototip (scripts/test_face_detection.py) kalintisi.
    #   EDITED_DIR           -- teslimatin tek kaynagi siparis klasoru oldugundan (delivery.py)
    #                           kullanilmiyordu. data/edited klasoru diskte DURUYOR: iki eski
    #                           OrderItem.edited_path hala oraya isaret ediyor.

    # Her siparis, editorun calismasi icin "siparis_XXXX" klasoru olarak buraya yazilir.
    # .env'de ORDERS_EXPORT_DIR ile editorun makinesine PAYLASILAN bir klasore (ya da editor
    # sunucudaysa masaustundeki "Siparisler" klasorune) yonlendirilebilir.
    ORDERS_EXPORT_DIR: Path = Path(
        os.environ.get("ORDERS_EXPORT_DIR", str(DATA_DIR / "siparisler_export"))
    )

    # Gonderime hazir paketler: operator "Gonderime Hazirla"ya basinca siparisin
    # siparis_XXXX.zip'i buraya dusuyor. Operator bu klasordeki zip'i alip istedigi
    # yolla (mail eki, WeTransfer, TransferNow...) musteriye gonderir.
    GONDERILECEK_DIR: Path = Path(
        os.environ.get("GONDERILECEK_DIR", str(DATA_DIR / "gonderilecek"))
    )

    # --- Yuz tanima ayarlari (prototipten tasindi, ilerde gercek veriyle ayarlanacak) ---
    SIMILARITY_THRESHOLD: float = 0.40   # bu esigin ustundeki benzerlik ayni kisi sayilir
    MIN_DET_SCORE: float = 0.55          # tespit guven skoru; altindakiler elenir
    MIN_FACE_WIDTH_RATIO: float = 0.06   # yuz genisligi / foto genisligi; altindakiler elenir
    MATCH_WINDOW_DAYS: int = 14          # eslesme karsilastirmasi son bu kadar gune bakar


settings = Settings()

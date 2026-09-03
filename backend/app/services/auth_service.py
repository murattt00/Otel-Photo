"""
Operator girisi: sifre dogrulama, oturum yonetimi ve FastAPI bagimliligi.

Tasarim kararlari:
- TEK paylasilan operator sifresi var (ayri kullanici hesabi yok). Otelde paneli 1-2 kisi
  kullaniyor; rol/kullanici sistemi bu olcekte gereksiz karmasa olurdu.
- Sifre DB'de (operator_auth) PBKDF2-HMAC-SHA256 + rastgele salt ile hash'li tutulur.
  Duz metin hicbir yerde saklanmaz. .env'de degil DB'de olmasinin sebebi: panelden
  degistirilebilmesi.
- Oturum = rastgele token; DB'de (operator_sessions) tutulur, tarayiciya HttpOnly cookie
  olarak verilir. DB'de tutuldugu icin sunucu yeniden baslayinca oturum dusmez, "cikis"
  da token'i gercekten gecersiz kilar.
- Kaba kuvvet denemesine karsi basit bellek-ici gecikme/kilit var (asagida _throttle).

KIOSK BU KORUMANIN DISINDADIR: kiosk musterinin onundeki makinede calisir, orada giris
ekrani olamaz. Hangi ucun acik hangisinin korumali oldugu routers/ icinde belirlenir.
"""
import hashlib
import hmac
import secrets
import threading
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.database import get_db

COOKIE_NAME = "operator_oturum"

# PBKDF2 tur sayisi. Yuksek = kaba kuvvet yavaslar; 200k modern donanimda ~0.1 sn.
_PBKDF2_ITER = 200_000

# --- Kaba kuvvet sinirlama (bellek-ici; tek sunucu icin yeterli) ---
_MAX_DENEME = 5
_KILIT_SANIYE = 60
_throttle_lock = threading.Lock()
_basarisiz: dict[str, tuple[int, datetime]] = {}  # ip -> (deneme_sayisi, son_deneme)


def _hash_password(password: str, salt: str) -> str:
    """Sifreyi salt ile PBKDF2-HMAC-SHA256'dan gecirir, hex string dondurur."""
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ITER
    ).hex()


def get_or_create_auth(db: Session) -> models.OperatorAuth:
    """Operator sifre kaydini getirir; ilk aciliste varsayilan sifreyle olusturur."""
    auth = db.query(models.OperatorAuth).first()
    if auth is None:
        salt = secrets.token_hex(16)
        auth = models.OperatorAuth(
            password_hash=_hash_password(settings.OPERATOR_INITIAL_PASSWORD, salt),
            salt=salt,
            is_default=True,
        )
        db.add(auth)
        db.commit()
        db.refresh(auth)
    return auth


def verify_password(db: Session, password: str) -> bool:
    """Verilen sifre dogru mu? (zamanlama saldirisina karsi hmac.compare_digest)"""
    auth = get_or_create_auth(db)
    return hmac.compare_digest(_hash_password(password, auth.salt), auth.password_hash)


def change_password(db: Session, yeni: str) -> None:
    """Sifreyi degistirir (yeni salt uretir) ve TUM aktif oturumlari sonlandirir.

    Oturumlarin dusurulmesi bilincli: sifre degistiginde eski cihazlarda acik kalmis
    oturumlar da kapanmali.
    """
    auth = get_or_create_auth(db)
    auth.salt = secrets.token_hex(16)
    auth.password_hash = _hash_password(yeni, auth.salt)
    auth.is_default = False
    db.query(models.OperatorSession).delete()
    db.commit()


def create_session(db: Session) -> str:
    """Yeni oturum token'i uretir, DB'ye yazar ve dondurur."""
    _temizle_suresi_dolmus(db)
    token = secrets.token_urlsafe(32)[:64]
    db.add(
        models.OperatorSession(
            token=token,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.SESSION_HOURS),
        )
    )
    db.commit()
    return token


def delete_session(db: Session, token: str | None) -> None:
    """Cikis: token'i DB'den siler."""
    if not token:
        return
    db.query(models.OperatorSession).filter(models.OperatorSession.token == token).delete()
    db.commit()


def _temizle_suresi_dolmus(db: Session) -> None:
    """Suresi gecmis oturumlari siler (tablo sismesin)."""
    db.query(models.OperatorSession).filter(
        models.OperatorSession.expires_at < datetime.now(timezone.utc)
    ).delete()


def is_logged_in(request: Request, db: Session) -> bool:
    """Istekteki cookie gecerli bir oturuma mi ait?"""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return False
    oturum = (
        db.query(models.OperatorSession)
        .filter(
            models.OperatorSession.token == token,
            models.OperatorSession.expires_at >= datetime.now(timezone.utc),
        )
        .first()
    )
    return oturum is not None


# --- Kaba kuvvet sinirlama ---

def throttle_kontrol(ip: str) -> None:
    """Cok fazla basarisiz deneme yapan IP'yi gecici kilitler (429)."""
    with _throttle_lock:
        kayit = _basarisiz.get(ip)
        if not kayit:
            return
        sayi, son = kayit
        gecen = (datetime.now(timezone.utc) - son).total_seconds()
        if sayi >= _MAX_DENEME and gecen < _KILIT_SANIYE:
            raise HTTPException(
                status_code=429,
                detail=f"Cok fazla hatali deneme. {int(_KILIT_SANIYE - gecen)} saniye sonra tekrar deneyin.",
            )
        if gecen >= _KILIT_SANIYE:
            _basarisiz.pop(ip, None)


def throttle_basarisiz(ip: str) -> None:
    with _throttle_lock:
        sayi, _ = _basarisiz.get(ip, (0, None))
        _basarisiz[ip] = (sayi + 1, datetime.now(timezone.utc))


def throttle_sifirla(ip: str) -> None:
    with _throttle_lock:
        _basarisiz.pop(ip, None)


# --- FastAPI bagimliliklari ---

def require_operator(request: Request, db: Session = Depends(get_db)) -> None:
    """Korumali uclarda kullanilir: giris yoksa 401 dondurur.

    Kullanim:  @router.post("", dependencies=[Depends(require_operator)])
    """
    if not is_logged_in(request, db):
        raise HTTPException(status_code=401, detail="Operator girisi gerekli.")


# Panele giren kisi tum musteri e-postalarini ve filigransiz orijinalleri gorebiliyor;
# bu yuzden "123456" gibi sifreler kabul edilmemeli.
_YAYGIN_SIFRELER = {
    "12345678", "123456789", "1234567890", "password", "parola", "sifre123",
    "otel1234", "qwerty123", "11111111", "admin123", "otelfoto",
}


def sifre_kurali(sifre: str) -> str | None:
    """Yeni sifre politikasi. Sorun varsa Turkce mesaj, yoksa None doner."""
    if len(sifre) < 8:
        return "Sifre en az 8 karakter olmali."
    if sifre.isdigit():
        return "Sifre sadece rakamlardan olusamaz; harf de ekleyin."
    if sifre.lower() in _YAYGIN_SIFRELER:
        return "Bu sifre cok yaygin, tahmin edilmesi kolay. Baska bir sifre secin."
    return None

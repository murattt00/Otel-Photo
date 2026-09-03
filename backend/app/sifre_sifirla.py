"""
Operator sifresini sifirlama araci -- SIFRE UNUTULURSA KURTARMA YOLU.

Panelde "sifremi unuttum" akisi YOK (tek paylasilan sifre, e-posta gonderimi yok).
Sifre unutulursa sunucuya erisimi olan kisi bu scripti calistirir.

Kullanim (backend/ klasorunden):
    ../venv/Scripts/python.exe -m app.sifre_sifirla                 -> varsayilana (otel123) doner
    ../venv/Scripts/python.exe -m app.sifre_sifirla YeniSifre123    -> belirtilen sifreyi kurar

Islem sonrasinda TUM acik oturumlar kapatilir; operatorun yeniden giris yapmasi gerekir.
Guvenlik notu: bu script sunucuda calisir, uzaktan cagrilamaz -- makineye fiziksel/uzak
masaustu erisimi olan kisi zaten DB'ye de erisebilir, dolayisiyla ek risk getirmez.
"""
import secrets
import sys

from app import models
from app.config import settings
from app.database import SessionLocal
from app.services import auth_service


def main() -> None:
    yeni = sys.argv[1] if len(sys.argv) > 1 else settings.OPERATOR_INITIAL_PASSWORD
    varsayilana_donuyor = len(sys.argv) <= 1

    hata = auth_service.sifre_kurali(yeni)
    if hata and not varsayilana_donuyor:
        print(f"HATA: {hata}")
        sys.exit(1)

    db = SessionLocal()
    try:
        auth = db.query(models.OperatorAuth).first()
        salt = secrets.token_hex(16)
        if auth is None:
            auth = models.OperatorAuth(
                password_hash=auth_service._hash_password(yeni, salt),
                salt=salt,
                is_default=varsayilana_donuyor,
            )
            db.add(auth)
        else:
            auth.salt = salt
            auth.password_hash = auth_service._hash_password(yeni, salt)
            # Varsayilana donduysak panelde tekrar "sifrenizi degistirin" uyarisi ciksin
            auth.is_default = varsayilana_donuyor

        silinen = db.query(models.OperatorSession).delete()
        db.commit()
    finally:
        db.close()

    print("Operator sifresi sifirlandi.")
    print(f"  Yeni sifre     : {yeni}")
    print(f"  Kapatilan oturum: {silinen}")
    if varsayilana_donuyor:
        print("  UYARI: kurulum varsayilani kuruldu -- panele girip hemen degistirin.")


if __name__ == "__main__":
    main()

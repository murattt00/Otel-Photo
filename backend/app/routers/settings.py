"""
Ayarlar: klasor yollarini operator panelinden yonetme.

Yollar SUNUCUDA cozulur, operatorun bilgisayarinda degil. Ayrinti ve UNC yolu notu:
app/services/settings_service.py dosyasinin basinda.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import settings_service
from app.services.auth_service import require_operator

router = APIRouter(
    prefix="/settings",
    tags=["ayarlar"],
    dependencies=[Depends(require_operator)],  # tum ayar uclari operator girisi ister
)


@router.get("/klasorler")
def klasorleri_listele():
    """Ayarlanabilir klasorleri, mevcut degerlerini ve diskteki durumlarini dondurur."""
    return settings_service.tum_durumlar()


@router.post("/klasorler/test")
def klasor_test(veri: dict):
    """Yolu KAYDETMEDEN dener: olusturulabiliyor mu, yazilabiliyor mu?"""
    return settings_service.dogrula(veri.get("yol", ""))


@router.patch("/klasorler/{anahtar}")
def klasor_ayarla(anahtar: str, veri: dict, db: Session = Depends(get_db)):
    """Klasor yolunu kaydeder. Yazilamiyorsa 400 ile reddeder (bozuk ayar kaydedilmesin)."""
    sonuc = settings_service.ayarla(db, anahtar, veri.get("yol", ""))
    if not sonuc["gecerli"]:
        raise HTTPException(status_code=400, detail=sonuc["mesaj"])
    return sonuc


@router.delete("/klasorler/{anahtar}")
def klasor_sifirla(anahtar: str, db: Session = Depends(get_db)):
    """Ayari siler -> .env/varsayilan degere doner."""
    if anahtar not in settings_service.KLASORLER:
        raise HTTPException(status_code=404, detail="Bilinmeyen ayar.")
    return settings_service.sifirla(db, anahtar)

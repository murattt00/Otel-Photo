"""
Operator girisi: giris / cikis / sifre degistirme.

Tek paylasilan sifre + cookie tabanli oturum. Ayrintili tasarim notu:
app/services/auth_service.py dosyasinin basinda.

NOT (cookie secure bayragi): sistem otel LAN'inda duz HTTP uzerinden calisiyor. Cookie'ye
secure=True konsaydi tarayici onu HTTPS disinda hic gondermezdi ve giris hic calismazdi.
Sisteme HTTPS eklenirse secure=True yapilmalidir.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app import schemas
from app.config import settings
from app.database import get_db
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["operator-giris"])


@router.get("/durum", response_model=schemas.AuthDurum)
def auth_durum(request: Request, db: Session = Depends(get_db)):
    """Giris yapilmis mi + hala varsayilan sifre mi kullaniliyor?

    Aciktir (giris gerektirmez): panel acilirken giris ekrani mi yoksa dashboard mu
    gosterilecegine bu ucun cevabina gore karar verir.
    """
    auth = auth_service.get_or_create_auth(db)
    return schemas.AuthDurum(
        giris=auth_service.is_logged_in(request, db),
        varsayilan_sifre=auth.is_default,
    )


@router.post("/login", response_model=schemas.AuthDurum)
def login(data: schemas.LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """Sifreyi dogrular, oturum cookie'si verir."""
    ip = request.client.host if request.client else "bilinmiyor"
    auth_service.throttle_kontrol(ip)  # cok denemede 429

    if not auth_service.verify_password(db, data.sifre):
        auth_service.throttle_basarisiz(ip)
        raise HTTPException(status_code=401, detail="Sifre hatali.")

    auth_service.throttle_sifirla(ip)
    token = auth_service.create_session(db)
    response.set_cookie(
        key=auth_service.COOKIE_NAME,
        value=token,
        httponly=True,          # JavaScript okuyamaz (XSS'te calinmasin)
        samesite="lax",
        max_age=settings.SESSION_HOURS * 3600,
        path="/",
    )
    auth = auth_service.get_or_create_auth(db)
    return schemas.AuthDurum(giris=True, varsayilan_sifre=auth.is_default)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    """Cikis: token DB'den silinir, cookie temizlenir."""
    auth_service.delete_session(db, request.cookies.get(auth_service.COOKIE_NAME))
    response.delete_cookie(auth_service.COOKIE_NAME, path="/")
    return {"mesaj": "Cikis yapildi."}


@router.post("/sifre-degistir", dependencies=[Depends(auth_service.require_operator)])
def sifre_degistir(
    data: schemas.SifreDegistirIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Operator kendi sifresini degistirir (mevcut sifreyi bilmek zorunda).

    Sifre degisince TUM oturumlar dusurulur; hemen ardindan bu tarayici icin yeni bir
    oturum acilir ki operator degisiklikten sonra panelden atilmasin.
    """
    if not auth_service.verify_password(db, data.mevcut_sifre):
        raise HTTPException(status_code=401, detail="Mevcut sifre hatali.")
    if data.yeni_sifre == data.mevcut_sifre:
        raise HTTPException(status_code=400, detail="Yeni sifre eskisiyle ayni olamaz.")

    hata = auth_service.sifre_kurali(data.yeni_sifre)
    if hata:
        raise HTTPException(status_code=400, detail=hata)

    auth_service.change_password(db, data.yeni_sifre)

    token = auth_service.create_session(db)
    response.set_cookie(
        key=auth_service.COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=settings.SESSION_HOURS * 3600,
        path="/",
    )
    return {"mesaj": "Sifre degistirildi."}

"""
Pydantic semalari: API'nin girdi/cikti veri sekilleri.

SQLAlchemy modelleri (models.py) veritabani tablolarini, buradaki semalar ise
API uzerinden gidip gelen JSON'un seklini tanimlar. from_attributes=True sayesinde
ORM nesnelerinden dogrudan uretilebilirler.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---- Fotografci ----
class PhotographerCreate(BaseModel):
    name: str
    username: str


class PhotographerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    username: str
    created_at: datetime


# ---- Yukleme sonucu ----
class UploadResult(BaseModel):
    yuklenen: int
    atlanan: int = 0                    # tur/boyut nedeniyle atlanan dosya sayisi
    atlanan_dosyalar: list[str] = []    # atlananlarin adlari (kisa liste)
    foto_idleri: list[int]
    mesaj: str


# ---- Klasor ingestion (sunucudaki klasorden isleme) ----
class IngestRequest(BaseModel):
    photographer_id: int
    folder: str  # sunucudaki klasorun tam yolu


class IngestResult(BaseModel):
    bulunan: int   # klasorde bulunan gecerli foto sayisi
    eklenen: int   # kuyruga eklenen
    atlanan: int   # cok buyuk/gecersiz
    mesaj: str


# ---- Foto ----
class PhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filename: str
    status: str            # pending / processing / done / error
    is_processed: bool
    uploaded_by_id: int | None


# ---- Musteri (yuz grubu / klasor) ----
class CustomerOut(BaseModel):
    id: int
    folder_code: str
    is_active: bool
    foto_sayisi: int


# ---- Urun / Albuw ----
class ProductCreate(BaseModel):
    name: str
    price: float
    photo_count: int | None = None  # None = serbest secim
    description: str | None = None
    is_active: bool = True


class ProductUpdate(BaseModel):
    # Hepsi opsiyonel; sadece gonderilen alanlar guncellenir
    name: str | None = None
    price: float | None = None
    photo_count: int | None = None
    description: str | None = None
    is_active: bool | None = None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    price: float
    photo_count: int | None
    description: str | None
    is_active: bool


# ---- Siparis (sepet) ----
class OrderItemCreate(BaseModel):
    photo_id: int
    note: str | None = None  # bu fotoya ozel not ( or. photoshop istegi)


class OrderCreate(BaseModel):
    customer_id: int
    product_id: int | None = None  # secilen albuw/urun turu
    # E-posta ZORUNLU (basit format kontrolu; email-validator bagimliligi eklemiyoruz)
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    note: str | None = None
    items: list[OrderItemCreate]


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    photo_id: int
    note: str | None
    edited: bool = False  # operator duzenlenmis versiyonu yukledi mi


class OrderOut(BaseModel):
    id: int
    customer_id: int
    customer_folder: str | None
    product_id: int | None
    product_name: str | None
    email: str | None
    status: str
    note: str | None
    created_at: datetime
    revised: bool = False  # musteri sonradan duzenledi mi ("duzenlendi" rozeti)
    foto_sayisi: int
    toplam_fiyat: float | None = None  # serbest: foto basi x foto sayisi, albuw: sabit
    items: list[OrderItemOut] = []


class OrderUpdate(BaseModel):
    """Mevcut bir siparisi (sepeti) guncelleme. customer_id degismez."""
    product_id: int | None = None
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    note: str | None = None
    items: list[OrderItemCreate]


class OrderStatusUpdate(BaseModel):
    status: str  # yeni / hazir / teslim


# ---- Kiosk ----
class KioskPhoto(BaseModel):
    id: int
    url: str  # filigranli gorsel adresi


class KioskScanResult(BaseModel):
    eslesme: bool
    mesaj: str
    sebep: str | None = None  # "yuz_bulunamadi" | "musteri_bulunamadi" | None
    musteri_id: int | None = None
    benzerlik: float | None = None
    fotolar: list[KioskPhoto] = []


# ---- Operator girisi ----
class LoginIn(BaseModel):
    sifre: str


class SifreDegistirIn(BaseModel):
    mevcut_sifre: str
    yeni_sifre: str = Field(..., min_length=6, max_length=128)


class AuthDurum(BaseModel):
    giris: bool                 # su an giris yapilmis mi
    varsayilan_sifre: bool      # hala kurulum varsayilani mi kullaniliyor (uyari icin)

"""
Veritabani modelleri (SQLAlchemy 2.0).

Temel varliklar ve iliskiler:
- Photographer : sisteme foto yukleyen personel / fotografci
- Customer     : bir YUZ GRUBU = bir musteri klasoru (musteri_XXX). Ayni kisiye ait
                 fotograflarin toplandigi mantiksal klasor. (Kayitli birey degil, yuz kumesi.)
- Photo        : sisteme yuklenen tek bir fotograf dosyasi
- Face         : bir fotografta tespit edilen TEK bir yuz + 512 boyutlu embedding.
                 Bir foto birden fazla yuz icerebilir; her yuz bir Customer'a baglanir.
                 (Photo <-> Customer arasindaki kopru budur.)
- Order        : bir musterinin kioskta olusturdugu siparis
- OrderItem    : siparise eklenen tek bir foto (+ o fotoya ozel not)

Not: Yuz embedding'leri (512 boyutlu float32 vektor) LargeBinary olarak, numpy'nin
.tobytes() ciktisiyla saklanir. Benzerlik karsilastirmasi (cosine) simdilik Python/numpy
tarafinda yapilir -- bu olcekte (tek otel, 2 haftalik pencere) fazlasiyla yeterli.
Ilerde olcek buyurse pgvector'e gecilebilir.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Photographer(Base):
    """Sisteme foto yukleyen personel/fotografci. (Auth ileride eklenecek.)"""
    __tablename__ = "photographers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    username: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    photos: Mapped[list["Photo"]] = relationship(back_populates="uploaded_by")


class Customer(Base):
    """Bir yuz grubu / musteri klasoru (musteri_XXX)."""
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    folder_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)  # ornek: musteri_001
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Artimli centroid ( olcek icin): bu musterinin tum yuzlerinin ortalama embedding'i +
    # yuz sayisi. Her yeni yuzde guncellenir; boylece eslestirme her seferinde tum yuzleri
    # tekrar hesaplamak zorunda kalmaz (N^2 -> O(musteri sayisi)).
    centroid: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)  # numpy float32 512-dim
    face_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # updated_at = son yuz eklenme zamani; 14 gunluk ESLESTIRME penceresi bununla belirlenir.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    faces: Mapped[list["Face"]] = relationship(back_populates="customer")
    orders: Mapped[list["Order"]] = relationship(back_populates="customer")


class Photo(Base):
    """Sisteme yuklenen tek bir fotograf dosyasi."""
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))       # orijinal dosya adi
    stored_path: Mapped[str] = mapped_column(String(500))    # diskteki kayit yolu
    uploaded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("photographers.id"), nullable=True
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False)  # (geriye donuk) status=='done' esdegeri
    # Kuyruk durumu: pending (islenmeyi bekliyor) / processing / done / error
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)  # islemede hata olursa mesaj

    uploaded_by: Mapped["Photographer | None"] = relationship(back_populates="photos")
    faces: Mapped[list["Face"]] = relationship(
        back_populates="photo", cascade="all, delete-orphan"
    )


class Face(Base):
    """Bir fotograftaki tek bir yuz + embedding. Photo <-> Customer koprusu."""
    __tablename__ = "faces"

    id: Mapped[int] = mapped_column(primary_key=True)
    photo_id: Mapped[int] = mapped_column(
        ForeignKey("photos.id", ondelete="CASCADE"), index=True
    )
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id"), nullable=True, index=True
    )
    embedding: Mapped[bytes] = mapped_column(LargeBinary)  # numpy float32 512-dim .tobytes()
    det_score: Mapped[float] = mapped_column(Float)
    bbox: Mapped[dict] = mapped_column(JSON)  # {"x1":..,"y1":..,"x2":..,"y2":..}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    photo: Mapped["Photo"] = relationship(back_populates="faces")
    customer: Mapped["Customer | None"] = relationship(back_populates="faces")


class Order(Base):
    """Bir musterinin kioskta olusturdugu siparis (sepet).

    status: "yeni" (operatore dustu) -> "hazir" (basildi/hazirlandi) -> "teslim" (verildi).
    product_id: secilen albuw/urun turu (None = urun secilmeden serbest -- normalde set edilir).
    email: musterinin e-postasi (dijital kopya/iletisim icin).
    """
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="yeni")  # yeni / hazir (/ teslim ileride)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)    # siparis geneli not
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Musteri siparisi SONRADAN duzenlerse buraya zaman yazilir; operator "duzenlendi" rozetini
    # bununla gosterir ve siparis "yeni" sekmesine geri duser.
    revised_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer: Mapped["Customer"] = relationship(back_populates="orders")
    product: Mapped["Product | None"] = relationship()
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class Product(Base):
    """Operatorun tanimladigi satis urunu / albuw turu.

    Ornekler: "5'lik Albuw" (photo_count=5, price=300), "10'luk Paket" (photo_count=10,
    price=500), "Tek Baski" (photo_count=1, price=50), "Serbest Secim" (photo_count=None).
    photo_count=None ise musteri istedigi kadar foto secebilir (serbest mod).
    """
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float] = mapped_column(Float)  # TL
    photo_count: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = serbest/sinirsiz
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # pasifse kioskta gorunmez
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OrderItem(Base):
    """Siparise eklenen tek bir foto ve o fotoya ozel not."""
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    photo_id: Mapped[int] = mapped_column(ForeignKey("photos.id"), index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)  # bu fotoya ozel not
    # Operator photoshop yapip yukledigi duzenlenmis versiyonun dosya yolu (orijinal degismez).
    # Teslimatta edited_path varsa o, yoksa orijinal (Photo.stored_path) kullanilir.
    edited_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    order: Mapped["Order"] = relationship(back_populates="items")
    photo: Mapped["Photo"] = relationship()


class OperatorAuth(Base):
    """Operator panelinin TEK paylasilan sifresi (ayri kullanici hesabi yok).

    Neden .env'de degil DB'de: sifre panelden degistirilebilsin diye. .env'de tutulsaydi
    degistirmek sunucudaki dosyayi yeniden yazmayi gerektirirdi.
    Sifre asla duz metin saklanmaz: PBKDF2-HMAC-SHA256 + kayda ozel rastgele salt.
    Tablo tek satir tutar (id=1); ilk aciliste varsayilan sifreyle olusturulur.
    """
    __tablename__ = "operator_auth"

    id: Mapped[int] = mapped_column(primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    salt: Mapped[str] = mapped_column(String(64))
    # Hala kurulum varsayilani mi kullaniliyor? Panelde "sifrenizi degistirin" uyarisi icin.
    is_default: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OperatorSession(Base):
    """Giris yapmis operator oturumu -- cookie'deki token'in veritabani karsiligi.

    Bellekte degil DB'de tutulur ki: (1) sunucu yeniden baslayinca operator tekrar giris
    yapmak zorunda kalmasin, (2) "cikis" gercekten token'i gecersiz kilsin.
    """
    __tablename__ = "operator_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AppSetting(Base):
    """Calisirken degistirilebilen ayarlar (anahtar/deger).

    Neden DB: klasor yollari gibi ayarlar operator panelinden degistirilebilsin diye.
    .env'de kalsalardi degistirmek icin sunucu dosyasini duzenleyip yeniden baslatmak
    gerekirdi. Oncelik: DB degeri > .env > kod icindeki varsayilan.
    """
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(String(500))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

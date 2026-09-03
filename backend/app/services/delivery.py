"""
Teslim paketi hazirlama: siparis klasorunu zip'leyip "gonderilecek" klasorune koyar.

ONEMLI TASARIM KARARI -- ILETISIM KOPUKLUGUNUN COZUMU:
Sistemde iki ayri duzenleme yolu vardi ve birbirlerinden habersizlerdi:
  (A) operator panelden duzenlenmis fotoyu yukler  -> OrderItem.edited_path
  (B) editor siparis_XXXX klasorunde dosyayi YERINDE duzenler -> sistem bunu hic gormezdi
Eski zip ucu (/orders/{id}/download) sadece (A)'ya bakiyordu; editor (B) ile calisirsa
musteriye DUZENLENMEMIS orijinaller gidiyordu, sessizce.

Cozum: teslimatin TEK KAYNAGI artik siparis klasorudur (ORDERS_EXPORT_DIR/siparis_XXXX).
Editor orada ne biraktiysa musteriye o gider. Panelden yukleme (A) yolu da bu klasore
yazdigi surece ayni yere akar -- iki yol tek noktada bulusur.

Ayrica her dosyanin GERCEKTEN duzenlenip duzenlenmedigi tespit edilir: export sirasinda
shutil.copy2 kullanildigi icin kopya, orijinalin boyutunu ve degistirilme zamanini aynen
tasir. Ikisinden biri farkliysa dosyaya dokunulmus demektir. Boylece operator "hic
duzenlenmemis" bir siparisi yanlislikla gonderemez -- panel uyarir.
"""
import os
import zipfile
from pathlib import Path

from sqlalchemy.orm import Session

from app import models
from app.services.order_export import export_order, order_folder
from app.services.settings_service import klasor

# Pakete girecek dosya turleri (editor PSD/tmp birakirsa musteriye gitmesin)
_GONDERILEBILIR = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}

# Siparisten cikarilan fotolarin tasindigi alt klasor (export_order tarafindan kullanilir)
KALDIRILAN_ALT_KLASOR = "_kaldirilan"


def paket_yolu(order_id: int) -> Path:
    """Bir siparisin gonderim zip'inin tam yolu."""
    return klasor("gonderilecek_klasoru") / f"siparis_{order_id:04d}.zip"


def _gonderilecek_dosyalar(siparis_klasoru: Path) -> list[Path]:
    """Siparis klasorundeki gonderilebilir gorselleri (bilgi dosyasi ve _kaldirilan haric)."""
    if not siparis_klasoru.exists():
        return []
    return sorted(
        f for f in siparis_klasoru.iterdir()
        if f.is_file()
        and f.suffix.lower() in _GONDERILEBILIR
        and not f.name.startswith("_")
    )


def _duzenlendi_mi(db: Session, order: models.Order, dosya: Path) -> bool:
    """Dosya export'tan sonra degistirilmis mi?

    export_order shutil.copy2 ile kopyaladigi icin dokunulmamis kopya, orijinalle ayni
    boyut ve ayni mtime'a sahiptir. Herhangi biri farkliysa editor dosyayi islemistir.
    Orijinali bulunamayan dosya (editorun ekledigi yeni dosya) 'duzenlenmis' sayilir.
    """
    for it in order.items:
        if it.photo is None:
            continue
        # Dosya adi "01_foto{photo_id}.uzanti" bicimindedir
        if f"foto{it.photo.id}" not in dosya.stem:
            continue
        try:
            o = os.stat(it.photo.stored_path)
            k = dosya.stat()
        except OSError:
            return True
        return o.st_size != k.st_size or int(o.st_mtime) != int(k.st_mtime)
    return True


def paket_hazirla(db: Session, order: models.Order) -> dict:
    """Siparis klasorunu zip'leyip gonderilecek klasorune koyar.

    Donen sozlukte operator panelinin gosterdigi her sey var: zip adi/yolu, foto sayisi,
    boyut ve KAC FOTONUN HENUZ DUZENLENMEDIGI (uyari icin).
    """
    # Paketlemeden ONCE klasoru tazele: siparise ait olup eksik kalan foto varsa kopyalanir,
    # siparisten cikarilmis bayat dosyalar _kaldirilan/ altina tasinir. Editorun duzenledigi
    # dosyalar EZILMEZ. Boylece pakete her zaman siparisin GUNCEL hali girer.
    export_order(order.id)

    siparis_klasoru = order_folder(order.id)
    dosyalar = _gonderilecek_dosyalar(siparis_klasoru)

    if not dosyalar:
        return {
            "hazir": False,
            "mesaj": f"Siparis klasoru bos ya da bulunamadi: {siparis_klasoru}",
            "klasor": str(siparis_klasoru),
        }

    duzenlenmemis = [f.name for f in dosyalar if not _duzenlendi_mi(db, order, f)]

    hedef = klasor("gonderilecek_klasoru")
    hedef.mkdir(parents=True, exist_ok=True)
    zip_yolu = paket_yolu(order.id)

    # JPEG zaten sikisik -> ZIP_STORED (sikistirma bosuna CPU yakar)
    with zipfile.ZipFile(zip_yolu, "w", zipfile.ZIP_STORED) as z:
        for f in dosyalar:
            z.write(f, arcname=f.name)

    boyut = zip_yolu.stat().st_size
    return {
        "hazir": True,
        "zip_adi": zip_yolu.name,
        "zip_yolu": str(zip_yolu),
        "klasor": str(hedef),
        "foto_sayisi": len(dosyalar),
        "boyut_mb": round(boyut / 1024 / 1024, 1),
        "duzenlenmemis": duzenlenmemis,
        "email": order.email,
        "mesaj": f"{len(dosyalar)} fotograf paketlendi.",
    }


def paket_durum(order_id: int) -> dict:
    """Bu siparis icin daha once paket hazirlanmis mi? (panelde rozet gostermek icin)"""
    z = paket_yolu(order_id)
    if not z.exists():
        return {"var": False}
    st = z.stat()
    return {
        "var": True,
        "zip_adi": z.name,
        "boyut_mb": round(st.st_size / 1024 / 1024, 1),
        "hazirlanma": int(st.st_mtime),
    }

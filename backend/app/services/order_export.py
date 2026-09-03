"""
Siparis klasoru export'u.

Editorler klasor bazli calisiyor: masaustundeki "Siparisler" klasorunde her siparis
"siparis_XXXX" alt klasoru olarak duruyor; editor numarayla bulup photoshop yapip TransferNow
ile gonderiyor. Teker teker indir/yukle onlar icin cok yavas.

Bu servis, her siparis icin ORDERS_EXPORT_DIR altinda bir "siparis_XXXX" klasoru olusturur:
- Siparisteki fotograflarin (orijinal full-res) kopyalari
- Yapilacak duzenlemeleri + e-posta + paket + toplami iceren bir bilgi dosyasi (.txt)

Onerilen kurulum: ORDERS_EXPORT_DIR sunucuda olsun, editorun makinesine Windows paylasimi ile
baglansin. Boylece editor yerinde duzenler, sunucu da nihai dosyalara sahip olur (ileride
otomatik gonderme icin gerekli).

TAHRIP ETMEZ: zaten var olan dosyanin uzerine yazmaz (editorun duzenlemesini korur); sadece
eksik fotolari ekler ve bilgi dosyasini gunceller.
"""
from pathlib import Path
import shutil

from app import models
from app.services.settings_service import klasor
from app.database import SessionLocal


def order_folder(order_id: int) -> Path:
    return klasor("siparis_klasoru") / f"siparis_{order_id:04d}"


def _total(order: models.Order) -> float | None:
    if order.product is None:
        return None
    if order.product.photo_count is None:  # foto basi
        return round(order.product.price * len(order.items), 2)
    return order.product.price


def _ayikla(folder: Path, beklenen: set[str]) -> None:
    """Siparise ait olmayan gorselleri _kaldirilan/ alt klasorune tasir."""
    for f in folder.iterdir():
        if not f.is_file() or f.name.startswith("_") or f.name in beklenen:
            continue
        if f.suffix.lower() not in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}:
            continue
        hedef_klasor = folder / "_kaldirilan"
        hedef_klasor.mkdir(exist_ok=True)
        try:
            f.replace(hedef_klasor / f.name)
        except OSError:
            pass


def export_order(order_id: int) -> str | None:
    """Siparisi ORDERS_EXPORT_DIR/siparis_XXXX klasorune yazar. Kendi DB oturumunu acar
    (arka plan gorevi olarak da cagrilabilsin)."""
    db = SessionLocal()
    try:
        order = db.get(models.Order, order_id)
        if order is None:
            return None

        folder = order_folder(order_id)
        folder.mkdir(parents=True, exist_ok=True)

        items = sorted(order.items, key=lambda x: x.id)
        satirlar = [
            f"SIPARIS #{order.id}",
            f"Tarih   : {order.created_at:%Y-%m-%d %H:%M}",
            f"E-posta : {order.email or '-'}",
            f"Paket   : {order.product.name if order.product else '-'}"
            + (f"  (Toplam: {_total(order):g} TL)" if _total(order) is not None else ""),
            "",
            "FOTOGRAFLAR ve YAPILACAK DUZENLEMELER:",
        ]

        beklenen: set[str] = set()

        for i, it in enumerate(items, 1):
            photo = it.photo
            if photo is None:
                continue
            ext = Path(photo.stored_path).suffix or ".jpg"
            name = f"{i:02d}_foto{photo.id}{ext}"
            beklenen.add(name)
            dst = folder / name
            # Var olan dosyayi EZME (editorun duzenlemesini koru)
            if not dst.exists():
                try:
                    shutil.copy2(photo.stored_path, dst)
                except OSError:
                    pass
            not_txt = f"NOT: {it.note}" if it.note else "(not yok)"
            satirlar.append(f"  {name}  ->  {not_txt}")

        # Musteri siparisi duzenleyip foto CIKARDIYSA, o dosya klasorde kalmasin --
        # yoksa editor artik siparise ait olmayan fotoyu duzenler ve teslim paketine girer.
        # SILMIYORUZ (editorun emegi kaybolmasin): _kaldirilan/ alt klasorune tasiyoruz.
        _ayikla(folder, beklenen)

        (folder / f"_SIPARIS_{order.id}_BILGI.txt").write_text(
            "\n".join(satirlar) + "\n", encoding="utf-8"
        )
        return str(folder)
    finally:
        db.close()

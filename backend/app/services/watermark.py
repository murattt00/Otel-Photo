"""
Filigran servisi.

Kioskta gosterilen fotograflara, capraz tekrar eden yari saydam bir "OTEL ADI - ONIZLEME"
yazisi basar. Amac: musteri odeme yapmadan ekrani fotograflayip giderse bile fotografin
satilabilir kalitede olmamasi.

Filigran, istek aninda (on-the-fly) uygulanir; orijinal dosya degistirilmez.
"""
import io
import math

from PIL import Image, ImageDraw, ImageFont

# Kiosk galerisinde tam cozunurluk gerekmez; hem hiz hem koruma icin kuculturuz.
_GALLERY_MAX_SIZE = 1400


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Windows sistem fontunu dener (Turkce karakter + boyut kontrolu icin), yoksa varsayilan."""
    for path in ("C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def watermark_image(image_path: str, hotel_name: str, max_size: int | None = _GALLERY_MAX_SIZE) -> bytes:
    """Fotografa capraz tekrar eden filigran basar, JPEG baytlari dondurur.

    max_size: en uzun kenar bu piksele kuculutulur. None ise kuculutulmez (tam boyut,
    lightbox/inceleme icin). Filigran her iki durumda da uygulanir.
    """
    img = Image.open(image_path).convert("RGB")
    if max_size is not None:
        img.thumbnail((max_size, max_size))

    text = f"{hotel_name}   •   ONIZLEME"
    font_size = max(18, img.width // 22)
    font = _load_font(font_size)

    # Capraz desen icin: goruntuden buyuk kare bir katmana metni doseyip katmani dondur
    diag = int(math.hypot(img.width, img.height))
    layer = Image.new("RGBA", (diag, diag), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    step_x = text_w + font_size * 3
    step_y = text_h + font_size * 3

    for y in range(0, diag, step_y):
        for x in range(0, diag, step_x):
            draw.text((x, y), text, font=font, fill=(255, 255, 255, 70))

    layer = layer.rotate(30, expand=False)

    # Katmani goruntu ortasina hizala
    left = (layer.width - img.width) // 2
    top = (layer.height - img.height) // 2
    layer = layer.crop((left, top, left + img.width, top + img.height))

    watermarked = Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")

    buf = io.BytesIO()
    watermarked.save(buf, format="JPEG", quality=82)
    return buf.getvalue()


def resized_jpeg(image_path: str, max_size: int = 1000) -> bytes:
    """Filigransiz kucultulmus JPEG (operator onizlemesi icin). Orijinali bozmaz."""
    img = Image.open(image_path).convert("RGB")
    img.thumbnail((max_size, max_size))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()

# Otel Fotoğrafçıları Yönetim Sistemi

## Proje Vizyonu

Otel/tatil köylerinde çalışan fotoğrafçılar için yüz tanıma tabanlı foto yönetim ve sipariş sistemi.

Akış: fotoğrafçılar gün boyu çekim yapar → hafıza kartından sisteme foto yükler → sistem yeni
fotoları tarar, yüz tanıma modeliyle embedding çıkarır → **son 2 haftalık pencere** içinde mevcut
müşteri klasörleriyle karşılaştırır → eşleşme varsa o klasöre, yoksa yeni açılan klasöre ekler →
müşteri kasadaki ayrı bir bilgisayarda yüzünü taratır → kendi yüzüyle eşleşen klasördeki fotoları
görür → istediklerini seçip isteğe bağlı not ekleyerek her foto için sipariş oluşturur → sipariş,
fotoğrafçıların foto yüklediği bilgisayara düşer.

Ticari değerlendirme, risk analizi (özellikle KVKK/biyometrik veri), süre tahmini ve teknoloji
seçimi tartışması 2026-07-08 tarihli sohbette yapıldı — özet: fikir sağlam ve satılabilir, model
eğitmeye gerek yok (pretrained InsightFace yeterli), MVP için kalan iş ~6-10 hafta.

## Nasıl Çalıştırılır (backend)

```
cd otel-foto-sistemi/backend
../venv/Scripts/python.exe -m uvicorn app.main:app --reload    # sunucu: http://localhost:8000
```
- Tarayıcı doğrulama: `http://localhost:8000/docs` (Swagger UI), `/health`, `/health/db`.
- Migration: `cd backend && ../venv/Scripts/alembic.exe upgrade head` (yeni model değişikliğinde
  önce `alembic revision --autogenerate -m "..."`).
- DB bilgileri `.env`'de: `otel_foto_db` / `otel_foto_user`. Postgres superuser: `postgres`.

## Mevcut Durum (yapılan)

### Aşama 0 — Backend iskeleti (TAMAMLANDI, uçtan uca doğrulandı)
- `backend/app/config.py` — `.env`'i (harici bağımlılık olmadan) parse eder; `DATABASE_URL`,
  veri klasör yolları ve yüz tanıma eşikleri (`SIMILARITY_THRESHOLD=0.40`, `MIN_DET_SCORE=0.55`,
  `MIN_FACE_WIDTH_RATIO=0.06`, `MATCH_WINDOW_DAYS=14`) tek yerde.
- `backend/app/database.py` — SQLAlchemy `engine`, `SessionLocal`, `Base`, `get_db` dependency.
- `backend/app/models.py` — 6 model: `Photographer`, `Customer` (yüz grubu/klasör, `folder_code`),
  `Photo`, `Face` (photo↔customer köprüsü, `embedding` **LargeBinary** olarak), `Order`,
  `OrderItem`. Bir foto çok yüz → çok Customer.
- `backend/app/main.py` + `backend/app/routers/health.py` — FastAPI app, `/`, `/health`, `/health/db`.
- `backend/alembic/` + `alembic.ini` — migration altyapısı; `env.py` `app.config`'ten
  DATABASE_URL ve `Base.metadata`'yı kullanır. İlk migration uygulandı, 6 tablo Postgres'te oluştu.
- `backend/requirements.txt`, `otel-foto-sistemi/.gitignore` eklendi.
- **PostgreSQL 17.5** çalışıyor; `otel_foto_db` + `otel_foto_user` hazır ve bağlantı doğrulandı.

### Aşama 1 — Foto yükleme + otomatik yüz sınıflandırma (TAMAMLANDI, uçtan uca doğrulandı)
Prototip mantığı gerçek API + DB + arka plan işleme olarak servisleştirildi. 32 örnek fotoyla
test edildi → **12 müşteri klasörü** (prototiple aynı), grup fotoları doğru şekilde birden çok
klasöre giriyor.
- `backend/app/schemas.py` — Pydantic giriş/çıkış şemaları.
- `backend/app/services/face_service.py` — InsightFace `buffalo_l` sarmalayıcı; model lazy
  singleton (bir kez yüklenir), `detect_faces(path)` → filtrelenmiş yüzler (embedding, det_score,
  bbox). Unicode yol için `cv2.imdecode` kullanılıyor.
- `backend/app/services/matching_service.py` — `find_or_create_customer(db, embedding)`: son
  `MATCH_WINDOW_DAYS` gündeki aktif müşteri yüzlerinin centroid'iyle cosine karşılaştırır,
  eşik üstü en iyisine atar, yoksa `musteri_XXX` açar. Tümü DB üzerinden.
- `backend/app/services/classification.py` — `process_photos(photo_ids)`: arka plan görevi;
  her foto için yüz tespiti → müşteri eşleştirme → `Face` kaydı → müşteri klasörüne kopya.
- Router'lar: `photographers.py` (POST/GET), `photos.py` (`POST /photos/upload` çoklu dosya +
  `photographer_id`, işlemi BackgroundTasks'e atar; `GET /photos`), `customers.py`
  (`GET /customers` foto sayısıyla, `GET /customers/{id}/photos`).
- **Not (Starlette 1.3.1 tuhaflığı):** `include_router` route'ları `app.routes` düz listesinde
  APIRoute olarak DEĞİL, `_IncludedRouter` olarak ekler. Route'lar /docs ve istek anında düzgün
  çalışır — route sayarken kafa karıştırır, panik yapma.

### Aşama 2A — Kiosk çekirdeği (TAMAMLANDI, backend doğrulandı)
Müşteri ekranı: karşılama → kamera → yüz tara → eşleşen fotolar (filigranlı galeri).
- `backend/app/static/index.html` — tek dosyalık kiosk arayüzü (canlı/tatil teması, gradyan,
  dokunmatik-dostu). 3 ekran: karşılama (BAŞLA), kamera (webcam + "yüzünüzü yaklaştırın" + Tara),
  sonuç (galeri, tıklayarak seçim + alt aksiyon çubuğu). Foto seçim → sepet akışı 2C'de gelecek
  (şu an seçim görsel + "yakında" toast'u). Marka renkleri CSS değişkeninde (kolay yeniden tema).
- `backend/app/routers/kiosk.py` — `GET /kiosk` (sayfa), `GET /kiosk/info` (otel adı),
  `POST /kiosk/scan` (webcam karesi → en büyük yüz → `find_best_customer` → filigranlı foto listesi).
- `backend/app/services/watermark.py` — Pillow ile çapraz tekrar eden "OTEL ADI • ÖNİZLEME"
  filigranı, istek anında (orijinali bozmaz), galeri için 1400px'e küçültür. Doğrulandı (görsel OK).
- `backend/app/routers/photos.py` → `GET /photos/{id}/image?filigran=true|false&boyut=galeri|tam`
  — filigranlı (kiosk) / orijinal görsel; `boyut=tam` tam çözünürlük (lightbox), `galeri` max 1400px.
- **Lightbox (büyütme/inceleme):** galeride fotoya dokununca tam boyut (yine filigranlı) açılır;
  ileri/geri (ok tuşları da), köşedeki ✓ ile hızlı seçim, lightbox içinde Seç/Kaldır. Aynı pozdan
  birden fazla varken müşteri inceleyip seçsin diye. `watermark_image(max_size=None)` = tam boyut.
- `face_service.detect_faces_bytes()` (webcam baytları, filtre gevşek), `matching_service.
  find_best_customer()` (SALT-OKUNUR, yeni müşteri açmaz) eklendi.
- **Test:** örnek foto /kiosk/scan'e gönderildi → müşteri 6, benzerlik 0.78, 2 foto döndü;
  filigranlı JPEG geçerli. Kamera/tarayıcı testi kullanıcıda (webcam gerekli).
- **Kararlar:** tema=canlı/eğlenceli, tekrar gelen müşteri=yüz+e-posta, filigran=otel adı+önizleme.
- **AÇIK:** gerçek otel adı (`HOTEL_NAME`, şu an "OTEL ADI" yer tutucu; `.env`'e HOTEL_NAME=... ile
  değişir). Webcam tarayıcıda `localhost`/HTTPS ister (LAN'da IP ile kamera engellenebilir).

### Aşama 2B — Ürün/albüm yönetimi, operatör tarafı (TAMAMLANDI, doğrulandı)
- `backend/app/models.py` → `Product` modeli (name, description, price [TL float], photo_count
  [int nullable], is_active, created_at). Migration `56e177af92b9`.
  - **Fiyatlandırma semantiği:** `photo_count=None` → **serbest seçim, fiyat = FOTO BAŞINA**;
    kiosk toplam = fiyat × seçili foto (dinamik, foto ekle/çıkar ile anlık değişir), kioskta
    **varsayılan seçili** gelir. `photo_count=N` → sabit albüm, fiyat sabit, kapasite ≤ N.
    Sipariş toplamı `OrderOut.toplam_fiyat` (orders.py `_order_total`); operatör kartında gösterilir.
    Kioskta sipariş ekranında her fotonun yanında "×" (çıkar) butonu var.
- `backend/app/routers/products.py` — CRUD: `POST/GET/PATCH/DELETE /products`; `GET /products?
  sadece_aktif=true` (kiosk yalnız aktifleri görecek).
- `backend/app/routers/operator.py` + `backend/app/static/operator.html` — `GET /operator`
  operatör paneli: ürün ekle/düzenle/sil, aktif/pasif, temiz light dashboard (marka renkleri).
- Test: ekle/güncelle/pasifleştir/sil/aktif-filtre hepsi geçti.

### Aşama 2C — Sepet + albüm seçimi + sipariş (TAMAMLANDI, uçtan uca doğrulandı)
Müşteri döngüsü kapandı: tara → galeri → seç → sipariş ekranı → onay → operatöre düşer.
- `models.py` → `Order`'a `email`, `product_id` (FK products), `status` ("yeni"/"hazir"/"teslim")
  eklendi; `product` ilişkisi. Migration `31cc9e594695`.
- `backend/app/routers/orders.py` — `POST /orders` (sepet onayı: müşteri/ürün/foto doğrular,
  sabit albümde kapasite aşımını 400 ile reddeder), `GET /orders?status=`, `GET /orders/{id}`,
  `PATCH /orders/{id}/status`. `_serialize` türetilmiş alanlar (customer_folder, product_name,
  foto_sayisi) verir.
- Kiosk (`static/index.html`) → **TEK EKRAN 3 KOLON** (2 adımlı değil): sol=paket/albüm seçimi
  (`.shop-left`, `#prod-grid`), orta=foto galerisi (`.shop-center`, `#gallery`), sağ=sepet
  (`.shop-right`: `#cart-items` seçili fotolar+not+×, `#co-email`, `#prod-warn`, toplam, Onayla).
  Galeride ✓ ile sepete ekle/çıkar → sepet + fiyat ANLIK güncellenir. `renderAlbums/renderCart/
  updateTotals/toggleSelect` + `notes` map (photoId→not, yeniden çizimde korunur). Ayrı checkout
  ekranı / actionbar KALDIRILDI.
- **Tam sayı zorunluluğu:** sabit albümde foto sayısı TAM olmalı (`_validate_product_and_photos`
  `!=` kontrolü, 400). Serbest üründe sınır yok. Kioskta `updateTotals` az/fazla uyarısı verir,
  onay butonu tam sayıda aktif olur. Test: 5'lik→3 foto 400, 5 foto 201, 7 foto 400.
- Operatör paneli (`static/operator.html`) → sekmeli (Ürünler / Siparişler). Siparişler sekmesi:
  gelen siparişler kart halinde (orijinal foto önizleme + notlar + e-posta), "Hazır"/"Teslim"
  durum butonları, Yenile. Foto önizleme `?filigran=false` (operatör orijinali görür/basar).
- **Not:** operatör sipariş foto önizlemesi orijinali (filigransız) kullanır — baskı için doğru.
  Gerçek zamanlı bildirim yok (operatör "Yenile" ile çeker); WebSocket ileride (Faz 3).

### Aşama 2D (kısmi) + düzeltmeler (TAMAMLANDI, doğrulandı)
- **E-posta artık ZORUNLU:** `schemas.OrderCreate.email` = `Field(..., pattern=<basit email>)`
  (422 döner); kiosk checkout'ta da regex doğrulaması + "zorunlu" etiketi.
- **Tekrar gelen müşteri:** `GET /orders` artık `customer_id` ve `email` filtreleri alıyor. Kiosk
  taramadan sonra (yüzle bulunan müşterinin) önceki siparişlerini result ekranında "Önceki
  Siparişleriniz" bölümünde gösteriyor (durum: hazırlanıyor/hazır/teslim). Kimlik = yüz eşleşmesi.
  NOT: eski siparişi *düzenleme* henüz yok (sadece görüntüleme) — sonraki adım.

### Aşama 2E — Eski sipariş düzenleme + e-posta ile giriş (TAMAMLANDI, backend doğrulandı)
Kiosk müşteri tarafı tamamlandı.
- **Sipariş düzenleme:** `PATCH /orders/{id}` (`schemas.OrderUpdate`) — sadece `status=="yeni"`
  siparişler; `hazir`/`teslim` ise **409**. Kalemler tamamen değiştirilir (eski OrderItem'lar
  silinip yenileri eklenir). Doğrulama `_validate_product_and_photos` ile create+update ortak.
  Kioskta: result ekranındaki "Önceki Siparişleriniz"de `yeni` siparişe dokununca checkout
  düzenleme modunda açılır (fotolar seçili, notlar/ürün/e-posta dolu, buton "Güncelle" → PATCH).
- **E-posta ile giriş:** `GET /kiosk/by-email?email=` — bu e-postayla verilmiş en son siparişin
  müşterisini bulur, o müşterinin fotolarını `KioskScanResult` olarak döndürür (yüz taramaya
  alternatif; 14 gün penceresinden bağımsız, veri kalıcı). Kioskta karşılama ekranında
  "✉️ E-posta ile Siparişlerim" butonu → e-posta ekranı → `emailLogin()` → aynı result akışı.
- **Test:** oluştur→by-email(10 foto)→PATCH(3 foto+not/email güncel)→hazir→PATCH 409. Hepsi geçti.
- **Fotoğraf yükleme arayüzü:** Operatör paneline "📤 Fotoğraf Yükle" sekmesi eklendi —
  fotoğrafçı ekle/listele + fotoğrafçı seç + çoklu dosya → `POST /photos/upload`. (Önceden sadece
  /docs'tan yapılabiliyordu.) Yükleme = operatör bir fotoğrafçı seçip o kartın fotolarını yükler.

### Ölçek Chunk 1 — İşleme çekirdeği yeniden kuruldu (TAMAMLANDI, doğrulandı)
Faz B + C1 + D1 birlikte. 32 örnek fotoyla tekrar test → **12 müşteri (aynı dağılım)**, upload
**0.3 sn'de** döndü, centroid'ler dolu (face_count toplamı=faces sayısı), customer_folders boş.
- **Kalıcı kuyruk + worker (Faz B):** `backend/app/worker.py` — uygulama açılışında (main.py
  `lifespan`) tek worker thread başlar; `status='pending'` fotoları `FOR UPDATE SKIP LOCKED` ile
  sırayla işler. Yeniden başlamaya dayanıklı, yarış hatası yok, hata olan foto `status='error'`.
  `Photo.status` (pending/processing/done/error) + `Photo.error` eklendi. Upload artık ANINDA
  döner (BackgroundTasks kaldırıldı); dosyalar diske `shutil.copyfileobj` ile akıtılır.
- **Kopyalama kaldırıldı (Faz C1):** `backend/app/services/processing.py` (eski classification.py
  yerine) — müşteri klasörüne fiziksel kopya YOK, sadece `Face` ilişkisi. Depolama ~1.5-2× düşer.
- **Artımlı centroid (Faz D1):** `Customer.centroid` (LargeBinary) + `Customer.face_count`;
  `matching_service` her yüzde centroid'i artımlı günceller, eşleştirmede tüm yüzleri değil sadece
  aktif müşteri centroid'lerini karşılaştırır (N²→O(müşteri)). 14 gün penceresi = `updated_at`
  filtresi (veri SİLİNMİYOR, sadece eşleştirme sınırı). Migration `bdb2827cbd3e`.
- **Durum takibi:** `GET /photos/durum` → {pending, processing, done, error, toplam}.
- **Kalan ölçek işleri:** yok (Faz A/B/C1/C2/D1 bitti). Sadece çok büyük ölçekte Faz D2
  (pgvector) — muhtemelen gerekmez. Detay: docs/olcek-yol-haritasi.md.

### Ölçek Faz C2 — Görsel önbelleği (TAMAMLANDI, doğrulandı)
- `backend/app/services/images.py` — türevler `data/cache/` altında bir kez üretilip önbelleklenir:
  `{id}_gal.jpg` (filigranlı 1400px, kiosk galeri), `{id}_full.jpg` (filigranlı tam, lightbox,
  ilk açılışta üretilir), `{id}_op.jpg` (filigransız 1000px, operatör önizleme).
- `watermark.py` → `resized_jpeg()` (filigransız küçültme) eklendi.
- `processing.py` → yüz varsa işlemede galeri önbelleği **önceden** üretilir (`ensure_gallery_cache`);
  kiosk ilk görüntülemede üretim maliyeti ödemez.
- `photos.py` → `GET /photos/{id}/image` artık orijinali her istekte decode/filigran etmez,
  önbellek dosyasını `FileResponse` ile servis eder. Ölçüm: tam boyut 146→30ms, operatör 105→18ms
  (gerçek 15MB fotolarda kazanç çok daha büyük).
- `operator.html` sipariş önizlemeleri artık küçük filigransız önbelleği (`filigran=false&boyut=galeri`)
  kullanır; tıklayınca orijinal (`boyut=tam`) baskı için açılır.
- **Not:** HOTEL_NAME değişirse filigranlı önbellek (`_gal/_full`) bayatlar → `data/cache/` temizlenmeli.

### Ölçek Faz A — Yükleme dayanıklılığı (TAMAMLANDI, doğrulandı)
- **A1 parçalı yükleme:** operatör paneli fotoları 25'erli gruplar hâlinde gönderir + ilerleme
  çubuğu + canlı işleme durumu (`/photos/durum` polling). `static/operator.html` yükleme sekmesi.
- **A2 klasör ingestion:** `POST /photos/ingest` (photographer_id + folder) — sunucudaki klasörü
  (alt klasörler dahil) tarar, geçerli fotoları **YERİNDE** (kopyasız) kuyruğa ekler. 32 foto
  0.1 sn'de eklendi, stored_path ingest klasörünü gösteriyor, işlendi → 12 müşteri. Büyük
  partiler için (60 GB'ı HTTP'den geçirmeden). Operatör panelinde "Yöntem 2" olarak.
- **A3 doğrulama:** izinli uzantı (`.jpg/.jpeg/.png`) + `MAX_UPLOAD_MB` (varsayılan 60) kontrolü;
  geçersizler atlanır ve raporlanır (`UploadResult.atlanan/atlanan_dosyalar`). Config'te.
- **Not:** ingest endpoint sunucudaki keyfi yolu okur — auth eklenince (Faz 3) sınırlanmalı.

### Faz 3A — Operatör photoshop + teslim paketi (TAMAMLANDI, doğrulandı)
Operatör = photoshop yapan kişi. Orijinal korunur, düzenlenmiş versiyon order item'a bağlanır.
- `models.py` → `OrderItem.edited_path` (nullable), `OrderItem.photo` ilişkisi. Migration
  `7193e337229d`. `config.EDITED_DIR = data/edited`.
- `orders.py`: `POST /orders/{oid}/items/{item_id}/edited` (photoshop'lu foto yükle, orijinal
  değişmez), `GET /orders/items/{item_id}/edited-image` (düzenlenmiş önizleme), `GET /orders/{oid}/
  download` (**teslim paketi zip**: her foto için edited varsa o, yoksa orijinal full-res,
  ZIP_STORED). `OrderItemOut.edited` bayrağı. Kalemler id'ye göre sıralı (deterministik).
- Operatör paneli sipariş kartı: her foto için **⬇ İndir** (orijinali photoshop için indir) +
  **✎ Yükle** (düzenlenmişi yükle) + "✅ düzenlendi" rozeti; sipariş için **📦 Teslim Paketi (zip)**.
- **Fotoğrafçı takibi korunur:** edited yeni Photo DEĞİL, OrderItem'a türev; `OrderItem→Photo→
  Photographer` zinciri bozulmaz. Photoshop makinesi sunucu ya da başka bir LAN makinesi olabilir
  (indir/yükle HTTP; fark etmez). Detay: [[operator-photoshop-teslimat]], docs/operator-teslimat-yol-haritasi.md.
- **Teslimat kararı:** WeTransfer otomatikleştirilemiyor (API kapalı) → operatör zip'i indirip
  mevcut gibi WeTransfer'e atar (Yol A). Otomatik e-posta+bulut link (Yol B) sonra.

### Faz 3A-2 — Otomatik sipariş klasörü export'u (TAMAMLANDI, doğrulandı)
Gerçek editör iş akışı KLASÖR bazlı (masaüstü "Siparişler/siparişXXXX", TransferNow ile gönderim);
teker teker indir/yükle onlar için yavaş. Çözüm:
- `config.ORDERS_EXPORT_DIR` (.env ile editörün makinesine PAYLAŞILAN klasöre / masaüstü
  "Siparisler" klasörüne yönlendirilebilir; varsayılan `data/siparisler_export`).
- `services/order_export.py` → `export_order(order_id)`: `siparis_XXXX/` klasörü yazar (fotoların
  orijinal kopyaları + `_SIPARIS_X_BILGI.txt`: no, tarih, e-posta, paket+toplam, foto başına
  düzenleme notları). **TAHRİP ETMEZ** (var olan dosyayı ezmez → editörün düzenlemesini korur).
- `orders.py`: create + update'te BackgroundTasks ile otomatik export; `POST /orders/{id}/export`
  (manuel yenileme, UI'dan kaldırıldı ama endpoint duruyor).
- **Operatör Siparişler görünümü SADELEŞTİRİLDİ (kullanıcı isteği):** foto indir/yükle + zip +
  klasör butonları KALDIRILDI (editör masaüstü `siparis_XXXX` klasöründen çalışıyor). Kartta artık
  sadece bilgi: sipariş no + `📁 siparis_XXXX` (açılacak klasör) + paket/toplam + e-posta +
  her foto için thumbnail + dosya adı (`01_fotoX`) + yapılacak düzenleme notu.

### Faz 3A-3 — Operatör sipariş sekmeleri + sayfalama + düzenleme resurface (TAMAMLANDI, doğrulandı)
Yüzlerce sipariş/gün için ölçekli operatör görünümü.
- `models.py` → `Order.revised_at` (nullable). Migration `f42f3b196a35`. `OrderOut.revised` bayrağı.
- **Düzenleme resurface:** `PATCH /orders/{id}` (müşteri düzenlemesi) artık 409 vermez; her
  düzenlemede `status="yeni"` + `revised_at=now` → sipariş "Yeni Gelenler"e geri düşer, operatör
  "✏️ DÜZENLENDİ" rozetiyle görür. Kioskta `teslim` hariç her sipariş düzenlenebilir.
- **Sayfalama:** `GET /orders?status=&limit=&offset=` + `GET /orders/sayilar` ({yeni, hazir, toplam}).
- **Operatör paneli Siparişler:** iki alt-sekme **🆕 Yeni Gelenler** / **✅ Hazır** (sayı rozetli),
  20'şerli sayfalama; sekme sayıları 15 sn'de bir otomatik yenilenir (yeni sipariş rozete düşer).
- **Operatör paneli TASARIM REVİZYONU (dashboard):** Üst pill-tab yapısı → **admin dashboard**:
  solda koyu **sidebar** (marka + nav: Siparişler/Ürünler/Fotoğraf Yükle, aktif=turkuaz, yeni
  sipariş sayısı rozeti), üstte **page-head** (sekmeye göre başlık/alt başlık), gövde hafif gri
  zemin + gölgeli beyaz kartlar (boş beyazlık gitti). Açılış sekmesi=Siparişler. `showTab` başlık
  set eder + ilgili veriyi yükler. Sidebar rozeti 15 sn'de bir güncellenir. Responsive (dar
  ekranda sidebar yatay). [[tasarim-revizyonu-bekliyor]] bu revizyonla büyük ölçüde karşılandı
  (operatör tarafı); kiosk tasarımı ayrı. **Ürünler:** tablo → **kart grid** (`prod-card2`,
  `#prod-list-grid`, loadProducts kart üretir). **Fotoğraf Yükle:** iki yöntem yan yana
  **method-box** kartlarında (genişliği doldurur). Butonlara gölge/hover cilası.
- **Kart + detay modal (kullanıcı isteği):** Siparişler artık **kompakt tıklanabilir kartlar**
  (`.orders-grid`, satırda 2-3). Karta tıklayınca **detay modal** açılır (`#order-modal`): tüm
  fotolar (thumbnail + `01_fotoX` adı + düzeltme notu), müşteri bilgisi + **📋 e-posta kopyala**
  (`copyEmail`, clipboard), ve durumdan "✓ Hazır İşaretle" / "↩ Yeniye Al". 50+ fotoluk siparişler
  için uygun. `ordersById` map + `openOrderDetail`/`closeOrderModal`/`markStatusFromDetail`.
- **Durum:** şimdilik `yeni`/`hazir` (teslim ileride). `setStatus` yeni↔hazir.
- Test: sayılar, sayfalama, hazir→müşteri düzenleme→yeni+revised=true — hepsi geçti.
- **Önerilen kurulum:** export klasörü SUNUCUDA olsun, editöre Windows paylaşımıyla bağlansın →
  editör yerinde düzenler, sunucu da nihai dosyalara sahip olur (Yol B otomasyonuna kapı açar).
- **TransferNow:** API'si var (business plan); anahtar sağlanırsa "hazır"da sunucudaki nihai
  dosyalar TransferNow API'sine (ya da kendi bulut+link'imize) yüklenip müşteriye mail — Faz 3B.

### Yüz tanıma çekirdeği (POC — daha önce yapılmıştı, çalışıyor)

- `otel-foto-sistemi/backend/app/gpu_setup.py` — Windows'ta onnxruntime-gpu'nun CUDA/cuDNN
  DLL'lerini bulması için nvidia-* pip paketlerinin `bin/` klasörlerini `os.add_dll_directory` +
  PATH ile ekler. **Her yeni script, onnxruntime/insightface import etmeden ÖNCE
  `import app.gpu_setup` yapmalı.**
- `otel-foto-sistemi/backend/test_cuda.py` — CUDA provider doğrulama scripti.
- `otel-foto-sistemi/scripts/test_face_detection.py` — InsightFace (`buffalo_l`) ile
  `data/raw_uploads/` içindeki fotoları işler, yüz tespiti + 512 boyutlu embedding çıkarır, tespit
  kutularını çizip `data/debug_output/`'a kaydeder (gözle doğrulama için).
- `otel-foto-sistemi/scripts/test_face_clustering.py` — Embedding'lere göre fotoları
  `data/customer_folders/musteri_XXX/` altında kümeler. Her klasörün centroid (ortalama)
  embedding'i ile cosine similarity hesaplar; eşik üstü en yüksek benzerlikli klasöre ekler, yoksa
  yeni klasör açar.
  - `SIMILARITY_THRESHOLD = 0.40` — eşleşme eşiği, gerçek veriyle ayarlanacak.
  - `MIN_DET_SCORE = 0.55`, `MIN_FACE_WIDTH_RATIO = 0.06` — arka plandaki küçük/belirsiz yüzleri eler.
- `otel-foto-sistemi/backend/.env` — `DATABASE_URL` (artık `config.py` üzerinden kullanılıyor).
- `otel-foto-sistemi/data/` — test verisi (örnek WhatsApp fotoları) + `raw_uploads/`, `gonderilecek/` (hazır teslim zip'leri), `siparisler_export/`,
  `customer_folders/`, `debug_output/` klasörleri (gitignore'da, sadece `.gitkeep` takip ediliyor).

### Faz 3B — Operatör girişi / güvenlik (TAMAMLANDI, uçtan uca doğrulandı)
Sistem artık auth'suz değil. **Tek paylaşılan operatör şifresi** (kullanıcı hesabı yok — otelde
paneli 1-2 kişi kullanıyor, rol sistemi bu ölçekte gereksiz).
- `models.py` → `OperatorAuth` (password_hash + salt + `is_default`), `OperatorSession`
  (token, expires_at). Migration `630045e45cbb`.
- `services/auth_service.py` — PBKDF2-HMAC-SHA256 (200k tur) + kayda özel salt; şifre **DB'de**
  (`.env`'de değil — panelden değiştirilebilsin diye). Oturum = rastgele token, **DB'de** tutulur
  (sunucu restart'ında oturum düşmez, çıkış token'ı gerçekten geçersiz kılar), tarayıcıya
  **HttpOnly cookie**. `require_operator` FastAPI dependency'si. Bellek-içi kaba kuvvet
  sınırlaması: 5 hatalı deneme → 60 sn kilit (429).
- `routers/auth.py` — `GET /auth/durum` (açık; panel giriş ekranı mı dashboard mu göstereceğine
  buna bakar), `POST /auth/login`, `POST /auth/logout`, `POST /auth/sifre-degistir`.
  Şifre değişince TÜM oturumlar düşer, ardından bu tarayıcıya yeni oturum verilir.
- **İlk şifre:** `OPERATOR_INITIAL_PASSWORD` (varsayılan `otel123`), ilk açılışta DB'ye yazılır.
  Varsayılan kaldığı sürece panelde sarı "şifrenizi değiştirin" uyarısı görünür.
- `static/operator.html` → giriş ekranı (tam ekran overlay), sidebar'da 🔑 Şifre Değiştir /
  🚪 Çıkış Yap, şifre değiştirme modalı. `window.fetch` sarmalanır: herhangi bir istek **401**
  dönerse otomatik giriş ekranına döner (oturum süresi dolunca).
- **Auth sınırı — KİOSK AÇIK KALMALI** (müşterinin önündeki makinede giriş ekranı olamaz):
  | açık (kiosk) | korumalı (operatör) |
  |---|---|
  | `/kiosk/*`, `/operator` (sayfa), `/auth/durum` | ürün ekle/düzenle/sil, `/photographers`, `/customers` |
  | `/products?sadece_aktif=true` | `/photos/upload`, `/photos/ingest`, `/photos/durum`, `GET /photos` |
  | `POST /orders`, `PATCH /orders/{id}`, `GET /orders/{id}` | `PATCH /orders/{id}/status`, `/export`, `/download`, `/items/../edited` |
  | `/photos/{id}/image?**filigran=true**` | `?**filigran=false**` (orijinal = satılabilir ürün) |
  | `GET /orders?customer_id=` / `?email=` (kendi siparişi) | `GET /orders` **filtresiz** (= tüm otelin siparişleri), `/orders/sayilar` |
  Son iki satır **parametreye göre** karar verir (`is_logged_in` ile endpoint içinde).
- **Test:** girişsiz 401'ler, girişli 200'ler, yanlış şifre 401, kısa şifre 422, şifre değişince
  eski şifre 401 + eski cookie 401 + mevcut tarayıcı içeride kalıyor, çıkış 401, 6. denemede 429,
  kiosk regresyonu (tara/e-posta/galeri) sağlam. Hepsi geçti.
- **AÇIK KALAN (bilinçli):** kiosk kimliği "yüz eşleşmesi"ne dayanıyor, gizli anahtar yok →
  `customer_id`/`order_id` tahmin edilerek başkasının siparişi görülebilir/düzenlenebilir
  (`GET/PATCH /orders/{id}`, `GET /orders?customer_id=`). Kapatmak için kiosk taramasında
  müşteriye kısa ömürlü bir oturum token'ı verilmeli — LAN'da kiosk fiziksel olarak kontrollü
  olduğu için şimdilik ertelendi.
- **Cookie notu:** LAN'da düz HTTP kullanıldığı için cookie `secure=False`. HTTPS'e geçilirse
  `secure=True` yapılmalı (`routers/auth.py`).

### Faz 3C — Gönderim paketi + iletişim kopukluğunun çözümü (TAMAMLANDI, doğrulandı)
**Çözülen sorun:** sistemde iki ayrı düzenleme yolu vardı ve birbirlerinden habersizlerdi —
(A) operatör panelden düzenlenmiş fotoyu yükler → `OrderItem.edited_path`; (B) editör
`siparis_XXXX` klasöründe dosyayı **yerinde** düzenler → sistem bunu hiç görmezdi. Eski zip ucu
sadece (A)'ya bakıyordu, yani editör (B) ile çalışırsa müşteriye **düzenlenmemiş orijinaller**
gidiyordu, sessizce.

**Karar: teslimatın TEK KAYNAĞI artık sipariş klasörüdür** (`ORDERS_EXPORT_DIR/siparis_XXXX`).
Editör orada ne bıraktıysa müşteriye o gider. Panelden yükleme yolu da aynı klasöre aktığı
sürece iki yol tek noktada buluşur.

- `config.GONDERILECEK_DIR` (.env ile değiştirilebilir; varsayılan `data/gonderilecek`).
- `services/delivery.py` — `paket_hazirla(db, order)`: sipariş klasöründeki görselleri
  (`_` ile başlayanlar ve `_kaldirilan/` hariç, izinli uzantılar) `siparis_XXXX.zip` olarak
  GONDERILECEK_DIR'e yazar (ZIP_STORED). Döndürür: zip adı/yolu, foto sayısı, MB,
  **`duzenlenmemis`** listesi, e-posta. `paket_yolu()`, `paket_durum()` de var.
- **Düzenlendi mi tespiti:** export `shutil.copy2` kullandığı için dokunulmamış kopya
  orijinalle **aynı boyut + aynı mtime**'a sahiptir. Biri farklıysa editör dosyaya dokunmuştur.
  Böylece operatör hiç düzenlenmemiş bir siparişi yanlışlıkla gönderemez — panel uyarır.
- `orders.py`: `POST /orders/{id}/gonderime-hazirla` (paketi üretir), `GET /orders/{id}/paket`
  (zip'i tarayıcıya indirir). İkisi de operatör girişi ister.
- **Bayat dosya ayıklama:** `order_export.py` → `_ayikla()`. Müşteri siparişi düzenleyip foto
  çıkarınca eski dosya klasörde kalıyordu (editör artık siparişte olmayan fotoyu düzenliyordu ve
  pakete giriyordu). Artık siparişe ait olmayan görseller `_kaldirilan/` alt klasörüne **taşınır**
  (silinmez — editörün emeği kaybolmasın). Export hâlâ mevcut dosyayı **ezmez**.
- **Operatör paneli:** sipariş detay modalinde, sadece **`hazir`** siparişlerde
  **📦 Gönderime Hazırla** butonu. Basınca sonuç kutusu: zip adı · foto sayısı · MB · klasör yolu
  (kopyala) · e-posta (kopyala) · ⬇ Zip'i indir. Hiç düzenlenmemiş foto varsa **sarı uyarı**;
  paket 20 MB'ı aşarsa "mail eki limitini aşıyor, WeTransfer/TransferNow kullanın" notu.
- **Sistem GÖNDERMEZ, paketi hazırlar** (bilinçli): SMTP hesabı, API anahtarı, spam/teslim edilme
  derdi yok. Operatör zip'i alıp istediği yolla yollar (mail eki, WeTransfer, TransferNow).
- **Test:** paket 3 foto → export yenile → bayat 2 dosya `_kaldirilan/`a taşındı → paket 1 foto;
  editör fotoyu yerinde düzenledi → `duzenlenmemis: []` + zip 0.2→0.4 MB (düzenlenmiş sürüm
  pakete girdi); export tekrar çalıştı → editörün dosyası **ezilmedi**; girişsiz 401. Hepsi geçti.
- **Sonraki adım (isteğe bağlı):** `.eml` taslağı (`X-Unsent: 1` header'ı ile Outlook'ta
  düzenlenebilir taslak olarak açılır, zip ekli) — sadece ~20 MB altı siparişlerde işe yarar.
  Büyükler için bulut + link şart (müşteri otelden ayrılınca LAN linki ölür).

## Henüz Yapılmayanlar (yol haritası)

- **SIRADAKI seçenekler:** (a) **Büyük tasarım revizyonu** (kullanıcı mevcut tasarımı beğenmedi —
  bkz. [[tasarim-revizyonu-bekliyor]]); (b) fotoğrafçı başına satış raporu (veri hazır:
  OrderItem→Photo→Photographer); (c) operatör güvenliği/giriş (Faz 3).
  Kiosk müşteri tarafı TAMAMLANDI (tara/e-posta giriş → galeri → seç/incele → sipariş → düzenle).
- **Faz 3 (operatör tarafı — analiz yapıldı, bkz. docs/operator-teslimat-yol-haritasi.md):**
  1. **Photoshop re-upload:** operatör=photoshop yapan kişi; `OrderItem.edited_path`, orijinal+edited
     ikisi de tutulur, teslimatta edited öncelikli. 2. **Teslimat:** e-posta ile (küçük=ek,
     büyük=bulut+link; "email kaliteyi düşürür" mit, asıl sorun boyut). 3. Operatör state + gerçek
     zamanlı sipariş bildirimi (polling/WebSocket). 4. Operatör şifreli giriş. 5. KVKK rıza.
     6. Fotoğrafçı satış raporu (veri hazır). 7. DB yedek script'i (pg_dump; foto yedeği manuel).
     Kararlar hafızada: [[operator-photoshop-teslimat]].
- **Aşama 1 iyileştirmeleri (sonra):** `Photo.uploaded_by_id`'yi DB'de NOT NULL yapmak (şu an
  API'de zorunlu ama kolonda nullable), gerçek veriyle `SIMILARITY_THRESHOLD` ayarı, çok büyük
  partilerde gerçek kuyruk (şu an FastAPI BackgroundTasks).
- **İleride:** fotoğrafçı başına satış raporu, admin düzeltme araçları (klasör birleştir/böl),
  KVKK rıza akışı + otomatik veri silme (14 gün penceresi), auth.
- Kiosk (müşteri) arayüzü — webcam ile yüz tarama, eşleşen klasörü listeleme
- Sipariş sistemi — foto seçimi, not ekleme, sipariş oluşturma
- Fotoğrafçı bildirim ekranı — sipariş, yükleme yapılan bilgisayara gerçek zamanlı düşmeli
- Personel/fotoğrafçı kimlik doğrulaması
- KVKK/rıza akışı — yüz verisi biyometrik/özel nitelikli kişisel veri sayılır, açık rıza ve
  otomatik veri silme politikası (2 haftalık pencere bunun için kullanılabilir) tasarlanmalı

## Teknoloji Kararları / Konvansiyonlar

- Yüz tanıma: InsightFace `buffalo_l` + onnxruntime-gpu (CUDA) — pretrained model, sıfırdan
  eğitim gerekmiyor.
- DB: **PostgreSQL 17.5** (kurulu ve çalışıyor). Embedding'ler `Face.embedding` alanında
  **LargeBinary** (numpy `.tobytes()`) olarak saklanıyor; benzerlik (cosine) şimdilik
  Python/numpy'de yapılacak — bu ölçekte yeterli. Ölçek büyürse `pgvector`'e geçilebilir
  (Windows'ta ayrı kurulum gerektirdiği için şimdilik kaçınıldı).
- **Postgres auth notu:** `pg_hba.conf` `scram-sha-256` istiyor; rol şifresi set edilirken
  `SET password_encryption TO 'scram-sha-256'` gerekli, yoksa md5 hash'le kaydolup login
  başarısız olur. Ayrıca PG15+ `public` şemasında CREATE için `otel_foto_user`'a şema
  sahipliği/izni verildi.
- Migration aracı: **Alembic** (`backend/alembic/`). Model değişince autogenerate + upgrade.
- Kod genelinde docstring/yorumlar **Türkçe** yazılıyor — yeni kod bu konvansiyona uymalı.
- Klasör/naming konvansiyonu: `musteri_XXX` (3 haneli, sıfırla dolgulu).
- Git deposu `otel-foto-sistemi/` içinde (kök `otel_photo/` değil).

## Ölçek / Üretim Hazırlığı (ÖNEMLİ)

Gerçek hedef yük: **~4000 foto/gün** (4 fotoğrafçı × ~1000), foto başına ~10–20 MB → ~60 GB/gün,
14 günlük pencerede ~840 GB / ~110.000 yüz. Mevcut kod bu ölçeğin altına göre yazıldı; 4 darboğaz:
(1) tek dev yükleme isteği, (2) BackgroundTasks (kuyruk yok), (3) fiziksel klasör kopyalama
(depolama şişer), (4) N² eşleştirme. Tam plan: **[docs/olcek-yol-haritasi.md](otel-foto-sistemi/docs/olcek-yol-haritasi.md)**.
Üretimden önce Faz A (parçalı/klasör yükleme) + B (kuyruk+worker) + C (kopyalama kaldır + thumbnail)
+ D1 (artımlı centroid) + E (otomatik silme) yapılmalı. Detay: [[olcek-hedefleri]].

## Kısa İş Tahmini (referans, MVP için)

Backend API+DB ~1-2 hafta · upload pipeline ~1 hafta · pencere/klasör mantığı productionizing
~3-5 gün · kiosk arayüzü ~1-2 hafta · sipariş+bildirim ~1 hafta · test/tuning ~1-2 hafta.
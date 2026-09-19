# 🏨 Otel Foto Sistemi — Yüz Tanıma Tabanlı Fotoğraf Yönetim ve Kiosk Satış Platformu

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.139-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL%2017-336791.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![InsightFace](<https://img.shields.io/badge/AI-InsightFace%20(buffalo__l)-orange.svg>)]()
[![CUDA](https://img.shields.io/badge/GPU-CUDA%20%2F%20ONNX%20Runtime-76B900.svg?logo=nvidia&logoColor=white)](https://developer.nvidia.com/cuda-toolkit)

Otel fotoğrafçıları ve stüdyoları için geliştirilmiş **yüz tanıma tabanlı** uçtan uca fotoğraf yönetim, sipariş ve kiosk satış sistemi.

Otelde gün boyu çekilen binlerce fotoğraf sisteme aktarılır. Sistem, fotoğraflardaki yüzleri yapay zekâ ile tespit edip 512 boyutlu vektörlere (embedding) dönüştürür ve aynı kişiye ait olanları otomatik olarak gruplar. Misafir lobideki kiosk ekranında yüzünü kameraya gösterir, **yalnızca kendi fotoğraflarını** filigranlı olarak görür, beğendiklerini seçip sipariş verir. Sipariş operatör paneline düşer; editör fotoğrafları düzenler ve sistem tek tıkla teslimat paketini hazırlar.

> **Çözdüğü Problem:** Eskiden misafir binlerce basılı fotoğrafın veya dijital dosyanın arasında kendini elle aramak zorundaydı; personel de hangi fotoğrafın kime ait olduğunu ve hangi fotoğrafçının çektiğini takip edemiyordu. Bu sistem hem misafir deneyimini hızlandırır hem de stüdyo operasyonunu otomatikleştirir.

---

## 📑 İçindekiler

- [Nasıl Çalışır?](#-nasıl-çalışır)
- [Sipariş Akışı ve Editör İş Akışı](#-sipariş-akışı)
- [Yüz Tanıma ve Müşteri Gruplama](#-yüz-tanıma-ve-müşteri-gruplama)
- [Mimari ve Teknoloji Yığını](#-mimari)
- [Kurulum Adımları](#-kurulum)
- [.env Yapılandırması ve Öncelik Sırası](#-env-yapılandırması)
- [Çalıştırma](#-çalıştırma)
- [Kullanım Senaryoları](#-kullanım)
- [Klasör Yapısı](#-klasör-yapısı)
- [Veri Modeli (Veritabanı Şeması)](#-veri-modeli)
- [Güvenlik ve KVKK](#-güvenlik)
- [API Uç Noktaları Referansı](#-api-uçları)
- [Yazar ve Lisans](#-lisans)

---

## ⚙️ Nasıl Çalışır?

Sistem tek bir ana sunucuda çalışır, kullanıcılar yerel ağdan tarayıcı aracılığıyla bağlanır. İki temel arayüzü vardır:

| Arayüz              | Adres       | Kullanıcı                                    | Yetkilendirme                    |
| ------------------- | ----------- | -------------------------------------------- | -------------------------------- |
| **Kiosk**           | `/kiosk`    | Misafir (Lobideki dokunmatik ekran / tablet) | Girişsiz (Halka açık)            |
| **Operatör Paneli** | `/operator` | Otel personeli & Editörler                   | Şifreli oturum (HttpOnly Cookie) |

Yüz tanıma ve görsel işleme sunucudaki GPU üzerinde çalışır; kiosk makinesinin güçlü bir donanıma sahip olması gerekmez, standart bir web tarayıcısı ve webcam yeterlidir.

```
 Fotoğrafçılar                Sunucu (FastAPI + GPU)                  Misafir
 ─────────────                ──────────────────────                  ───────
  hafıza kartı  ──►  operatör yükler  ──►  arka plan işçisi
                                           · yüzleri bulur
                                           · aynı kişiyi gruplar   ◄── kiosk'ta
                                           · önizleme üretir            yüzünü taratır
                                                   │                        │
                                                   └────────────────────────┘
                                                     kendi fotoğraflarını görür
                                                     seçer, sipariş verir
                                                             │
  Operatör  ◄────────────────────────────────────────────────┘
  · siparişi görür, klasöründe fotoğrafları düzenler (Photoshop)
  · "Hazırla ve Paketle" der  ──►  zip "gönderilecek" klasörüne düşer
  · zip'i misafire yollar     ──►  "Gönderildi" işaretler
```

> [!NOTE]
> **Sistem fotoğrafı kendisi göndermez.** Hazır zip arşivini sunucudaki `gonderilecek` klasörüne bırakır; operatör otelin tercih ettiği yolla (e-posta eki, WeTransfer, USB bellek vb.) misafire teslim eder.

---

## 📦 Sipariş Akışı

Her siparişin üç durumu vardır ve operatör panelinde üç ayrı sekme olarak yönetilir:

| Durum             | Anlamı                                                            | Müşteri Değiştirebilir mi? |
| ----------------- | ----------------------------------------------------------------- | :------------------------: |
| 🆕 **yeni**       | Misafir siparişi kiosk'tan verdi, operatör henüz işleme başlamadı |          **Evet**          |
| ✅ **hazır**      | Operatör düzenlemeyi bitirdi, teslimat zip'i oluşturuldu          |           Hayır            |
| 📮 **gönderildi** | Operatör paketi misafire teslim etti / yolladı                    |           Hayır            |

### Kilit Neden "Hazır"da Başlar?

Operatör "Hazır" dediği an Photoshop düzenlemeleri tamamlanmıştır. Bundan sonra kiosk'tan gelebilecek bir müşteri güncellemesi, sipariş klasöründeki düzenlenmiş dosyaların yeniden numaralanıp orijinalleriyle ezilmesine yol açabilirdi. Bu durum editörün emeğinin kaybolmasını önlemek için kilitlenir.

- **Sipariş Revizyonu:** Misafir "yeni" durumdaki siparişini kiosk'tan güncelleyebilir (fotoğraf ekleyip çıkarabilir, düzenleme notu yazabilir). Bu durumda sipariş "düzenlendi" damgası alır ve **listenin en başına gelir**; sıralama `created_at` değil, son dokunulma zamanı (`revised_at`) üzerinden yapılır.
- **Bayat Paket Koruması:** Sipariş içeriği değişirse `gonderilecek` klasöründeki eski zip otomatik olarak **silinir** — operatörün eski paketi yanlışlıkla göndermesi engellenir.

### Sipariş Klasörü ve Yerinde Düzenleme

Sipariş oluştuğu anda sunucuda otomatik bir çalışma klasörü oluşturulur:

```
siparis_0007/
├── 01_foto23.jpg              ← Siparişteki fotoğrafların tam çözünürlüklü kopyası
├── 02_foto41.jpg
├── 03_foto55.jpg
├── _SIPARIS_7_BILGI.txt       ← Müşteri e-postası, paket türü, foto başına özel notlar
└── _kaldirilan/               ← Müşteri sonradan foto çıkardıysa buraya taşınır (silinmez)
```

Editör bu klasörde **yerinde (in-place)** çalışır; dosyayı Photoshop'ta açar, rötuşunu yapar ve aynı dosyanın üzerine kaydeder.

> [!TIP]
> **Düzenleme Denetimi (`shutil.copy2`):** Fotoğraflar dışa aktarılırken `shutil.copy2` kullanıldığı için dokunulmamış bir dosya, orijinaliyle tamamen aynı boyuta ve değiştirilme zamanına sahiptir. İkisinden biri farklıysa dosya işlenmiştir. Paketleme sırasında panel **"3 fotoğraf hiç düzenlenmemiş"** diyerek operatörü uyarır.

---

## 🧠 Yüz Tanıma ve Müşteri Gruplama

- **Model:** **InsightFace `buffalo_l`**, `onnxruntime-gpu` (CUDA) üzerinde çalışır. Önceden eğitilmiş modeldir, ek eğitim gerektirmez.
- **Vektör Temsili:** Her yüz için **512 boyutlu embedding** çıkarılır ve veritabanında saklanır.
- **Benzerlik Ölçütü:** **Kosinüs Benzerliği** (Cosine Similarity); eşik değeri `0.40`.

### Artımsal Centroid Kümeleme

Sistemde önceden kayıtlı müşteri hesabı yoktur; mantıksal yüz grupları (`musteri_001`, `musteri_002`...) vardır. Yeni bir fotoğraf işlendiğinde, fotoğraftaki yüzler mevcut müşterilerin _centroid_ vektörleriyle (o müşteriye ait tüm yüzlerin ortalaması) karşılaştırılır:

- Eşiği geçen en yakın müşteriye atanır.
- Hiçbir eşiği geçemezse otomatik olarak yeni bir müşteri grubu açılır.
- **Centroid Artımlı Güncellenir:** Her yeni yüzde geçmişteki tüm yüzler veritabanından tekrar okunmaz; mevcut ağırlıklı ortalamaya yeni vektör matematiksel olarak eklenir:
  $$\vec{C}_{yeni} = \frac{N \cdot \vec{C}_{eski} + \vec{E}_{yeni}}{N + 1}$$

### 14 Günlük Hareket Penceresi

Yüz eşleştirme işlemi yalnızca son 14 günde hareket görmüş müşterilerle yapılır. Bu bir veri silme politikası **değildir**; veritabanındaki hiçbir yüz silinmez. Sadece eşleştirme uzayını sınırlayarak hem performansı korur hem de geçmiş sezonlardaki müşterilerle hatalı eşleşmeleri engeller.

### Arka Plan İşleme Kuyruğu

Yüklenen fotoğraflar veritabanında `pending` durumuyla kuyruğa alınır ve HTTP isteği hemen döner. Sunucu başlangıcında ayağa kalkan kalıcı işçi (`worker.py`) fotoğrafları sırayla işler:

```
pending  ──►  processing  ──►  done
                   └────────►  error   ──► (Panelden "↻ Tekrar Dene")
```

Kuyruk veritabanında tutulduğu için sunucu yeniden başlasa bile yarım kalan işler kaybolmaz.

### Görsel Önbelleği (Türevler)

Orijinal fotoğraflar 10–20 MB olabildiği için her istekte yeniden boyutlandırılmaz ve filigranlanmaz. Türevler bir kez üretilip `data/cache/` altında saklanır:

| Dosya Deseni    | Çözünürlük     | Filigran Durumu | Kullanım Yeri              |
| --------------- | -------------- | :-------------: | -------------------------- |
| `{id}_gal.jpg`  | Maks. 1400px   | **Filigranlı**  | Kiosk galeri ızgarası      |
| `{id}_full.jpg` | Orijinal boyut | **Filigranlı**  | Kiosk büyütme (Lightbox)   |
| `{id}_op.jpg`   | Maks. 1000px   | **Filigransız** | Operatör paneli önizlemesi |

Filigran, otel adının çapraz tekrar eden yarı saydam bir yazı olarak basılmasıyla oluşturulur. Otel adı panelden değiştirilirse filigranlı önbellek otomatik temizlenir.

---

## 🏛️ Mimari

| Katman                 | Teknoloji                                  | Açıklama                                         |
| ---------------------- | ------------------------------------------ | ------------------------------------------------ |
| **API & Web Sunucusu** | FastAPI + Uvicorn (Python 3.10+)           | Yüksek eşzamanlı async REST mimarisi             |
| **Veritabanı & ORM**   | PostgreSQL 17 + SQLAlchemy 2.0             | İlişkisel veri modeli ve bağlantı havuzu         |
| **Veritabanı Göçleri** | Alembic                                    | Sürüm kontrollü şema göçleri                     |
| **Yüz Tanıma**         | InsightFace `buffalo_l` + ONNX Runtime GPU | CUDA hızlandırmalı yüz tespiti ve embedding      |
| **Görüntü İşleme**     | OpenCV + Pillow                            | Görsel okuma, boyutlandırma ve filigranlama      |
| **Kullanıcı Arayüzü**  | Vanilla HTML5 / CSS3 / ES6 JavaScript      | Derleme adımı (build step) olmayan statik arayüz |

```
backend/app/
├── main.py            # Uygulama girişi, router bağlantıları, worker başlatma
├── config.py          # .env yapılandırması ve sistem sabitleri
├── database.py        # SQLAlchemy oturum ve bağlantı havuzu yönetimi
├── models.py          # PostgreSQL veritabanı modelleri
├── schemas.py         # Pydantic istek/cevap doğrulama şemaları
├── worker.py          # Kalıcı arka plan fotoğraf işleme işçisi
├── routers/           # HTTP uç noktaları (auth, photos, kiosk, orders, products...)
├── services/          # İş mantığı servisleri
│   ├── face_service.py       # InsightFace model yükleme ve yüz tespiti
│   ├── matching_service.py   # Kosinüs benzerliği ile müşteri eşleştirme
│   ├── processing.py         # Tekil fotoğraf işleme adımları
│   ├── images.py             # Önbellekli görsel türev yönetimi
│   ├── watermark.py          # Çapraz filigran basma motoru
│   ├── order_export.py       # Sipariş klasörü oluşturma
│   ├── delivery.py           # Teslimat zip paketi hazırlama
│   ├── auth_service.py       # Operatör kimlik doğrulama ve oturum
│   └── settings_service.py   # Dinamik sistem ayarları
└── static/            # Kiosk (index.html) ve Operatör Paneli (operator.html)
```

---

## 🚀 Kurulum

### Gereksinimler

- **Python 3.10 veya üzeri**
- **PostgreSQL 17** (çalışır durumda)
- **NVIDIA GPU + Güncel CUDA Sürücüsü** _(GPU bulunamazsa sistem otomatik olarak CPU moduna düşer)_

### 1. Depoyu Klonlayın ve Sanal Ortamı Kurun

```bash
git clone https://github.com/murattt00/Otel-_Photo.git
cd Otel-_Photo
python -m venv venv
venv\Scripts\activate            # Linux/macOS: source venv/bin/activate
pip install -r backend/requirements.txt
```

### 2. Veritabanını Hazırlayın

PostgreSQL üzerinde veritabanı ve kullanıcısını oluşturun:

```sql
CREATE DATABASE otel_foto_db;
CREATE USER otel_foto_user WITH PASSWORD 'guclu-bir-sifre';
GRANT ALL PRIVILEGES ON DATABASE otel_foto_db TO otel_foto_user;
\c otel_foto_db
GRANT ALL ON SCHEMA public TO otel_foto_user;
```

> [!WARNING]
> `pg_hba.conf` dosyanız `scram-sha-256` doğrulaması istiyorsa, şifreyi tanımlamadan önce `SET password_encryption TO 'scram-sha-256';` komutunu çalıştırın.

### 3. `.env` Dosyasını Yapılandırın

```bash
cp backend/.env.example backend/.env
```

Dosyayı açıp veritabanı bağlantınızı düzenleyin:

```ini
DATABASE_URL=postgresql://otel_foto_user:guclu-bir-sifre@localhost:5432/otel_foto_db
HOTEL_NAME=Grand Resort Hotel
OPERATOR_INITIAL_PASSWORD=KurulumSifresi2026
SESSION_HOURS=12
MAX_UPLOAD_MB=60
ORDERS_EXPORT_DIR=data/siparisler_export
GONDERILECEK_DIR=data/gonderilecek
```

### 4. Tabloları Oluşturun (Alembic Migration)

```bash
cd backend
python -m alembic upgrade head
```

---

## ⚙️ .env Yapılandırması

Bir ayar birden fazla yerde tanımlıysa öncelik hiyerarşisi şu şekildedir:

```
Veritabanı (Panelden Değiştirilen)  >  Ortam Değişkeni  >  backend/.env  >  Koddaki Varsayılan
```

### Temel Değişkenler

- **`DATABASE_URL` (Zorunlu):** `postgresql://kullanici:sifre@sunucu:port/veritabani`
- **`HOTEL_NAME`:** Kiosk başlığında ve fotoğrafların üzerindeki filigranda görünür. Panelden değiştirildiğinde filigran önbelleği otomatik temizlenir.
- **`OPERATOR_INITIAL_PASSWORD`:** Yalnızca ilk kurulumda operatör şifresini belirler. İlk açılıştan sonra şifre panelden değiştirilir ve veritabanında tuzlanmış (salted) hash olarak saklanır.
  - _Şifre unutulursa sıfırlama komutu:_
    ```bash
    cd backend
    python -m app.sifre_sifirla              # Varsayılan şifreye döndürür
    python -m app.sifre_sifirla YeniSifre1   # Belirtilen şifreyi kurar
    ```
- **`SESSION_HOURS`:** Operatör oturum süresi (Varsayılan: 12 saat).
- **`MAX_UPLOAD_MB`:** Tek fotoğraf için boyut tavanı (Varsayılan: 60 MB).
- **`ORDERS_EXPORT_DIR`:** Photoshop editörünün çalıştığı sipariş klasörlerinin yolu. Ağ paylaşımları için UNC yolu desteklenir (`\\EDITOR-PC\Siparisler`).
- **`GONDERILECEK_DIR`:** Hazır zip paketlerinin bırakılacağı klasör.

### Yüz Tanıma Eşik Sabitleri (`config.py`)

- `SIMILARITY_THRESHOLD = 0.40`: Kosinüs benzerliği eşiği.
- `MIN_DET_SCORE = 0.55`: Minimum tespit güven skoru.
- `MIN_FACE_WIDTH_RATIO = 0.06`: Arka plandaki küçük/alakasız yüzleri eleme oranı.
- `MATCH_WINDOW_DAYS = 14`: Eşleştirmenin bakacağı geriye dönük gün sayısı.

---

## 🖥️ Çalıştırma

Sunucuyu tüm yerel ağa açmak için:

```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Windows ortamında test için `backend\basla.bat` dosyasına çift tıklayarak `--reload` modunda yerel olarak başlatabilirsiniz.

| Arayüz                               | URL                               |
| ------------------------------------ | --------------------------------- |
| **Misafir Kiosk Ekranı**             | `http://SUNUCU-IP:8000/kiosk`     |
| **Operatör Yönetim Paneli**          | `http://SUNUCU-IP:8000/operator`  |
| **Etkileşimli Swagger API Dokümanı** | `http://SUNUCU-IP:8000/docs`      |
| **Veritabanı Sağlık Kontrolü**       | `http://SUNUCU-IP:8000/health/db` |

---

## 📖 Kullanım

1. **Fotoğrafçıları Tanımlayın:** Panel → _Fotoğrafçılar_. Fotoğraflar yüklendiğinde ilgili personele atanır ve satış primi takibi yapılır.
2. **Ürünleri / Paketleri Tanımlayın:** Panel → _Ürünler_. Sabit albüm (örn. 5 fotoğraf sabit fiyat) veya serbest seçimli adet bazlı ürünler eklenebilir.
3. **Fotoğrafları Yükleyin:**
   - _Tarayıcıdan:_ Panel → Yükleme ekranından sürükleyip bırakın.
   - _Sunucu Klasöründen İçe Alma:_ Hafıza kartını sunucudaki bir klasöre aktarıp tam yolunu verin; sistem fotoğrafları **yerinde (in-place)** işler, diskte fazladan kopya üretmez.
4. **Misafir Kiosk Deneyimi:**
   - Misafir ekrandaki butona basar, yüzünü kameraya gösterir.
   - Eşleşen fotoğraflar filigranlı olarak listelenir.
   - Fotoğrafları lightbox'ta inceler, paket seçer, özel rötuş notu yazar ve e-postasını girerek siparişi tamamlar.
   - Yüz taraması yapılamazsa e-posta ile geçmiş siparişlerine erişebilir.
5. **Operatör Siparişi İşler:**
   - Panelde _Yeni_ sekmesindeki siparişe tıklar.
   - `siparis_XXXX` klasöründe Photoshop ile fotoğrafları düzenleyip kaydeder.
   - **"✓ Hazırla ve Paketle"** butonuna basar; sistem düzenlenmemiş fotoğraf kontrolü yapar ve teslimat zip'ini `gonderilecek` klasörüne yazar.
   - Zip misafire teslim edildikten sonra **"📮 Gönderildi"** olarak işaretlenir.

---

## 🗄️ Veri Modeli

```
photographers ──< photos ──< faces >── customers
                    │           │
                    │      (512-D Embedding)
                    │
               order_items >── orders ──> products
```

| Tablo               | Açıklama                                                                          |
| ------------------- | --------------------------------------------------------------------------------- |
| `photographers`     | Fotoğrafçı personelleri ve komisyon takibi                                        |
| `customers`         | Yüz grupları (`musteri_001`...) + Centroid embedding + Yüz sayısı                 |
| `photos`            | Fotoğraf kayıtları, dosya yolları ve işleme durumları                             |
| `faces`             | Fotoğraftaki tekil yüzler ve 512-D embedding'ler (`photos` ↔ `customers` köprüsü) |
| `products`          | Albüm ve serbest seçim ürün/paket tanımları                                       |
| `orders`            | Sipariş üst bilgileri (durum, e-posta, zaman damgaları, toplam tutar)             |
| `order_items`       | Siparişteki fotoğraflar ve o fotoğrafa özel müşteri rötuş notları                 |
| `operator_auth`     | Tuzlanmış PBKDF2 operatör şifre hash'i                                            |
| `operator_sessions` | Aktif operatör oturum çerezleri                                                   |
| `app_settings`      | Panelden değiştirilebilen dinamik ayarlar (klasörler, otel adı)                   |

---

## 🔒 Güvenlik

- **Parola Güvenliği:** Operatör şifresi PBKDF2-HMAC-SHA256 ile 200.000 tur ve kayda özel rastgele tuz (salt) ile hash'lenir.
- **HttpOnly Çerezler:** Oturum belirteçleri veritabanında saklanır ve tarayıcıya `HttpOnly` olarak verilir; JavaScript erişemez (XSS koruması).
- **Kaba Kuvvet (Brute Force) Koruması:** Art arda 5 hatalı şifre denemesinde ilgili IP adresi 60 saniye boyunca kilitlenir.
- **Görsel İzolasyonu:** Filigransız tam çözünürlüklü orijinaller yalnızca doğrulanmış operatör oturumuna açılır. Kiosk yalnızca filigranlı türevleri alabilir.
- **KVKK / GDPR Uyarısı:** Yüz embedding'leri biyometrik veri niteliğindedir. Sistemi ticari üretim ortamında devreye almadan önce aydınlatma metni ve açık rıza süreçlerinin tamamlandığından emin olun.

---

## 📡 API Uçları

Tam ve etkileşimli API dokümantasyonu çalışan sunucuda `http://SUNUCU-IP:8000/docs` adresindedir.

```
Sağlık
  GET    /health                          Sunucu canlılık kontrolü
  GET    /health/db                       Veritabanı bağlantı kontrolü

Operatör Kimlik Doğrulama
  GET    /auth/durum                      Giriş durumu ve varsayılan şifre kontrolü
  POST   /auth/login                      Şifre doğrulama ve oturum açma
  POST   /auth/logout                     Oturumu kapatma
  POST   /auth/sifre-degistir             Şifre güncelleme (mevcut şifre gerekir)

Fotoğraf Yönetimi (Operatör)
  POST   /photos/upload                   Tarayıcıdan çoklu fotoğraf yükleme
  POST   /photos/ingest                   Sunucudaki klasörü yerinde içe alma
  GET    /photos                          Fotoğraf listesi ve filtreleme
  GET    /photos/durum                    İşleme kuyruğu sayaçları
  POST   /photos/tekrar-dene              Hatalı fotoğrafları tekrar kuyruğa alma
  GET    /photos/{id}/image               Görsel önizleme servisi

Müşteri, Fotoğrafçı ve Ürünler
  GET    /customers                       Müşteri yüz grupları ve fotoğraf sayıları
  GET    /customers/{id}/photos           Belirli bir müşterinin fotoğrafları
  GET    /photographers                   Fotoğrafçı listesi
  POST   /photographers                   Yeni fotoğrafçı ekleme
  GET    /products                        Ürün listesi (?sadece_aktif=true)
  POST   /products                        Yeni ürün ekleme
  PATCH  /products/{id}                   Ürün güncelleme
  DELETE /products/{id}                   Ürün silme

Kiosk (Halka Açık / Misafir)
  GET    /kiosk                           Kiosk web arayüzü
  GET    /kiosk/info                      Otel adı ve sistem bilgisi
  POST   /kiosk/scan                      Webcam karesinden müşteri yüzü tanıma
  GET    /kiosk/by-email                  E-posta adresiyle geçmiş fotoğraflara erişim

Siparişler
  POST   /orders                          Yeni sipariş oluşturma (Kiosk)
  PATCH  /orders/{id}                     Siparişi güncelleme (Yalnızca "yeni" durumda)
  GET    /orders                          Siparişleri listeleme (Operatör yetkisi gerekir)
  GET    /orders/{id}                     Sipariş detayı
  GET    /orders/sayilar                  Durum bazlı sayaçlar
  PATCH  /orders/{id}/status              Sipariş durumu güncelleme ("hazır" paketler)
  POST   /orders/{id}/gonderime-hazirla   Teslimat zip'ini yeniden oluşturma
  POST   /orders/{id}/export              Sipariş çalışma klasörünü yeniden üretme
  GET    /orders/{id}/paket               Hazır zip arşivini indirme

Ayarlar (Operatör)
  GET    /settings/klasorler              Klasör yolları ve yazılabilirlik durumları
  POST   /settings/klasorler/test         Bir yolu kaydetmeden önce yazma testi yapma
  PATCH  /settings/klasorler/{anahtar}    Klasör yolunu güncelleme
  DELETE /settings/klasorler/{anahtar}    Varsayılan klasör yoluna dönme
  GET    /settings/otel-adi               Mevcut otel adını alma
  PATCH  /settings/otel-adi               Otel adını güncelleme (filigranları yeniler)
```

---

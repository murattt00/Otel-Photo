# Otel Foto Sistemi

Otel fotoğrafçıları için yüz tanıma tabanlı fotoğraf yönetim ve satış sistemi.

Otelde çekilen binlerce fotoğraf sisteme yüklenir, sistem her fotoğraftaki yüzleri tanıyıp
aynı kişiye ait olanları otomatik gruplar. Misafir lobideki kiosk ekranında yüzünü taratır,
**sadece kendi fotoğraflarını** görür, beğendiklerini seçip sipariş verir. Sipariş operatöre
düşer, operatör fotoğrafları düzenleyip teslim paketini hazırlar.

Çözdüğü problem: eskiden misafir binlerce fotoğrafın arasında kendini elle aramak zorundaydı;
personel de hangi fotoğrafın kime ait olduğunu takip edemiyordu.

---

## İçindekiler

- [Nasıl çalışır](#nasıl-çalışır)
- [Sipariş akışı](#sipariş-akışı)
- [Yüz tanıma ve müşteri gruplama](#yüz-tanıma-ve-müşteri-gruplama)
- [Mimari](#mimari)
- [Kurulum](#kurulum)
- [.env yapılandırması](#env-yapılandırması)
- [Çalıştırma](#çalıştırma)
- [Kullanım](#kullanım)
- [Klasör yapısı](#klasör-yapısı)
- [Veri modeli](#veri-modeli)
- [Güvenlik](#güvenlik)
- [API uçları](#api-uçları)

---

## Nasıl çalışır

Sistem tek bir sunucuda çalışır, kullanıcılar tarayıcıdan bağlanır. İki arayüzü vardır:

| Arayüz | Adres | Kim kullanır |
|---|---|---|
| **Kiosk** | `/kiosk` | Misafir (lobideki dokunmatik ekran / tablet) |
| **Operatör paneli** | `/operator` | Otel personeli (şifreli giriş) |

Yüz tanıma sunucudaki GPU üzerinde çalışır; kiosk makinesinin güçlü olması gerekmez, tarayıcı
yeter.

```
 Fotoğrafçılar                Sunucu (GPU)                     Misafir
 ─────────────                ────────────                     ───────
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
 · siparişi görür, klasöründe fotoğrafları düzenler
 · "Hazırla ve Paketle" der  ──►  zip "gönderilecek" klasörüne düşer
 · zip'i misafire yollar     ──►  "Gönderildi" işaretler
```

**Sistem fotoğrafı kendisi göndermez.** Hazır zip'i gönderilecek klasörüne bırakır; operatör
onu istediği yolla (e-posta eki, WeTransfer, TransferNow…) yollar.

---

## Sipariş akışı

Her siparişin üç durumu vardır ve panelde üç sekme olarak görünür:

| Durum | Anlamı | Müşteri değiştirebilir mi? |
|---|---|---|
| 🆕 **yeni** | Misafir siparişi verdi, operatör henüz işe başlamadı | **Evet** |
| ✅ **hazır** | Operatör düzenlemeyi bitirdi, zip hazırlandı | Hayır |
| 📮 **gönderildi** | Operatör paketi misafire yolladı | Hayır |

**Kilit neden "hazır"da başlar:** operatör "Hazır" dediği an photoshop bitmiştir. Bundan
sonra gelen bir müşteri düzenlemesi, sipariş klasöründeki düzenlenmiş dosyaların yeniden
numaralanıp orijinalle değişmesine yol açardı — yani editörün emeği kaybolurdu.

Misafir "yeni" durumdaki siparişini kiosk'tan değiştirebilir (fotoğraf ekler/çıkarır, not
yazar). Bu durumda sipariş "düzenlendi" damgası alır ve **listenin başına gelir** — sıralama
`created_at` değil, son dokunulma zamanı (`revised_at`) üzerinden yapılır, yoksa üç gün önceki
bir sipariş güncellendiğinde sayfalamanın dibinde kalıp gözden kaçardı.

Sipariş içeriği değişirse gönderilecek klasöründeki eski zip **silinir** — operatör orada
duran bayat paketi yanlışlıkla yollamasın diye.

### Sipariş klasörü

Sipariş oluşur oluşmaz sunucuda bir klasör yazılır:

```
siparis_0007/
├── 01_foto23.jpg              ← siparişteki fotoğrafların full-res kopyası
├── 02_foto41.jpg
├── 03_foto55.jpg
├── _SIPARIS_7_BILGI.txt       ← e-posta, paket, toplam, foto başına düzenleme notları
└── _kaldirilan/               ← müşteri sonradan çıkardıysa buraya taşınır (silinmez)
```

Editör bu klasörde **yerinde** çalışır; dosyayı açar, photoshop yapar, kaydeder. Teslim
paketinin tek kaynağı bu klasördür — editör orada ne bıraktıysa misafire o gider. Klasör
yolu operatör panelinden ayarlanabilir, editörün makinesine Windows paylaşımı olarak
bağlanabilir.

Sistem hangi dosyanın gerçekten düzenlendiğini de anlar: export sırasında `shutil.copy2`
kullanıldığı için dokunulmamış kopya, orijinaliyle aynı boyut ve aynı değiştirilme zamanına
sahiptir. İkisinden biri farklıysa dosya işlenmiştir. Böylece paketleme sırasında panel
**"3 fotoğraf hiç düzenlenmemiş"** diye uyarır.

---

## Yüz tanıma ve müşteri gruplama

- Model: **InsightFace `buffalo_l`**, onnxruntime-gpu (CUDA) üzerinde. Hazır eğitilmiş model;
  ayrıca eğitim gerekmez.
- Her yüz için **512 boyutlu embedding** çıkarılır ve veritabanında saklanır.
- Benzerlik ölçüsü **kosinüs**; eşik `0.40`.

**Müşteri = yüz grubu.** Sistemde kayıtlı birey yoktur; `musteri_001`, `musteri_002` … diye
mantıksal klasörler vardır. Yeni bir yüz geldiğinde mevcut müşterilerin *centroid*'leriyle
(o müşterinin tüm yüzlerinin ortalaması) karşılaştırılır; eşiği geçen en yakın müşteriye
atanır, hiçbiri geçmezse yeni müşteri açılır.

Centroid her yeni yüzde **artımlı** güncellenir — her seferinde geçmişteki tüm yüzler yeniden
okunmaz.

Bir fotoğrafta birden fazla yüz olabilir, dolayısıyla bir grup fotoğrafı birden fazla
müşteride görünür. Fotoğraf diskte **tek kopya** durur; müşteri–fotoğraf ilişkisi yalnızca
veritabanındaki `faces` tablosunda tutulur.

**14 günlük pencere:** eşleştirme sadece son 14 günde hareket görmüş müşterilerle karşılaştırma
yapar. Bu bir **silme politikası değildir** — hiçbir veri silinmez, pencere yalnızca
karşılaştırma kümesini sınırlar.

### İşleme kuyruğu

Yüklenen fotoğraflar `pending` durumuyla kuyruğa girer, istek hemen döner. Uygulama açılışında
başlayan **kalıcı bir işçi (worker)** fotoğrafları sırayla işler:

```
pending  ──►  processing  ──►  done
                   └────────►  error   ──► (panelden "↻ Tekrar dene")
```

Kuyruk veritabanında tutulduğu için sunucu yeniden başlasa bile yarım kalan işler kaybolmaz.
Fotoğraflar tek elden sırayla işlendiğinden eşleştirmede yarış durumu oluşmaz. Bir fotoğraf
hata verirse diğerleri etkilenmez; panelde "3850/4000 işlendi, 2 hatalı" şeklinde görünür.

### Görsel önbelleği

Orijinal fotoğraflar 10–20 MB olabildiği için her istekte yeniden çözülüp filigranlanmaz.
Türevler bir kez üretilip `data/cache/` altında saklanır:

| Dosya | İçerik | Nerede kullanılır |
|---|---|---|
| `{id}_gal.jpg` | Filigranlı, en fazla 1400px | Kiosk galerisi |
| `{id}_full.jpg` | Filigranlı, tam boyut | Kiosk büyütme (lightbox) |
| `{id}_op.jpg` | **Filigransız**, en fazla 1000px | Operatör önizlemesi |

Filigran, otel adının çapraz tekrar eden yarı saydam bir yazı olarak basılmasıyla oluşur;
amaç misafirin ödeme yapmadan ekranı fotoğraflayıp gitmesi hâlinde görüntünün satılabilir
kalitede olmamasıdır. **Orijinal dosyaya asla dokunulmaz.** Otel adı değişirse filigranlı
türevler otomatik silinir, sonraki istekte yeni isimle üretilir.

---

## Mimari

| Katman | Teknoloji |
|---|---|
| API | FastAPI + Uvicorn (Python 3.10) |
| Veritabanı | PostgreSQL 17 + SQLAlchemy 2.0, migration: Alembic |
| Yüz tanıma | InsightFace `buffalo_l` + onnxruntime-gpu (CUDA) |
| Görüntü işleme | OpenCV (okuma/tespit), Pillow (filigran, yeniden boyutlandırma) |
| Arayüz | Bağımlılıksız HTML/CSS/JS (`app/static/`) — derleme adımı yok |

```
backend/app/
├── main.py            uygulama girişi, router'ları bağlar, işçiyi başlatır
├── config.py          .env okuma + sabitler
├── database.py        bağlantı havuzu, oturum yönetimi
├── models.py          veritabanı tabloları
├── schemas.py         istek/cevap şemaları (Pydantic)
├── worker.py          arka plan foto işleme kuyruğu
├── routers/           HTTP uçları (auth, photos, kiosk, orders, products, settings…)
├── services/          iş mantığı
│   ├── face_service.py       model yükleme + yüz tespiti
│   ├── matching_service.py   yüzü doğru müşteriye eşleştirme
│   ├── processing.py         tek fotoğrafın işlenmesi
│   ├── images.py             önbellekli görsel türevleri
│   ├── watermark.py          filigran
│   ├── order_export.py       sipariş klasörü yazma
│   ├── delivery.py           teslim paketi (zip)
│   ├── auth_service.py       operatör girişi/oturum
│   └── settings_service.py   çalışırken değişen ayarlar
└── static/            kiosk (index.html) + operatör paneli (operator.html)
```

---

## Kurulum

### Gereksinimler

- **Python 3.10+**
- **PostgreSQL 17** (kurulu ve çalışır durumda)
- **NVIDIA GPU + CUDA sürücüsü** — yüz tanıma için. CUDA bulunamazsa sistem CPU'ya düşer
  ve çalışır, ama çok daha yavaştır.
- Disk: fotoğraflar birikir, silinmez. Kapasiteyi buna göre planlayın.

### 1. Depoyu alın ve sanal ortamı kurun

```bash
git clone https://github.com/murattt00/Otel-_Photo.git
cd Otel-_Photo
python -m venv venv
venv\Scripts\activate            # Linux/macOS: source venv/bin/activate
pip install -r backend/requirements.txt
```

### 2. Veritabanını oluşturun

```sql
CREATE DATABASE otel_foto_db;
CREATE USER otel_foto_user WITH PASSWORD 'guclu-bir-sifre';
GRANT ALL PRIVILEGES ON DATABASE otel_foto_db TO otel_foto_user;
```

Ardından `otel_foto_db` içinde, PostgreSQL 15+ olduğu için `public` şemasında tablo
oluşturma izni de gerekir:

```sql
GRANT ALL ON SCHEMA public TO otel_foto_user;
```

> **Şifre şifreleme notu:** `pg_hba.conf` `scram-sha-256` istiyorsa, rol şifresini belirlerken
> önce `SET password_encryption TO 'scram-sha-256';` çalıştırın. Aksi hâlde şifre md5 ile
> kaydolur ve giriş başarısız olur.

### 3. `.env` dosyasını hazırlayın

```bash
cp backend/.env.example backend/.env
```

Sonra aşağıdaki bölüme göre doldurun.

### 4. Tabloları oluşturun

```bash
cd backend
..\venv\Scripts\python.exe -m alembic upgrade head
```

Bu komut tüm tabloları kurar. Sonraki güncellemelerde de aynı komut çalıştırılır.

---

## .env yapılandırması

`.env` dosyası **`backend/.env`** yolunda bulunur ve `backend/.env.example` dosyasından
kopyalanır. Formatı düz `ANAHTAR=deger` satırlarıdır; `#` ile başlayan satırlar yorumdur.
Değerleri tırnak içine almanız gerekmez.

**Bu dosya git'e girmez** — içinde veritabanı şifresi vardır. `.gitignore` onu dışarıda tutar.

### Öncelik sırası

Bir ayar birden fazla yerde tanımlıysa şu sırayla kazanır:

```
1. Gerçek ortam değişkeni      (varsa .env'i EZER)
2. backend/.env
3. Koddaki varsayılan
```

Klasör yolları ve otel adı için bir kademe daha vardır — bunlar **operatör panelinden**
değiştirilebildiği için veritabanındaki değer her şeyin önüne geçer:

```
Veritabanı (panel)  >  ortam değişkeni  >  .env  >  varsayılan
```

Yani bir klasörü panelden bir kez ayarladıysanız, `.env`'i değiştirmeniz artık bir şeyi
değiştirmez. Paneldeki "Varsayılana döndür" düğmesi veritabanı kaydını siler ve `.env`
değeri tekrar geçerli olur.

### Ayarlar

#### `DATABASE_URL` — **zorunlu**

Tek zorunlu ayar budur; boşsa uygulama açılmaz.

```ini
DATABASE_URL=postgresql://otel_foto_user:SIFRE@localhost:5432/otel_foto_db
```

Biçim: `postgresql://kullanici:sifre@sunucu:port/veritabani`

#### `HOTEL_NAME` — otel adı

Kiosk başlığında ve **filigranda** görünür. Varsayılan: `OTEL ADI`

```ini
HOTEL_NAME=Deniz Resort Hotel
```

Panelden de değiştirilebilir (Ayarlar sekmesi) ve normal kullanımda orası tercih edilir —
panelden değiştirince filigranlı önbellek otomatik temizlenir, `.env`'den değiştirince
temizlenmez.

#### `OPERATOR_INITIAL_PASSWORD` — kurulum şifresi

Panelin ilk açılışında veritabanına yazılan şifre. Varsayılan: `otel123`

```ini
OPERATOR_INITIAL_PASSWORD=IlkKurulumSifresi
```

> **Önemli:** bu değer **yalnızca ilk açılışta** kullanılır. Şifre kaydı bir kez oluştuktan
> sonra `.env`'i değiştirmek hiçbir şey yapmaz — şifre panelden değiştirilir ve veritabanında
> hash'li tutulur. Kurulum şifresi kullanıldığı sürece panelde "şifrenizi değiştirin"
> uyarısı görünür.

Şifre unutulursa:

```bash
cd backend
..\venv\Scripts\python.exe -m app.sifre_sifirla              # varsayılana döndürür
..\venv\Scripts\python.exe -m app.sifre_sifirla YeniSifre1   # belirtilen şifreyi kurar
```

#### `SESSION_HOURS` — oturum süresi (saat)

Operatörün ne kadar süre giriş yapmış kalacağı. Varsayılan: `12` (bir vardiyayı kapsar,
ertesi gün tekrar giriş ister).

```ini
SESSION_HOURS=12
```

#### `MAX_UPLOAD_MB` — tek fotoğraf boyut sınırı

Bundan büyük dosyalar atlanır ve rapor edilir. Varsayılan: `60`

```ini
MAX_UPLOAD_MB=60
```

#### `ORDERS_EXPORT_DIR` — sipariş klasörlerinin yazılacağı yer

Her sipariş buraya `siparis_XXXX` klasörü olarak düşer; editör burada çalışır.
Varsayılan: `data/siparisler_export`

```ini
ORDERS_EXPORT_DIR=C:\Siparisler
```

#### `GONDERILECEK_DIR` — hazır paketlerin düşeceği yer

"Hazırla ve Paketle" denince `siparis_XXXX.zip` buraya düşer. Operatörün kolay ulaşabileceği
bir klasör olmalı. Varsayılan: `data/gonderilecek`

```ini
GONDERILECEK_DIR=C:\Gonderilecek
```

> **Yollar sunucunun gözünden çözülür**, operatörün kendi bilgisayarından değil. Operatör
> ayrı bir makinedeyse `D:\Siparisler` yazmak **sunucunun** D diskini gösterir. Editörün
> makinesindeki bir klasör hedefleniyorsa UNC yolu kullanın: `\\EDITOR-PC\Siparisler`

### Örnek tam `.env`

```ini
# --- Veritabani (zorunlu) ---
DATABASE_URL=postgresql://otel_foto_user:cok-gizli-sifre@localhost:5432/otel_foto_db

# --- Marka ---
HOTEL_NAME=Deniz Resort Hotel

# --- Operator girisi ---
OPERATOR_INITIAL_PASSWORD=KurulumSifresi2026
SESSION_HOURS=12

# --- Yukleme ---
MAX_UPLOAD_MB=60

# --- Klasorler (panelden de ayarlanabilir) ---
ORDERS_EXPORT_DIR=C:\Siparisler
GONDERILECEK_DIR=C:\Gonderilecek
```

### `.env`'de olmayan ayarlar

Yüz tanıma eşikleri `backend/app/config.py` içinde sabittir; gerçek veriyle ayarlanmaları
gerekir:

| Sabit | Değer | Anlamı |
|---|---|---|
| `SIMILARITY_THRESHOLD` | `0.40` | Bu kosinüs benzerliğinin üstü "aynı kişi" sayılır |
| `MIN_DET_SCORE` | `0.55` | Tespit güven skoru; altındaki yüzler elenir |
| `MIN_FACE_WIDTH_RATIO` | `0.06` | Yüz genişliği / foto genişliği; arka plandaki küçük yüzler elenir |
| `MATCH_WINDOW_DAYS` | `14` | Eşleştirmenin kaç günlük müşteriye bakacağı |

Eşiği **yükseltmek** yanlış eşleşmeyi azaltır ama aynı kişinin fotoğrafları birden fazla
klasöre bölünebilir; **düşürmek** ise farklı kişileri aynı klasörde toplayabilir.

---

## Çalıştırma

```bash
cd backend
..\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` ağdaki diğer makinelerin (kiosk tableti, operatörün bilgisayarı) bağlanmasını
sağlar. Sadece sunucunun kendisinden erişilecekse `127.0.0.1` kullanın.

Windows'ta `backend\basla.bat` dosyasına çift tıklayarak da başlatabilirsiniz; bu betik
`--reload` ile ve **yalnızca yerel makineye açık** olarak (`127.0.0.1:8000`) çalıştırır —
yani tek makinede deneme içindir. Kiosk ve operatör ayrı makinelerdeyse yukarıdaki
`--host 0.0.0.0` komutunu kullanın.

| Adres | Açıklama |
|---|---|
| `http://SUNUCU-IP:8000/kiosk` | Misafir ekranı |
| `http://SUNUCU-IP:8000/operator` | Operatör paneli |
| `http://SUNUCU-IP:8000/docs` | Otomatik API dokümantasyonu (Swagger) |
| `http://SUNUCU-IP:8000/health/db` | Veritabanı bağlantı kontrolü |

Sunucu açılırken yüz tanıma modeli belleğe yüklenir; ilk açılış birkaç saniye sürebilir.

---

## Kullanım

### 1. Fotoğrafçıları tanımlayın

Panel → **Fotoğrafçılar**. Her fotoğraf bir fotoğrafçıya bağlanır; böylece hangi fotoğrafın
kim tarafından çekildiği ve satıştan kimin payı olduğu takip edilebilir
(`OrderItem → Photo → Photographer`).

### 2. Ürünleri tanımlayın

Panel → **Ürünler**. İki tip vardır:

| Tip | `photo_count` | Fiyatlandırma |
|---|---|---|
| Sabit albüm | ör. `5` | Sabit fiyat; müşteri **tam olarak** 5 fotoğraf seçmek zorunda |
| Serbest seçim | boş | Fotoğraf başına fiyat × seçilen adet |

Pasife alınan ürün kiosk'ta görünmez.

### 3. Fotoğrafları yükleyin

İki yol vardır:

**Tarayıcıdan yükleme** — Panel → Yükleme. Fotoğrafçıyı seçip dosyaları sürükleyin. Küçük
partiler için uygundur.

**Sunucudaki klasörden içe alma** — Hafıza kartını sunucudaki bir klasöre kopyalayın, panele
o klasörün tam yolunu verin. Sistem klasörü (alt klasörler dâhil) tarar ve fotoğrafları
**yerinde** işler; ikinci bir kopya oluşturmaz. Büyük partiler için bu yol çok daha hızlıdır.

Her iki durumda da istek hemen döner, işleme arka planda sürer. İlerlemeyi panelin işleme
durumu kutusundan izleyebilirsiniz.

### 4. Misafir kiosk'ta

1. Ekrandaki düğmeye basıp yüzünü kameraya gösterir.
2. Sistem eşleşen müşteri klasörünü bulur ve o kişinin fotoğraflarını **filigranlı** listeler.
3. Misafir fotoğrafları büyütüp inceler, beğendiklerini seçer.
4. Paket/albüm seçer, isterse her fotoğrafa özel not yazar ("arka plandaki kişiyi silin" gibi).
5. E-postasını girip siparişi onaylar.

Yüz taraması işe yaramazsa **e-posta ile giriş** alternatifi vardır: daha önce sipariş
verdiyse e-postasıyla fotoğraflarına ulaşır.

Misafir daha sonra tekrar gelip "yeni" durumdaki siparişini düzenleyebilir.

### 5. Operatör siparişi işler

1. Panel → **Siparişler** → 🆕 Yeni sekmesi. Karta tıklayınca fotoğraflar ve istenen
   düzenleme notları görünür.
2. Editör, `siparis_XXXX` klasöründeki dosyaları açıp düzenler ve kaydeder.
3. **"✓ Hazırla ve Paketle"** — sipariş "hazır" olur ve zip aynı anda gönderilecek klasörüne
   düşer. Hiç düzenlenmemiş fotoğraf varsa panel uyarır.
4. Operatör zip'i misafire yollar, sonra **"📮 Gönderildi"** işaretler.

Editör dosyalara sonradan dokunursa **"🔄 Yeniden Paketle"** ile zip tazelenir.
Yanlışlıkla ilerletilen sipariş **"↩ Geri Al"** ile geri çekilebilir; bu durumda gönderilecek
klasöründeki paket silinir.

### 6. Ayarlar

Panel → **Ayarlar**: otel adı ve üç klasör yolu (sipariş, gönderilecek, yükleme) buradan
değiştirilir. Kaydetmeden önce sistem yolun gerçekten **yazılabilir** olduğunu test eder —
ağ paylaşımlarında klasör görünür ama yazılamaz olabilir.

---

## Klasör yapısı

```
otel-foto-sistemi/
├── backend/
│   ├── app/                 uygulama kodu
│   ├── alembic/             veritabanı migration'ları
│   ├── requirements.txt
│   ├── .env                 (git'e girmez — siz oluşturursunuz)
│   └── .env.example
├── data/                    (git'e girmez)
│   ├── raw_uploads/         tarayıcıdan yüklenen orijinaller
│   ├── cache/               filigranlı/küçültülmüş türevler
│   ├── siparisler_export/   siparis_XXXX klasörleri (editör burada çalışır)
│   ├── gonderilecek/        hazır zip paketleri
│   └── edited/              eski düzenleme dosyaları
├── docs/
└── scripts/                 yüz tanıma deneme betikleri
```

`data/` altındaki hiçbir şey depoya girmez. `.gitignore` ayrıca görsel, arşiv ve veritabanı
yedeği uzantılarını **repoda nerede olursa olsun** dışarıda tutar; yanlışlıkla misafir
fotoğrafı commit'lemeyi engeller.

---

## Veri modeli

| Tablo | İçerik |
|---|---|
| `photographers` | Fotoğrafı çeken personel |
| `customers` | **Yüz grubu** (`musteri_001`…) + centroid + yüz sayısı |
| `photos` | Yüklenen her fotoğraf + işleme durumu |
| `faces` | Bir fotoğraftaki tek bir yüz + 512 boyutlu embedding. `photos` ↔ `customers` köprüsü |
| `products` | Satılan albüm/paket tanımları |
| `orders` | Sipariş: durum, e-posta, ürün, zaman damgaları |
| `order_items` | Siparişteki tek bir fotoğraf + o fotoğrafa özel not |
| `operator_auth` | Operatör şifresinin hash'i (tek satır) |
| `operator_sessions` | Açık oturumlar |
| `app_settings` | Çalışırken değiştirilebilen ayarlar (klasör yolları, otel adı) |

Bir fotoğrafta birden çok yüz olabildiği için `faces` tablosu çoktan-çoğa ilişki kurar:
aynı grup fotoğrafı birden fazla müşterinin galerisinde görünür.

---

## Güvenlik

- **Operatör paneli tek paylaşılan şifreyle korunur.** Şifre düz metin saklanmaz:
  PBKDF2-HMAC-SHA256, 200.000 tur, kayda özel rastgele salt.
- Oturum belirteci veritabanında tutulur ve tarayıcıya **HttpOnly** çerez olarak verilir —
  JavaScript okuyamaz. Veritabanında tutulduğu için sunucu yeniden başlayınca oturum düşmez,
  "çıkış" da belirteci gerçekten geçersiz kılar.
- Şifre değiştirilince **tüm oturumlar kapatılır**.
- Art arda 5 hatalı denemeden sonra o IP 60 saniye kilitlenir.
- Şifre kuralları: en az 8 karakter, sadece rakam olamaz, yaygın şifreler reddedilir.
- **Filigransız orijinaller yalnızca giriş yapmış operatöre** servis edilir. Kiosk sadece
  filigranlı sürümleri görebilir.
- **Kiosk bu korumanın dışındadır** — misafirin önündeki makinede giriş ekranı olamaz.

> Sistem düz HTTP üzerinden otel yerel ağında çalışır; çerezde `secure` bayrağı bu yüzden
> kapalıdır. HTTPS eklenirse açılmalıdır.

Yüz embedding'leri biyometrik veri sayılır. Sistemi üretimde kullanmadan önce KVKK
kapsamındaki aydınlatma ve açık rıza yükümlülüklerini karşıladığınızdan emin olun.

---

## API uçları

Tam ve etkileşimli dokümantasyon çalışan sunucuda `/docs` adresindedir.

**Sağlık**
```
GET    /health                          sunucu ayakta mı
GET    /health/db                       veritabanı bağlantısı
```

**Operatör girişi**
```
GET    /auth/durum                      giriş var mı, hâlâ varsayılan şifre mi
POST   /auth/login                      şifre doğrula, oturum çerezi ver
POST   /auth/logout                     oturumu kapat
POST   /auth/sifre-degistir             şifre değiştir (mevcut şifre gerekir)
```

**Fotoğraflar** *(operatör girişi gerekir)*
```
POST   /photos/upload                   tarayıcıdan foto yükle
POST   /photos/ingest                   sunucudaki klasörü yerinde içe al
GET    /photos                          tüm fotoğraflar
GET    /photos/durum                    işleme kuyruğu özeti
POST   /photos/tekrar-dene              hatalı fotoğrafları kuyruğa geri al
GET    /photos/{id}/image               görsel (filigranlı sürüm girişsiz de açık)
```

**Müşteriler / fotoğrafçılar / ürünler**
```
GET    /customers                       müşteri klasörleri + foto sayıları
GET    /customers/{id}/photos           bir müşterinin fotoğrafları
GET    /photographers                   fotoğrafçı listesi
POST   /photographers                   fotoğrafçı ekle
GET    /products                        ürünler (?sadece_aktif=true)
POST   /products                        ürün ekle
PATCH  /products/{id}                   ürün güncelle
DELETE /products/{id}                   ürün sil
```

**Kiosk** *(girişsiz — misafir kullanır)*
```
GET    /kiosk                           kiosk arayüzü
GET    /kiosk/info                      otel adı vb.
POST   /kiosk/scan                      webcam karesinden müşteriyi tanı
GET    /kiosk/by-email                  e-posta ile geçmiş siparişe ulaş
```

**Siparişler**
```
POST   /orders                          sipariş oluştur (kiosk)
PATCH  /orders/{id}                     siparişi güncelle (yalnızca "yeni" durumda)
GET    /orders                          listele (filtresiz çağrı operatör girişi ister)
GET    /orders/{id}                     sipariş detayı
GET    /orders/sayilar                  durum bazlı sayaçlar
PATCH  /orders/{id}/status              durum değiştir ("hazır" aynı anda paketler)
POST   /orders/{id}/gonderime-hazirla   zip'i yeniden üret
POST   /orders/{id}/export              sipariş klasörünü yeniden oluştur
GET    /orders/{id}/paket               hazır zip'i indir
```

**Ayarlar** *(operatör girişi gerekir)*
```
GET    /settings/klasorler              klasör yolları ve durumları
POST   /settings/klasorler/test         bir yolu kaydetmeden dene
PATCH  /settings/klasorler/{anahtar}    klasör yolunu değiştir
DELETE /settings/klasorler/{anahtar}    varsayılana döndür
GET    /settings/otel-adi               otel adını oku
PATCH  /settings/otel-adi               otel adını değiştir
```

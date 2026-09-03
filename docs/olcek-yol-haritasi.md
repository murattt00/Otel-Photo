# Ölçek Yol Haritası — Üretim Hazırlığı

Bu belge, sistemin gerçek üretim yüküne (~4000 foto/gün, büyük dosyalar) dayanacak hâle
getirilmesi için yapılacakları önceliklendirilmiş şekilde tanımlar.

## Ölçek Varsayımları

| Metrik | Değer |
|---|---|
| Fotoğrafçı sayısı | ~4 (değişebilir) |
| Foto/fotoğrafçı/gün | ~1000+ |
| Toplam foto/gün | **~4000** |
| Foto boyutu (yüksek çöz. JPEG) | ~10–20 MB (ort. ~15 MB) |
| Günlük veri | **~60 GB/gün** |
| Aktif pencere (14 gün) | **~840 GB** çalışan set |
| Yüz kaydı (14 gün) | **~110.000** embedding |
| Aktif müşteri kümesi (14 gün) | ~1.000–5.000 |

## Şu Anki Tasarımın 4 Darboğazı

1. **Tek dev yükleme isteği** — 4000 foto tek HTTP isteğinde = ~60 GB tek istek. Dakikalarca
   sürer, ilerleme yok, ağ kopması = baştan. Kırılgan.
2. **FastAPI BackgroundTasks ile işleme** — kalıcı değil, sıra/yeniden deneme yok, sunucu
   yeniden başlarsa yarım kalan işler kaybolur.
3. **Fiziksel klasör kopyalama** — `classification.py` her fotoyu müşteri klasörüne KOPYALIYOR;
   grup fotoları birden çok klasöre → depolama **1.5–2× şişer** (~840 GB yerine ~1.5 TB).
4. **Karesel (N²) eşleştirme** — her yeni yüz için son 14 günün TÜM embedding'lerini tekrar
   çekip centroid hesaplıyor. 110.000 yüzde ciddi yavaşlar.

---

## Yol Haritası (öncelik sırasıyla)

### Faz A — Yükleme Dayanıklılığı  ⏱️ ÖNCE (üretimden önce şart)
- **A1. Parçalı yükleme + ilerleme:** Tarayıcı 25–50'lik gruplar hâlinde gönderir; "1240/4000"
  ilerleme, grup takılırsa sadece o tekrar dener. Tek 60 GB'lık riskli istek biter.
- **A2. (Güçlü öneri) Sunucu-tarafı klasör ingestion:** Operatör kartı sunucudaki bir klasöre
  kopyalar; sistem o klasörü tarayıp işler. 60 GB'ı tarayıcıdan HTTP ile göndermekten **kat kat
  hızlı ve sağlam** (özellikle operatör = sunucu makinesi ise dosyalar zaten yerelde). "İzlenen
  klasör" (watch folder) mantığı.
- **A3. Dosya doğrulama:** tür (jpg/png), maksimum boyut, bozuk dosya atlanır ve raporlanır.

### Faz B — İşleme Motoru  ⏱️ ÖNCE
- **B1. Kalıcı kuyruk + tek worker:** BackgroundTasks yerine gerçek kuyruk. Fotolar sırayla,
  tek elden işlenir (yarış hatası yok — bkz. müşteri numarası çakışması). Sunucu yeniden
  başlarsa kaldığı yerden devam.
- **B2. Durum takibi + yeniden deneme:** `Photo.is_processed` + hata durumu; başarısızlar
  yeniden denenir; operatör panelinde "3850/4000 işlendi, 2 hatalı" görünür.
- **B3. Bellek-dostu okuma:** büyük dosyaları belleğe tamamen almadan diske akıt (stream).

### Faz C — Depolama Verimliliği  ⏱️ ÖNCE
- **C1. Kopyalamayı kaldır:** Fiziksel müşteri klasörü kopyalama yerine sadece DB ilişkisi
  (`Face.customer_id`). Depolamayı ~1.5–2× azaltır. Kiosk/operatör zaten ilişkiden okuyor.
- **C2. Önizleme/thumbnail üretimi (ingest'te):** Her foto için bir kez küçük filigranlı önizleme
  + küçük thumbnail üretilip diske önbelleklenir. Kiosk'a 15 MB orijinali her seferinde decode
  edip servis etmek yerine hazır küçük dosya servis edilir (CPU + bant genişliği tasarrufu).
- **C3. Düzenli saklama:** orijinaller tarih/fotoğrafçı klasör yapısında; öngörülebilir yol.

### Faz D — Eşleştirme Ölçeği  ⏱️ YAKIN
- **D1. Artımlı centroid:** Her müşterinin centroid'i + yüz sayısı `Customer`'da saklanır; yeni
  yüz eklenince güncellenir. Eşleştirme = yeni yüzü ~birkaç bin centroid ile karşılaştır (numpy'de
  milisaniyeler). N² problemi biter. **En kritik ölçek düzeltmesi.**
- **D2. (Gerekirse) pgvector + ANN index:** Müşteri sayısı on binlere çıkarsa yaklaşık en-yakın-
  komşu index'i. Windows'ta eklenti kurulumu gerekir; bu ölçekte muhtemelen D1 yeterli.

### Faz E — Saklama Politikası  ⏱️ YAKIN
- **KARAR (kullanıcı, 2026-07-08):** 14 gün sonrası veri **SİLİNMEYECEK** — tüm fotolar ve yüz
  verileri kalıcı kalır. 14 günlük periyot **yalnızca eşleştirme modelinin** hangi müşterilerle
  karşılaştırma yapacağını sınırlar (matching `updated_at >= son 14 gün`). Otomatik silme YOK.
- **E1. Sonuç — depolama sınırsız büyür:** ~60 GB/gün birikir (~1.8 TB/ay). İleride "orijinalleri
  arşiv/harici diske taşıma" stratejisi gerekebilir. Disk planlaması buna göre yapılmalı.
- **E2. KVKK notu (açık risk):** Biyometrik embedding'leri süresiz saklamak özel nitelikli
  kişisel veri açısından yasal risk. İleride en azından embedding'ler için bir saklama süresi
  (fotoları tutmaya devam ederek) yeniden değerlendirilmeli.
- **E3. Disk izleme/uyarı:** doluluk eşiği aşılınca uyarı.

### Faz F — Donanım / Dağıtım Notları
- **Disk:** 14 günlük pencere ~840 GB → en az **1.5–2 TB NVMe SSD** (hız yükleme+decode için önemli).
  Kopyalama kaldırılınca (C1) ~840 GB'a iner. Daha uzun saklama istenirse dış/arşiv disk.
- **RAM:** 32 GB önerilir (büyük görsel decode + Postgres + model).
- **GPU:** mevcut kurulum (CUDA + buffalo_l) bu yük için yeterli; 4000 foto/gün ≈ birkaç on dakika
  GPU işi.
- **Ağ:** operatör ayrı makinedeyse LAN'da Gigabit Ethernet şart (60 GB/gün transfer). Operatör =
  sunucu ise sorun yok (A2 ingestion ile).
- **Yedekleme:** siparişler + orijinaller için (en azından teslim edilene kadar).

---

## Önerilen Sıra (özet)
1. **Faz A + B + C birlikte** (üretimden önce): yükleme + işleme + depolama sağlam olmadan
   gerçek kullanım riskli.
2. **Faz D1** (artımlı centroid): veri büyümeden önce ekle.
3. **Faz F** (donanım/disk planı): silme olmadığı için depolama büyümesine göre.
4. Faz D2: ölçek gerçekten büyüyünce.

Not: Faz E (otomatik silme) kullanıcı kararıyla KALDIRILDI — veri kalıcı, 14 gün sadece
eşleştirme penceresi. Depolama planı buna göre yapılmalı (Faz F).

Not: Faz A–E tamamlanınca sistem "gerçek otel yükü"ne hazır olur. Öncesinde küçük/orta hacimde
sorunsuz çalışır ama yüksek hacimde kırılgandır.

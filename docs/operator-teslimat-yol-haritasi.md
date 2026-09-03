# Operatör Tarafı + Teslimat — Analiz ve Yol Haritası

Kiosk (müşteri) tarafı MVP olarak tamamlandı. Bu belge, operatörün gerçek iş akışı
(photoshop → teslimat) ve üretim kaygıları için yapılacakları tanımlar.

## Durum Özeti (2026-07-10)
- **Tamam:** backend çekirdeği, foto yükleme + otomatik yüz tanıma, kiosk tam döngü (tara/e-posta
  → galeri → tek ekran sepet → sipariş → düzenle), operatör ürün+sipariş yönetimi, fiyatlandırma
  (serbest/sabit), ölçek sağlamlaştırması (kuyruk, kopyasız, artımlı centroid, önbellek).
- **Eksik:** operatör state/gerçek-zaman, photoshop re-upload, teslimat, operatör auth, KVKK,
  fotoğrafçı satış raporu, tasarım revizyonu.

## 1) Operatör state yönetimi + gerçek zamanlı bildirim
- Sorun: düz JS, veri/çizim iç içe, manuel "Yenile", yeni sipariş anında görünmüyor.
- Yapılacak: sipariş listesini **otomatik yenile** (polling ~10sn) veya **WebSocket** (anında
  "🔔 yeni sipariş" + ses). State'i tek merkezde topla, hedefli render. Tasarım revizyonuyla
  birlikte yapılması mantıklı.

## 2) Photoshop → düzenlenmiş fotoyu geri yükleme
- **KARAR: orijinali + düzenlenmiş versiyonu İKİSİNİ DE tut** (orijinali silme/üzerine yazma).
  Neden: yüz tanıma orijinalden yapıldı; hatalı düzenlemede geri dönüş; tekrar sipariş; maliyet
  düşük (sadece sipariş edilen fotolar düzenlenir).
- Uygulama: `OrderItem.edited_path` (nullable). Operatör panelinde her sipariş fotosunun yanında
  "Photoshop'lu hâlini yükle" → o order item'a bağlanır, "düzenlendi" işaretlenir. **Teslimatta
  edited varsa o, yoksa orijinal** gönderilir. Orijinal dosyaya dokunulmaz.

## 3) Yedekleme
- **KARAR: uygulamaya gömme** (kullanıcı elle harddiske kopyalıyor). Şartlar:
  - Tüm orijinaller **tek düzenli klasörde** olsun (tarih/fotoğrafçı) → kopyalaması kolay; panelde
    yol gösterilsin.
  - **Uyarı:** sadece foto kopyalamak DB'yi (siparişler, yüz eşleşmeleri, edited) yedeklemez.
    Tam geri yükleme için ayda bir **`pg_dump`** de alınmalı (tek tıklık script verilebilir).

## 4) Teslimat — e-posta (WeTransfer yerine)
- **"E-posta kaliteyi düşürür" → MİT.** Ekli JPEG olduğu gibi gider, yeniden sıkışmaz. Algı,
  fotoyu mail gövdesine gömmekten gelir; ek olarak gönderince düşmez.
- **Asıl engel BOYUT:** e-posta eki limiti ~20-25 MB; tek foto 10-20 MB → birkaç foto aşar.
  WeTransfer kalite için değil, büyük dosya için kullanılıyor. Zip de çözmez (JPEG sıkışmaz).
- **Çözüm — kendi WeTransfer'imiz: indirme LİNKİ gönder.** Sipariş hazır olunca full-res
  (edited varsa edited) fotolar zip'lenir, İNTERNETTEN erişilebilir bir **bulut depoya** (B2/S3/
  Drive) yüklenir, **link e-postayla** yollanır. (Yerel LAN linki müşteri otelden ayrılınca
  çalışmaz — bu yüzden bulut şart.)
- **Kademeli:** küçük sipariş (≲20MB, ör. 1 foto) = doğrudan **e-posta eki**; büyük = **bulut+link**.
- Gereksinim: SMTP hesabı (otel maili / SendGrid / Gmail SMTP) + büyük dosya için bulut depo +
  internet.

## Önerilen Sıra (Faz 3)
1. **Photoshop re-upload** (OrderItem.edited_path + operatör yükleme) — iş akışının kalbi.
2. **Teslimat** (e-posta: küçükte ek, büyükte bulut+link) — photoshop'a bağlı.
3. **Operatör state + gerçek zamanlı bildirim** (tasarım revizyonuyla birlikte).
4. **Operatör auth** (şifreli giriş) — teslimat/veri erişimi hassaslaşınca.
5. **KVKK rıza akışı** (biyometrik veri — yasal, üretim öncesi).
6. **Fotoğrafçı satış raporu** (kolay, veri hazır: OrderItem→Photo→Photographer).
7. **DB yedek script'i** (pg_dump, isteğe bağlı tek tık).

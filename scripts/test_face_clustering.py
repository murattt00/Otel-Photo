"""
Yuz embedding'lerine gore fotograflari musteri klasorlerine ayirma testi.

Mantik:
- Her fotoyu sirayla isle (dosya adina gore siralama yeterli)
- Her yuz icin, mevcut klasorlerin centroid (ortalama) embedding'i ile cosine similarity hesapla
- Esik degerini gecen en yuksek benzerlikli klasore ekle, centroid'i guncelle
- Hicbiri esigi gecmiyorsa yeni klasor ac

Calistirma (backend/ klasorunden):
    python ../scripts/test_face_clustering.py
"""
import os
import sys
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app import gpu_setup  # noqa: F401

import cv2
import numpy as np
from insightface.app import FaceAnalysis

RAW_UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw_uploads")
CUSTOMER_FOLDERS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "customer_folders")

# ---- Ayarlanabilir esik degeri ----
# Baslangic degeri, kendi fotograflarinla deneyip ayarlayacagiz
SIMILARITY_THRESHOLD = 0.40

# Arka plandaki kucuk/alakasiz yuzleri elemek icin filtreler
MIN_DET_SCORE = 0.55          # tespit guven skoru bunun altindaysa yuz sayilmaz
MIN_FACE_WIDTH_RATIO = 0.06   # yuzun genisligi, foto genisliginin bu oranindan kucukse sayilmaz


def cosine_similarity(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


class CustomerFolder:
    """Bir musteriye ait klasoru ve o klasordeki yuzlerin ortalama embedding'ini (centroid) tutar."""

    def __init__(self, folder_id):
        self.folder_id = folder_id
        self.embeddings = []  # bu klasordeki tum yuz embedding'leri
        self.photo_files = set()  # bu klasore eklenen foto dosya adlari (tekrar kopyalamamak icin)

    @property
    def centroid(self):
        return np.mean(self.embeddings, axis=0)

    def add_face(self, embedding, photo_filename):
        self.embeddings.append(embedding)
        self.photo_files.add(photo_filename)


def main():
    print("InsightFace modeli yukleniyor...")
    app = FaceAnalysis(name="buffalo_l", providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    app.prepare(ctx_id=0, det_size=(640, 640))
    print("Model hazir.\n")

    # Onceki test klasorlerini temizle (her calistirmada sifirdan basla)
    if os.path.exists(CUSTOMER_FOLDERS_DIR):
        shutil.rmtree(CUSTOMER_FOLDERS_DIR)
    os.makedirs(CUSTOMER_FOLDERS_DIR, exist_ok=True)

    image_files = sorted([
        f for f in os.listdir(RAW_UPLOADS_DIR)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ])

    if not image_files:
        print(f"UYARI: {RAW_UPLOADS_DIR} klasorunde fotograf yok.")
        return

    folders = []
    next_folder_num = 1

    for filename in image_files:
        filepath = os.path.join(RAW_UPLOADS_DIR, filename)
        img = cv2.imread(filepath)
        if img is None:
            continue

        faces = app.get(img)
        img_width = img.shape[1]

        # Kucuk / dusuk guvenilirlikli yuzleri ele
        filtered_faces = []
        skipped_count = 0
        for face in faces:
            bbox = face.bbox
            face_width = bbox[2] - bbox[0]
            width_ratio = face_width / img_width

            if face.det_score < MIN_DET_SCORE or width_ratio < MIN_FACE_WIDTH_RATIO:
                skipped_count += 1
                continue
            filtered_faces.append(face)

        skip_txt = f" ({skipped_count} kucuk/belirsiz yuz elendi)" if skipped_count else ""
        print(f"{filename}: {len(filtered_faces)} yuz{skip_txt}")

        for face in filtered_faces:
            embedding = face.embedding

            # Mevcut klasorlerle karsilastir
            best_folder = None
            best_score = -1.0

            for folder in folders:
                score = cosine_similarity(embedding, folder.centroid)
                if score > best_score:
                    best_score = score
                    best_folder = folder

            if best_folder is not None and best_score >= SIMILARITY_THRESHOLD:
                best_folder.add_face(embedding, filename)
                print(f"    -> Eslesme: {best_folder.folder_id} (benzerlik={best_score:.3f})")
            else:
                new_folder = CustomerFolder(f"musteri_{next_folder_num:03d}")
                next_folder_num += 1
                new_folder.add_face(embedding, filename)
                folders.append(new_folder)
                score_txt = f"{best_score:.3f}" if best_folder else "yok"
                print(f"    -> Yeni klasor: {new_folder.folder_id} (en yakin benzerlik={score_txt})")

    # Fotograflari gercekten klasorlere kopyala (gozle kontrol icin)
    print(f"\n{len(folders)} musteri klasoru olustu. Fotograflar kopyalaniyor...\n")
    for folder in folders:
        folder_path = os.path.join(CUSTOMER_FOLDERS_DIR, folder.folder_id)
        os.makedirs(folder_path, exist_ok=True)
        for photo_filename in folder.photo_files:
            src = os.path.join(RAW_UPLOADS_DIR, photo_filename)
            dst = os.path.join(folder_path, photo_filename)
            shutil.copy2(src, dst)
        print(f"  {folder.folder_id}: {len(folder.photo_files)} foto")

    print(f"\nTamamlandi. {CUSTOMER_FOLDERS_DIR} klasorunu ac ve kontrol et.")
    print("Her musteri_XXX klasorunun icinde SADECE o kisiye ait fotolar olmali.")
    print("Eger karisiklik varsa (yanlis kisi baska klasorde / ayni kisi 2 klasorde),")
    print(f"SIMILARITY_THRESHOLD degerini (su an {SIMILARITY_THRESHOLD}) ayarlamamiz gerekecek.")


if __name__ == "__main__":
    main()
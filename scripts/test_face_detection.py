"""
InsightFace ile yuz tespiti ve embedding cikarma testi.

Calistirma (backend/ klasorunden):
    python ../scripts/test_face_detection.py

Bu script:
1. data/raw_uploads/ klasorundeki fotograflari okur
2. Her fotografta yuzleri tespit eder
3. Her yuz icin embedding (512 boyutlu vektor) cikarir
4. Tespit edilen yuzlerin etrafina kutu cizip data/debug_output/ klasorune kaydeder
   (goz ile dogrulama yapabilelim diye)
"""
import os
import sys
import time

# backend/app icindeki gpu_setup modulunu bulabilmesi icin path ekliyoruz
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app import gpu_setup  # noqa: F401 -- CUDA DLL yollarini ayarlar

import cv2
import numpy as np
from insightface.app import FaceAnalysis

# ---- Ayarlar ----
RAW_UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw_uploads")
DEBUG_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "debug_output")

os.makedirs(DEBUG_OUTPUT_DIR, exist_ok=True)


def main():
    print("InsightFace modeli yukleniyor (ilk calistirmada model indirilecek, biraz surebilir)...")

    app = FaceAnalysis(name="buffalo_l", providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
    app.prepare(ctx_id=0, det_size=(640, 640))

    print("Model hazir.\n")

    image_files = [
        f for f in os.listdir(RAW_UPLOADS_DIR)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ]

    if not image_files:
        print(f"UYARI: {RAW_UPLOADS_DIR} klasorunde hic fotograf bulunamadi.")
        print("Lutfen bu klasore birkac test fotografi koy ve tekrar calistir.")
        return

    print(f"{len(image_files)} fotograf bulundu, isleniyor...\n")

    for filename in image_files:
        filepath = os.path.join(RAW_UPLOADS_DIR, filename)
        img = cv2.imread(filepath)

        if img is None:
            print(f"  [HATA] {filename} okunamadi, atlaniyor.")
            continue

        start = time.time()
        faces = app.get(img)
        elapsed = time.time() - start

        print(f"{filename}: {len(faces)} yuz bulundu ({elapsed*1000:.0f} ms)")

        # Her yuz icin bilgi yazdir + kutu ciz
        debug_img = img.copy()
        for i, face in enumerate(faces):
            bbox = face.bbox.astype(int)
            embedding = face.embedding  # 512 boyutlu vektor
            det_score = face.det_score  # tespit guven skoru

            print(f"    Yuz {i+1}: guven={det_score:.2f}, embedding boyutu={embedding.shape}")

            cv2.rectangle(debug_img, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 255, 0), 2)
            cv2.putText(
                debug_img, f"#{i+1} ({det_score:.2f})",
                (bbox[0], bbox[1] - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2
            )

        out_path = os.path.join(DEBUG_OUTPUT_DIR, f"debug_{filename}")
        cv2.imwrite(out_path, debug_img)
        print(f"    -> Kontrol icin kaydedildi: {out_path}\n")

    print("Tamamlandi. data/debug_output/ klasorundeki fotograflari acip")
    print("yuzlerin dogru tespit edilip edilmedigini goz ile kontrol et.")


if __name__ == "__main__":
    main()
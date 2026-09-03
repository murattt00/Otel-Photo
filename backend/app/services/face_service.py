"""
Yuz tanima servisi: InsightFace modelini sarmalayan tek katman.

Prototipteki (scripts/test_face_detection.py) mantik buraya tasindi:
- Model (buffalo_l) SADECE BIR KEZ yuklenir (lazy singleton), sonraki cagrilarda tekrar kullanilir.
- Bir fotograf yolundan yuzleri tespit eder, kucuk/dusuk-guvenilirlikli yuzleri eler,
  her yuz icin 512 boyutlu embedding + bbox + det_score dondurur.

ONEMLI: insightface/onnxruntime import edilmeden ONCE app.gpu_setup import edilmeli
(CUDA DLL yollarini ayarlar). Bu yuzden en ustte import ediliyor.
"""
from app import gpu_setup  # noqa: F401 -- CUDA DLL yollari (insightface importundan ONCE olmali)

import cv2
import numpy as np
from insightface.app import FaceAnalysis

from app.config import settings

_model = None  # lazy yuklenen singleton


def get_model() -> FaceAnalysis:
    """InsightFace modelini (ilk cagrida) yukler ve onbellekler."""
    global _model
    if _model is None:
        print("[face_service] InsightFace modeli yukleniyor (buffalo_l)...")
        m = FaceAnalysis(
            name="buffalo_l",
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
        m.prepare(ctx_id=0, det_size=(640, 640))
        _model = m
        print("[face_service] Model hazir.")
    return _model


def _imread_unicode(path: str):
    """cv2.imread Windows'ta Turkce/unicode yollarda basarisiz olabilir;
    numpy uzerinden okuyup decode ederek bunu asariz."""
    data = np.fromfile(path, dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


class DetectedFace:
    """Tespit edilen tek bir yuz. embedding: np.float32 (512,)."""

    def __init__(self, embedding: np.ndarray, det_score: float, bbox: dict):
        self.embedding = embedding
        self.det_score = det_score
        self.bbox = bbox  # {"x1":.., "y1":.., "x2":.., "y2":..}


def _detect_on_image(img, apply_filter: bool = True) -> list[DetectedFace]:
    """Bir OpenCV goruntusu (numpy BGR) uzerinde yuz tespiti yapar.

    apply_filter=True iken prototipteki kucuk/dusuk-guvenilirlik filtresi uygulanir
    (yukleme icin). Kioskta ise musteri kameraya tek yuz tuttugu icin filtreyi
    gevsetiyoruz (apply_filter=False), sadece det_score esigi kalir.
    """
    model = get_model()
    faces = model.get(img)
    img_width = img.shape[1]

    result: list[DetectedFace] = []
    for face in faces:
        x1, y1, x2, y2 = [float(v) for v in face.bbox]
        width_ratio = (x2 - x1) / img_width

        if face.det_score < settings.MIN_DET_SCORE:
            continue
        if apply_filter and width_ratio < settings.MIN_FACE_WIDTH_RATIO:
            continue

        result.append(
            DetectedFace(
                embedding=face.embedding.astype(np.float32),
                det_score=float(face.det_score),
                bbox={"x1": x1, "y1": y1, "x2": x2, "y2": y2},
            )
        )
    return result


def detect_faces(image_path: str) -> list[DetectedFace]:
    """Bir dosya yolundaki fotograftan (filtreli) yuzleri tespit eder. Yukleme icin."""
    img = _imread_unicode(image_path)
    if img is None:
        return []
    return _detect_on_image(img, apply_filter=True)


def detect_faces_bytes(data: bytes, apply_filter: bool = False) -> list[DetectedFace]:
    """Ham bayt ( or. webcam yakalamasi) icinden yuz tespiti. Kiosk taramasi icin."""
    arr = np.frombuffer(data, dtype=np.uint8)
    if arr.size == 0:
        return []
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return []
    return _detect_on_image(img, apply_filter=apply_filter)

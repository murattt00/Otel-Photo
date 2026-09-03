"""
gpu_setup modulunun dogru calistigini dogrulayan test scripti.
Calistirma: python test_cuda_v2.py  (backend/ klasorunden)
"""
from app import gpu_setup  # noqa: F401 -- import edilince DLL yollari otomatik ayarlanir

import onnxruntime

providers = onnxruntime.get_available_providers()
print("Kullanilabilir providerlar:", providers)

if "CUDAExecutionProvider" in providers:
    print("GPU (CUDA) hazir, InsightFace GPU ile calisacak.")
else:
    print("UYARI: CUDA bulunamadi, CPU ile calisacak.")
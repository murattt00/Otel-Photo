"""
Bu modul, onnxruntime-gpu'nun CUDA/cuDNN DLL'lerini bulabilmesi icin
gerekli klasor yollarini Windows DLL arama yoluna ekler.

Projedeki her yerde onnxruntime veya insightface import etmeden ONCE
bu modulu import etmek yeterli:

    import app.gpu_setup  # noqa: F401 (sadece yan etkisi icin import ediliyor)
    import onnxruntime
    ...
"""
import os
import sys


def setup_cuda_dll_paths(verbose: bool = True) -> bool:
    """
    nvidia-cudnn-cu12, nvidia-cublas-cu12, nvidia-cuda-runtime-cu12
    paketlerinin bin klasorlerini DLL arama yoluna ekler.
    Hem os.add_dll_directory hem de PATH ortam degiskenini kullanir
    (bazi Windows/onnxruntime kombinasyonlarinda sadece add_dll_directory
    bagimli DLL'leri (cublasLt gibi) bulmakta yetersiz kalabiliyor).

    Returns:
        True: en az bir DLL klasoru basariyla eklendiyse
        False: hicbir paket bulunamadiysa (CPU'ya duser)
    """
    if sys.platform != "win32":
        return True

    added_any = False
    added_paths = []
    packages = [
        "nvidia.cudnn", "nvidia.cublas", "nvidia.cuda_runtime", "nvidia.cuda_nvrtc",
        "nvidia.cufft", "nvidia.curand", "nvidia.cusparse", "nvidia.cusolver",
    ]

    for pkg_name in packages:
        try:
            module = __import__(pkg_name, fromlist=["__path__"])
            pkg_path = list(module.__path__)[0]
            bin_path = os.path.join(pkg_path, "bin")
            if os.path.isdir(bin_path):
                os.add_dll_directory(bin_path)
                added_paths.append(bin_path)
                added_any = True
        except (ImportError, ModuleNotFoundError, IndexError):
            continue

    if added_paths:
        # PATH'e de ekleyelim, daha eski/genel DLL arama mekanizmasi icin
        current_path = os.environ.get("PATH", "")
        os.environ["PATH"] = os.pathsep.join(added_paths) + os.pathsep + current_path

    if verbose:
        if added_paths:
            print("[gpu_setup] Eklenen DLL klasorleri:")
            for p in added_paths:
                print(f"    {p}")
        else:
            print("[gpu_setup] UYARI: Hicbir CUDA DLL klasoru bulunamadi, CPU kullanilacak.")

    return added_any


_gpu_ready = setup_cuda_dll_paths()
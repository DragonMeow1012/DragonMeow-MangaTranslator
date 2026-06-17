"""GPU/CPU 自動分流安裝。

setup.bat 在 `pip install -r requirements.txt`（已裝 CPU 版 torch/paddlepaddle）之後呼叫本檔，
用 .venv 的 python 執行。流程：
  有 NVIDIA GPU → 升級成 torch 2.7 cu126 + paddlepaddle-gpu + nvidia-cudnn 9.23（並把 cudnn DLL
                  覆蓋到 torch/lib，讓 torch 與 paddle 共用同一份 cudnn，避免 9.x 版本不相容當機），
                  驗證；失敗（GPU 太舊 / driver 不支援 cu126）→ 回退 CPU 版。
  無 NVIDIA GPU → 不動（requirements.txt 已裝好 CPU 版）。

實測可共存組合（2026-06，RTX 4080 / driver CUDA 13.2）：torch 2.7.0+cu126（自帶 cudnn 9.7）、
paddlepaddle-gpu 3.3.1（cu126，編譯對 cudnn 9.9）、nvidia-cudnn-cu12 9.23.1.3 覆蓋兩邊 → 兩者都
跑 cudnn 9.23（皆向後相容）、無警告、torch-first import。
"""
import glob
import os
import shutil
import subprocess
import sys

PY = sys.executable
TORCH_CU126 = "https://download.pytorch.org/whl/cu126"
PADDLE_CU126 = "https://www.paddlepaddle.org.cn/packages/stable/cu126/"
CUDNN_PIN = "nvidia-cudnn-cu12==9.23.1.3"


def pip(*args):
    return subprocess.call([PY, "-m", "pip", *args])


def has_nvidia_gpu():
    try:
        r = subprocess.run(["nvidia-smi"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=25)
        return r.returncode == 0
    except Exception:
        return False


def _site_packages():
    import importlib.util
    spec = importlib.util.find_spec("torch")
    # .../site-packages/torch/__init__.py → .../site-packages（兩層 dirname）
    return os.path.dirname(os.path.dirname(spec.origin))


def overlay_cudnn():
    """把 nvidia wheel 的 cudnn DLL 覆蓋到 torch/lib，兩邊共用同一份 cudnn。"""
    site = _site_packages()
    src = os.path.join(site, "nvidia", "cudnn", "bin")
    dst = os.path.join(site, "torch", "lib")
    if not os.path.isdir(src) or not os.path.isdir(dst):
        print(f"[setup-gpu] 找不到 cudnn 來源/目標：{src} → {dst}")
        return False
    n = 0
    for f in glob.glob(os.path.join(src, "cudnn*.dll")):
        shutil.copy2(f, dst)
        n += 1
    print(f"[setup-gpu] 覆蓋 cudnn DLL → torch/lib（{n} 個）")
    return n > 0


def _clean_overlaid_cudnn():
    """移除先前 GPU 嘗試 overlay 到 torch/lib 的 cudnn DLL（回退 CPU 時呼叫）。

    overlay_cudnn() 是用 shutil.copy2 手動把 cudnn DLL 複製進 torch/lib，這些檔案
    不在 pip 的 RECORD 裡，故 `pip uninstall nvidia-cudnn-cu12` 不會移除它們。
    若殘留，CPU 版 torch（不含 cudnn）在 import 時的 _load_dll_libraries() 仍會去
    載入這些 GPU cudnn DLL；在缺 VC++ 執行階段 / 版本不符的機器上以 [WinError 126]
    整個 import torch 失敗（連 CPU 模式都起不來）。
    """
    try:
        dst = os.path.join(_site_packages(), "torch", "lib")
    except Exception:
        return
    n = 0
    for f in glob.glob(os.path.join(dst, "cudnn*.dll")):
        try:
            os.remove(f)
            n += 1
        except OSError:
            pass
    if n:
        print(f"[setup-gpu] 清除殘留的 GPU cudnn DLL（{n} 個）→ CPU 版 torch 可正常 import")


def verify_gpu():
    code = (
        "import torch, paddle;"
        "assert torch.cuda.is_available(), 'torch no cuda';"
        "assert paddle.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0, 'paddle no cuda';"
        "import torch.nn.functional as F;"
        "x=torch.randn(1,3,16,16,device='cuda');F.conv2d(x,torch.randn(4,3,3,3,device='cuda'));"
        "torch.cuda.synchronize();print('verify ok')"
    )
    return subprocess.call([PY, "-c", code]) == 0


def install_gpu():
    print("[setup-gpu] 偵測到 NVIDIA GPU → 安裝 GPU 版 torch cu126 + paddlepaddle-gpu + cudnn 9.23 ...")
    if pip("install", "torch==2.7.0", "torchvision==0.22.0", "--index-url", TORCH_CU126):
        return False
    pip("uninstall", "-y", "paddlepaddle")
    if pip("install", "paddlepaddle-gpu==3.3.1", "-i", PADDLE_CU126):
        return False
    pip("install", "--no-deps", "--force-reinstall", CUDNN_PIN)
    if not overlay_cudnn():
        return False
    return verify_gpu()


def install_cpu():
    print("[setup-gpu] 安裝 / 回退 CPU 版 torch + paddlepaddle ...")
    pip("install", "torch==2.6.0", "torchvision==0.21.0")
    pip("uninstall", "-y", "paddlepaddle-gpu", "nvidia-cudnn-cu12")
    pip("install", "paddlepaddle==3.3.1")
    _clean_overlaid_cudnn()


def main():
    if not has_nvidia_gpu():
        print("[setup-gpu] 未偵測到 NVIDIA GPU → 使用 CPU 版（requirements.txt 已安裝，manga-ocr/PaddleOCR 走 CPU）。")
        return
    if install_gpu():
        print("[setup-gpu] ✅ GPU 版就緒：日漫 manga-ocr 與韓漫 PaddleOCR 皆走 GPU。")
    else:
        print("[setup-gpu] ⚠ GPU 版安裝或驗證失敗（GPU 太舊 / driver 不支援 cu126）→ 回退 CPU 版。")
        install_cpu()
        print("[setup-gpu] ✅ 已回退 CPU 版。")


if __name__ == "__main__":
    main()

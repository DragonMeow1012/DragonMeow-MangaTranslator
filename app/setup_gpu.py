"""GPU/CPU 自動分流安裝。

setup.bat 在 `pip install -r requirements.txt`（已裝 CPU 版 torch/paddlepaddle）之後呼叫本檔，
用 .venv 的 python 執行。流程：
  有 NVIDIA GPU → 升級成 torch 2.7 cu126 + paddlepaddle-gpu + nvidia-cudnn 9.23（並把 cudnn DLL
                  覆蓋到 torch/lib，讓 torch 與 paddle 共用同一份 cudnn，避免 9.x 版本不相容當機），
                  驗證；失敗（驅動太舊）→ 提示更新驅動並回退 CPU 版。
  Blackwell（RTX 50 系列，sm_120）→ torch cu128（唯一含 sm_120 的 torch build）走 GPU；PaddleOCR 固定 CPU。
                  paddle 的 sm_120 只有 cu129 wheel，與 torch cu128 各自 bundle 一份「同名不同版」的 CUDA runtime
                  （cudart64_12.dll / cublas64_12.dll，12.8 vs 12.9）。同 process 先載 torch(12.8)，paddle 的
                  cu129 cublas 在已載入的 12.8 cudart 裡找不到進入點 → [WinError 127] → paddle 半初始化 →
                  「circular import」（實機 RTX 5070 Ti 重現）。torch 只有 cu128、paddle 只有 cu129，湊不出相同
                  CUDA minor 的配對，故單一 process 無法同時 GPU → paddle 退 CPU、且略過 cudnn overlay。
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
TORCH_CU128 = "https://download.pytorch.org/whl/cu128"        # Blackwell（sm_120）需要
PADDLE_CU126 = "https://www.paddlepaddle.org.cn/packages/stable/cu126/"
# Blackwell 的 paddle GPU wheel（sm_120 在 cu129）。目前不裝（見 install_gpu：與 torch cu128 同 process 會
# DLL 互撞）；保留供未來「把 paddle 放獨立 process / 服務」時用得到。
PADDLE_CU129 = "https://www.paddlepaddle.org.cn/packages/stable/cu129/"
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


def _max_compute_cap():
    """偵測到的最高 GPU compute capability（float）；失敗回 0.0。
    cu126 只 build 到 sm_90（9.0）；Blackwell（RTX 50=sm_120=12.0、B100=sm_100=10.0）超過 → 需 cu128。"""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=compute_cap", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=25)
        caps = []
        for tok in r.stdout.split():
            try:
                caps.append(float(tok))
            except ValueError:
                pass
        return max(caps) if caps else 0.0
    except Exception:
        return 0.0


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


def _verify_torch_cuda():
    """torch GPU 真驗：實跑一次 cuda conv2d（會抓到 sm 不符 / driver 不支援）。"""
    code = (
        "import torch;"
        "assert torch.cuda.is_available(), 'torch no cuda';"
        "import torch.nn.functional as F;"
        "x=torch.randn(1,3,16,16,device='cuda');F.conv2d(x,torch.randn(4,3,3,3,device='cuda'));"
        "torch.cuda.synchronize();print('torch cuda ok')"
    )
    return subprocess.call([PY, "-c", code]) == 0


def _verify_paddle_cuda():
    """paddle GPU 真驗：實跑一次 gpu conv2d（Blackwell 上沒 sm_120 kernel 會在此失敗）。"""
    code = (
        "import paddle;"
        "assert paddle.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0, 'paddle no cuda';"
        "paddle.set_device('gpu');"
        "import paddle.nn.functional as F;"
        "F.conv2d(paddle.randn([1,3,16,16]), paddle.randn([4,3,3,3]));"
        "paddle.device.cuda.synchronize();print('paddle cuda ok')"
    )
    return subprocess.call([PY, "-c", code]) == 0


def install_gpu():
    cap = _max_compute_cap()
    blackwell = cap >= 10.0  # cu126 最高 sm_90；sm_100 / sm_120 需 cu128

    # Blackwell（RTX 50 / sm_120）：torch 走 cu128（唯一含 sm_120 的 torch build），PaddleOCR 固定 CPU。
    # 不裝 cu129 paddle-gpu —— paddle cu129 與 torch cu128 各自 bundle 同名不同版的 CUDA DLL
    # （cudart64_12 / cublas64_12，12.8 vs 12.9），同一 process 先載 torch(12.8) 後，paddle 的 cu129
    # cublas 找不到 12.9 進入點 → [WinError 127] → paddle 半初始化 → circular import（RTX 5070 Ti 實機重現）。
    # torch 只有 cu128、paddle 只有 cu129，湊不出相同 CUDA minor 配對 → 單一 process 無法同時 GPU。
    # 取捨：torch（偵測/抹字/manga-ocr，主要計算）保 GPU；paddle 退 CPU（韓漫仍可用，日文本就建議 manga-ocr）。
    # 也略過 cudnn overlay：它唯一目的是讓 torch/paddle 共用 cudnn，paddle 走 CPU 後此需求消失，
    # 而 9.23 overlay 蓋掉 torch cu128 自帶 cudnn 在 sm_120 上未驗證、徒增風險。
    if blackwell:
        print(f"[setup-gpu] 偵測到 Blackwell / RTX 50（compute capability {cap}）→ torch cu128(GPU) + "
              "PaddleOCR 強制 CPU（paddle cu129 與 torch cu128 的 CUDA DLL 會 WinError 127 互撞）...")
        if pip("install", "torch==2.7.0", "torchvision==0.22.0", "--index-url", TORCH_CU128):
            return False
        # 兩個套件都卸再實裝：requirements 先裝 CPU paddlepaddle、舊輪又裝過 paddle-gpu 蓋在同一個
        # paddle/ 目錄；只卸 gpu 版會按它的 RECORD 連 CPU 的 paddle/ 檔一起刪，但 CPU metadata 還在 →
        # 下面 install 判「已安裝」不補檔 → No module named 'paddle'（RTX 5070 Ti 實機踩到）。
        # 全卸清掉 metadata，後面才會真的重裝、把 paddle/ 檔補回來。
        pip("uninstall", "-y", "paddlepaddle", "paddlepaddle-gpu")
        pip("install", "paddlepaddle==3.3.1")
        if not _verify_torch_cuda():
            return False
        print("[setup-gpu] ✅ Blackwell：torch 走 GPU(cu128)、PaddleOCR 走 CPU。")
        return True

    # 非 Blackwell（sm_89 及以下）：torch cu126 + paddlepaddle-gpu cu126 + cudnn 9.23 overlay。
    # 同一 CUDA minor 12.6、torch-first import，不會踩上面 Blackwell 那種跨版 DLL 互撞（檔頭有實測組合）。
    print("[setup-gpu] 偵測到 NVIDIA GPU → 安裝 GPU 版 torch cu126 + paddlepaddle-gpu + cudnn 9.23 ...")

    # 1) torch（主要計算，必須成功）
    if pip("install", "torch==2.7.0", "torchvision==0.22.0", "--index-url", TORCH_CU126):
        return False

    # 2) paddle-gpu（OCR；先裝，失敗稍後單獨退 CPU）
    pip("uninstall", "-y", "paddlepaddle", "paddlepaddle-gpu")
    paddle_gpu_ok = pip("install", "paddlepaddle-gpu==3.3.1", "-i", PADDLE_CU126) == 0

    # 3) cudnn 9.23 覆蓋 torch/lib，讓 torch 與 paddle 共用（在兩者安裝後才 force）
    pip("install", "--no-deps", "--force-reinstall", CUDNN_PIN)
    if not overlay_cudnn():
        return False

    # 4) torch GPU 必須通過；不過 → 整體回退 CPU（交給 main()）
    if not _verify_torch_cuda():
        return False

    # 5) paddle GPU 為加分項：裝失敗或驗證失敗 → 單獨退 paddle CPU，torch 仍 GPU
    if not paddle_gpu_ok or not _verify_paddle_cuda():
        print("[setup-gpu] ⚠ paddle GPU 不可用（裝不起來 / sm 不符）→ paddle 改用 CPU；torch 仍走 GPU。")
        pip("uninstall", "-y", "paddlepaddle", "paddlepaddle-gpu")  # 兩個都卸再實裝（理由同 Blackwell 分支：避免殘留 CPU metadata 擋住補檔）
        pip("install", "paddlepaddle==3.3.1")
    return True


def install_cpu():
    print("[setup-gpu] 安裝 / 回退 CPU 版 torch + paddlepaddle ...")
    pip("install", "torch==2.6.0", "torchvision==0.21.0")
    # 連 CPU paddlepaddle 一起卸（不只 gpu 版）：避免殘留 metadata 讓重裝判「已安裝」而不補回 paddle/ 檔。
    pip("uninstall", "-y", "paddlepaddle", "paddlepaddle-gpu", "nvidia-cudnn-cu12")
    pip("install", "paddlepaddle==3.3.1")
    _clean_overlaid_cudnn()


def main():
    if not has_nvidia_gpu():
        print("[setup-gpu] 未偵測到 NVIDIA GPU → 使用 CPU 版（requirements.txt 已安裝，manga-ocr/PaddleOCR 走 CPU）。")
        return
    if install_gpu():
        print("[setup-gpu] ✅ GPU 版就緒（torch 走 GPU；PaddleOCR 依上方訊息為 GPU 或已退 CPU）。")
    else:
        print("[setup-gpu] ⚠ GPU 版安裝或驗證失敗 → 回退 CPU 版。")
        print("[setup-gpu]    若你確實有 NVIDIA 顯卡，最可能是『驅動太舊』：")
        print("[setup-gpu]    請更新 NVIDIA 驅動到支援 CUDA 12 的版本（Windows 約 527 以上，建議更新到最新），再重跑 setup.bat。")
        install_cpu()
        print("[setup-gpu] ✅ 已回退 CPU 版。")


if __name__ == "__main__":
    main()

import numpy as np
from typing import List, Optional
from .common import CommonOCR, OfflineOCR
from .model_manga_ocr import ModelMangaOCR
from ..config import Ocr, OcrConfig
from ..utils import Quadrilateral

# 只保留 mocr (manga-ocr)。Model48pxOCR 是 ModelMangaOCR 內部依賴。
OCRS = {
    Ocr.mocr: ModelMangaOCR,
}
# PaddleOCR（韓/中/英/日多語；模型由 paddleocr 自動下載快取）。模組對 paddleocr 採延遲匯入，
# 故此處註冊不需 paddle 已安裝；未安裝時會在實際使用（_infer）才拋出清楚的匯入錯誤。
try:
    from .model_paddle_ocr import ModelPaddleOCR
    OCRS[Ocr.paddle] = ModelPaddleOCR
except Exception:
    pass
ocr_cache = {}


def get_ocr(key: Ocr, device: str = 'cpu') -> CommonOCR:
    if key not in OCRS:
        raise ValueError(
            f'Could not find OCR for: "{key}". '
            f'Choose from: {",".join(o.value for o in OCRS)}'
        )
    # 以 (模型, device) 為鍵：同一 OCR 的 CPU / GPU 各自獨立實例，可並存
    # （讓使用者在 UI 自由切「manga-ocr/PaddleOCR × CPU/GPU」，按需各自載入）。
    ck = (key, device)
    if not ocr_cache.get(ck):
        ocr_cache[ck] = OCRS[key]()
    return ocr_cache[ck]


async def prepare(ocr_key: Ocr, device: str = 'cpu'):
    ocr = get_ocr(ocr_key, device)
    if isinstance(ocr, OfflineOCR):
        await ocr.download()
        await ocr.load(device)


async def dispatch(
    ocr_key: Ocr, image: np.ndarray, regions: List[Quadrilateral],
    config: Optional[OcrConfig] = None, device: str = 'cpu', verbose: bool = False,
) -> List[Quadrilateral]:
    ocr = get_ocr(ocr_key, device)
    if isinstance(ocr, OfflineOCR):
        await ocr.load(device)
    config = config or OcrConfig()
    return await ocr.recognize(image, regions, config, verbose)


async def unload(ocr_key: Ocr):
    # 移除該 OCR 的所有裝置實例（cpu / gpu）
    for ck in [k for k in ocr_cache if k[0] == ocr_key]:
        ocr_cache.pop(ck, None)

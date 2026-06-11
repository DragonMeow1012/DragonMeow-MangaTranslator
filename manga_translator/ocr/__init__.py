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
ocr_cache = {}


def get_ocr(key: Ocr, *args, **kwargs) -> CommonOCR:
    if key not in OCRS:
        raise ValueError(
            f'Could not find OCR for: "{key}". '
            f'Choose from: {",".join(o.value for o in OCRS)}'
        )
    if not ocr_cache.get(key):
        ocr = OCRS[key]
        ocr_cache[key] = ocr(*args, **kwargs)
    return ocr_cache[key]


async def prepare(ocr_key: Ocr, device: str = 'cpu'):
    ocr = get_ocr(ocr_key)
    if isinstance(ocr, OfflineOCR):
        await ocr.download()
        await ocr.load(device)


async def dispatch(
    ocr_key: Ocr, image: np.ndarray, regions: List[Quadrilateral],
    config: Optional[OcrConfig] = None, device: str = 'cpu', verbose: bool = False,
) -> List[Quadrilateral]:
    ocr = get_ocr(ocr_key)
    if isinstance(ocr, OfflineOCR):
        await ocr.load(device)
    config = config or OcrConfig()
    return await ocr.recognize(image, regions, config, verbose)


async def unload(ocr_key: Ocr):
    ocr_cache.pop(ocr_key, None)

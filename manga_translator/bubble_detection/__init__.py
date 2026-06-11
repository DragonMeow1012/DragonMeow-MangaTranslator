"""
漫畫對話框偵測（YOLOv8）。

補 DBNet 不分氣泡的問題：DBNet 對相鄰氣泡的字常會被 textline_merge 誤合到同一個 region，
靠這個給 textline_merge 一個「氣泡邊界」當硬 cutoff——同氣泡內 textline 才能合併。

參考 Saber-Translator 的 saber_yolo refinement 思路；用 ogkalu/comic-speech-bubble-detector-yolov8m
（YOLOv8m, 8000 張漫畫訓練）公開權重，第一次用會留在 models/bubble_detector/。
"""
import os
import threading
from typing import List, Tuple

import numpy as np

from ..utils import get_logger

logger = get_logger('bubble_detection')

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_MODEL = os.path.join(_REPO_ROOT, 'models', 'bubble_detector', 'comic-speech-bubble-detector.pt')
_MODEL_PATH = os.environ.get('BUBBLE_DETECTOR_MODEL', _DEFAULT_MODEL)
_CONF_THRESH = float(os.environ.get('BUBBLE_DETECTOR_CONF', '0.15'))
_IOU_THRESH = float(os.environ.get('BUBBLE_DETECTOR_IOU', '0.5'))

_model = None
_load_failed = False
_load_lock = threading.Lock()


def _load_model():
    global _model, _load_failed
    if _model is not None or _load_failed:
        return _model
    with _load_lock:
        if _model is not None or _load_failed:
            return _model
        if not os.path.isfile(_MODEL_PATH):
            logger.warning(f'Bubble detector model not found at {_MODEL_PATH}; bubble-aware merge disabled')
            _load_failed = True
            return None
        try:
            from ultralytics import YOLO
            _model = YOLO(_MODEL_PATH)
            logger.info(f'Loaded bubble detector: {_MODEL_PATH}')
        except Exception as e:
            logger.warning(f'Failed to load bubble detector: {type(e).__name__}: {e}')
            _load_failed = True
            return None
    return _model


def detect_bubbles(img_rgb: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """回 [(x1, y1, x2, y2), ...]，依面積大到小排序。模型載入失敗或推理錯誤回 []。"""
    model = _load_model()
    if model is None:
        return []
    try:
        import cv2
        img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
        results = model.predict(img_bgr, conf=_CONF_THRESH, iou=_IOU_THRESH, verbose=False)
        boxes: List[Tuple[int, int, int, int]] = []
        for r in results:
            if r.boxes is None:
                continue
            for box in r.boxes.xyxy.cpu().numpy():
                x1, y1, x2, y2 = [int(v) for v in box]
                boxes.append((x1, y1, x2, y2))
        boxes.sort(key=lambda b: -((b[2] - b[0]) * (b[3] - b[1])))
        return boxes
    except Exception as e:
        logger.warning(f'Bubble detection failed: {type(e).__name__}: {e}')
        return []


def assign_textlines_to_bubbles(textlines, bubbles: List[Tuple[int, int, int, int]]) -> List[int]:
    """
    每個 textline 找重疊面積最大的 bubble；無重疊回 -1（旁白/框外字）。
    為了讓「中文標題框/小註解」不被誤判進大氣泡，要求至少 textline 60% 面積在該 bubble 內。
    """
    owners: List[int] = []
    for tl in textlines:
        try:
            aabb = tl.aabb
            x1, y1 = aabb.x, aabb.y
            x2, y2 = x1 + aabb.w, y1 + aabb.h
            tl_area = max(1, (x2 - x1) * (y2 - y1))
        except Exception:
            owners.append(-1)
            continue
        best_owner = -1
        best_overlap_ratio = 0.0
        for i, (bx1, by1, bx2, by2) in enumerate(bubbles):
            ix1, iy1 = max(x1, bx1), max(y1, by1)
            ix2, iy2 = min(x2, bx2), min(y2, by2)
            if ix2 <= ix1 or iy2 <= iy1:
                continue
            overlap = (ix2 - ix1) * (iy2 - iy1)
            ratio = overlap / tl_area
            if ratio > best_overlap_ratio:
                best_overlap_ratio = ratio
                best_owner = i
        # 至少 60% 面積在某個 bubble 內才算 owner，避免邊界 textline 被誤指
        owners.append(best_owner if best_overlap_ratio >= 0.6 else -1)
    return owners

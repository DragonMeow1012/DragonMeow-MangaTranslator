import os
from typing import List

import numpy as np

from .common import OfflineOCR
from ..config import OcrConfig
from ..utils import Quadrilateral


class ModelPaddleOCR(OfflineOCR):
    """
    PaddleOCR 後端 —— 主供韓漫（韓文 korean_PP-OCRv5）使用，也讀拉丁字母/數字。

    模型由 PaddleOCR 自行下載並快取於 ~/.paddlex/official_models，不走本框架的
    _MODEL_MAPPING（故留空）。已知 paddlepaddle CPU 在 oneDNN 下推論會炸
    （ConvertPirAttribute2RuntimeAttribute），因此固定 enable_mkldnn=False。
    """
    _MODEL_MAPPING = {}

    def __init__(self, *args, **kwargs):
        os.makedirs(self.model_dir, exist_ok=True)
        super().__init__(*args, **kwargs)
        self._engine = None
        self._engine_lang = None
        self.device = 'cpu'

    async def _load(self, device: str):
        # 實際建構延後到首次 _infer（依語言），這裡只記裝置。
        self.device = device

    async def _unload(self):
        self._engine = None
        self._engine_lang = None

    def _get_engine(self, lang: str):
        if self._engine is not None and self._engine_lang == lang:
            return self._engine
        os.environ.setdefault('FLAGS_use_mkldnn', '0')
        from paddleocr import PaddleOCR
        use_gpu = self.device in ('cuda', 'gpu')
        self._engine = PaddleOCR(
            lang=lang,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            enable_mkldnn=False,            # 規避 paddlepaddle CPU oneDNN bug
            device='gpu' if use_gpu else 'cpu',
        )
        self._engine_lang = lang
        self.logger.info(f'PaddleOCR engine ready (lang={lang}, device={self.device})')
        return self._engine

    def _recognize_crop(self, crop: np.ndarray, prob_threshold: float):
        try:
            res = self._engine.predict(crop)
        except Exception as e:
            self.logger.warning(f'PaddleOCR predict failed: {e}')
            return '', 0.0
        if not res:
            return '', 0.0
        r0 = res[0]
        data = r0.json.get('res', r0.json) if hasattr(r0, 'json') else (r0 if isinstance(r0, dict) else {})
        rec_texts = data.get('rec_texts', []) or []
        rec_scores = data.get('rec_scores', []) or []
        parts, scores = [], []
        for t, s in zip(rec_texts, rec_scores):
            s = float(s)
            if s >= prob_threshold and str(t).strip():
                parts.append(str(t))
                scores.append(s)
        if not parts:
            return '', 0.0
        return ''.join(parts), sum(scores) / len(scores)

    async def _infer(self, image: np.ndarray, textlines: List[Quadrilateral], config: OcrConfig,
                     verbose: bool = False, ignore_bubble: int = 0) -> List[Quadrilateral]:
        if len(textlines) == 0:
            return textlines

        prob_threshold = config.prob if config.prob is not None else 0.2
        # 韓漫主用；中/日/英之後可加「來源語言」選項切換 lang。
        lang = getattr(config, 'paddle_lang', None) or 'korean'
        self._get_engine(lang)

        quadrilaterals = list(self._generate_text_direction(textlines))
        if not quadrilaterals:
            return textlines
        is_quadrilaterals = isinstance(quadrilaterals[0][0], Quadrilateral)

        text_height = 48
        output_regions = []
        for q, d in quadrilaterals:
            crop = q.get_transformed_region(image, d, text_height)
            txt, prob = self._recognize_crop(crop, prob_threshold)
            if config.min_text_length and len(txt) < config.min_text_length:
                txt, prob = '', 0.0
            if verbose:
                self.logger.info(f'paddle prob:{prob:.3f} text:{txt}')
            cur = q
            if isinstance(cur, Quadrilateral):
                cur.text = txt
                cur.prob = prob
                cur.fg_r = cur.fg_g = cur.fg_b = 0
                cur.bg_r = cur.bg_g = cur.bg_b = 255
            else:  # TextBlock
                cur.text.append(txt)
                cur.update_font_colors(np.array([0, 0, 0]), np.array([255, 255, 255]))
            output_regions.append(cur)

        if is_quadrilaterals:
            return output_regions
        return textlines

import os

# paddlepaddle CPU 在 oneDNN 下推論會炸（ConvertPirAttribute2RuntimeAttribute），且 FLAGS 必須
# 在 import paddle 前就設好。本模組於 OCR 註冊時（伺服器啟動、paddle 尚未匯入）載入，故在此設
# 最保險；start.bat / start.sh 也會在 process 啟動時各設一道（雙保險）。
os.environ.setdefault("FLAGS_use_mkldnn", "0")

import asyncio
from typing import List

import numpy as np

from .common import OfflineOCR
from ..config import OcrConfig
from ..utils import Quadrilateral


class ModelPaddleOCR(OfflineOCR):
    """
    PaddleOCR 後端 —— 中/日/英/韓多語。預設 paddle_lang='auto' 會自動偵測語言
    （取最大文字區域用各語言模型探測、選信心最高者），也可指定 korean/ch/japan/en。

    模型由 PaddleOCR 自行下載並快取於 ~/.paddlex/official_models。已知 paddlepaddle CPU
    在 oneDNN 下推論會炸（ConvertPirAttribute2RuntimeAttribute），故固定 enable_mkldnn=False。
    """
    _MODEL_MAPPING = {}

    # 自動偵測候選（拉丁字母在這幾個模型都讀得到，故不另列 en）
    _DETECT_LANGS = ('korean', 'ch', 'japan')

    def __init__(self, *args, **kwargs):
        os.makedirs(self.model_dir, exist_ok=True)
        super().__init__(*args, **kwargs)
        self._engines = {}        # lang -> PaddleOCR（多語各快取一份）
        self.device = 'cpu'

    async def _load(self, device: str):
        # 實際建構延後到首次 _infer（依語言），這裡只記裝置。
        self.device = device

    async def _unload(self):
        self._engines = {}

    def _get_engine(self, lang: str):
        if lang in self._engines:
            return self._engines[lang]
        os.environ['FLAGS_use_mkldnn'] = '0'
        import paddle
        try:
            # import 後再硬關一次 oneDNN（不依賴環境變數時機）。
            paddle.set_flags({'FLAGS_use_mkldnn': False})
        except Exception:
            pass
        # GPU build（paddlepaddle-gpu）→ 用 GPU 加速；CPU build → 固定 CPU。
        # 注意：傳 'gpu' 給 CPU build 會走「嘗試 GPU 失敗 → 退回 CPU」路徑，那條不吃
        # FLAGS_use_mkldnn → 仍啟用 oneDNN → 踩 ConvertPirAttribute bug；故只在真 GPU build 才傳 gpu。
        # self.device 由 _load(device) 設定；使用者在 UI 選「PaddleOCR CPU」→ 即使有 GPU 也跑 CPU。
        want_gpu = str(getattr(self, 'device', 'cpu')) in ('cuda', 'gpu', 'mps')
        try:
            use_gpu = want_gpu and bool(paddle.is_compiled_with_cuda()) and paddle.device.cuda.device_count() > 0
        except Exception:
            use_gpu = False
        device = 'gpu' if use_gpu else 'cpu'
        from paddleocr import PaddleOCR
        self._engines[lang] = PaddleOCR(
            lang=lang,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            enable_mkldnn=False,
            device=device,
        )
        self.logger.info(f'PaddleOCR engine ready (lang={lang}, device={device})')
        return self._engines[lang]

    def _detect_lang(self, image: np.ndarray, quadrilaterals) -> str:
        """取最大文字區域當探針，各語言模型各跑一次，選平均信心最高者。"""
        if not quadrilaterals:
            return 'korean'

        def _area(qd):
            ab = getattr(qd[0], 'aabb', None)
            return (ab.w * ab.h) if ab is not None else 0

        q, d = max(quadrilaterals, key=_area)
        crop = q.get_transformed_region(image, d, 48)
        best, best_conf = 'korean', -1.0
        for lang in self._DETECT_LANGS:
            try:
                res = self._get_engine(lang).predict(crop)
                data = res[0].json.get('res', res[0].json)
                texts = data.get('rec_texts', []) or []
                scores = data.get('rec_scores', []) or []
                conf = (sum(scores) / len(scores)) if (scores and any(str(t).strip() for t in texts)) else 0.0
                if conf > best_conf:
                    best_conf, best = conf, lang
            except Exception:
                continue
        self.logger.info(f'PaddleOCR auto-detect lang={best} (conf={best_conf:.3f})')
        return best

    def _recognize_crop(self, engine, crop: np.ndarray, prob_threshold: float):
        try:
            res = engine.predict(crop)
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
        lang = getattr(config, 'paddle_lang', None) or 'korean'
        min_text_length = config.min_text_length

        quadrilaterals = list(self._generate_text_direction(textlines))
        if not quadrilaterals:
            return textlines

        # PaddleOCR 的 predict 是同步、CPU 密集；直接在 async 內跑會卡死 worker 唯一的 event loop，
        # 並發模式下其他圖「不持 GPU 鎖的 LLM 階段」也會一起停住 → 韓漫批次的並發等於白做。
        # 丟到 thread 讓 event loop 保持可推進。OCR 全程持 gpu_lock('pre')，同一時間只有一張在
        # OCR → 不會有兩個 thread 同時對同一 engine predict，故共用 engine 仍 thread-safe。
        return await asyncio.to_thread(
            self._infer_sync, image, quadrilaterals, lang, prob_threshold,
            min_text_length, verbose, textlines)

    def _infer_sync(self, image, quadrilaterals, lang, prob_threshold,
                    min_text_length, verbose, textlines):
        if lang == 'auto':
            lang = self._detect_lang(image, quadrilaterals)
        engine = self._get_engine(lang)
        is_quadrilaterals = isinstance(quadrilaterals[0][0], Quadrilateral)

        text_height = 48
        output_regions = []
        for q, d in quadrilaterals:
            crop = q.get_transformed_region(image, d, text_height)
            txt, prob = self._recognize_crop(engine, crop, prob_threshold)
            if min_text_length and len(txt) < min_text_length:
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

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


# PaddleOCR 信心下限（修「莫名冒出的句子」）：DBNet 偶爾把臉/背景誤判成字框，PaddleOCR 仍會
# 硬讀出一句通順韓文。前端預設 prob=0.08 幾乎不過濾；這裡設較高下限濾掉雜訊。韓文正常字通常
# 0.9+，0.6 不影響正常字；嫌誤砍可用 env PADDLE_OCR_MIN_PROB 調低、要更嚴可調高。
_PADDLE_MIN_PROB = float(os.getenv('PADDLE_OCR_MIN_PROB', '0.6'))


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
        self._auto_lang = None    # 自動偵測語言快取：同批 webtoon 同語言，偵測一次重用，省每頁 3 次探測 predict

    async def _load(self, device: str):
        # 實際建構延後到首次 _infer（依語言），這裡只記裝置。
        self.device = device

    async def _unload(self):
        self._engines = {}
        self._auto_lang = None

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
        return best, best_conf

    @staticmethod
    def _parse_ocr_result(r0):
        """從單一 PaddleOCR 結果物件抽出 (text, mean_conf)；不在這裡過濾信心，門檻交 caller。"""
        if r0 is None:
            return '', 0.0
        data = r0.json.get('res', r0.json) if hasattr(r0, 'json') else (r0 if isinstance(r0, dict) else {})
        rec_texts = data.get('rec_texts', []) or []
        rec_scores = data.get('rec_scores', []) or []
        parts, scores = [], []
        for t, s in zip(rec_texts, rec_scores):
            try:
                s = float(s)
            except (TypeError, ValueError):
                continue
            if str(t).strip():
                parts.append(str(t))
                scores.append(s)
        if not parts:
            return '', 0.0
        return ''.join(parts), sum(scores) / len(scores)

    def _recognize_crop(self, engine, crop: np.ndarray):
        try:
            res = engine.predict(crop)
        except Exception as e:
            self.logger.warning(f'PaddleOCR predict failed: {e}')
            return '', 0.0
        if not res:
            return '', 0.0
        return self._parse_ocr_result(res[0])

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
            # 語言偵測快取（#2 提速）：同批 webtoon 同語言，偵測一次重用，省每頁 3 次探測 predict。
            # 換系列會經 _unload 清掉重偵；想最穩可在 UI 直接選語言（完全略過偵測）。
            if self._auto_lang is not None:
                lang = self._auto_lang
            else:
                lang, _conf = self._detect_lang(image, quadrilaterals)
                # 只鎖定高信心偵測；低信心（例：把韓文誤判成 ch、conf~0.78）不快取，下一頁重偵，
                # 避免整批被一次誤判鎖死整本變亂碼。最穩仍是在 UI 直接手選語言（完全略過偵測）。
                if _conf >= 0.85:
                    self._auto_lang = lang
        engine = self._get_engine(lang)
        is_quadrilaterals = isinstance(quadrilaterals[0][0], Quadrilateral)

        text_height = 48
        crops = [q.get_transformed_region(image, d, text_height) for q, d in quadrilaterals]

        # 批次推論（#1 提速）：一次把所有 crop 丟給 PaddleOCR，省掉「逐框 predict」的固定開銷
        # —— webtoon 一頁多框時最有感（N 次序列 GPU 呼叫 → 1 次）。回傳筆數對不上或丟例外
        # → 退回逐框，正確性不受影響。
        batched = None
        if len(crops) > 1:
            try:
                res = engine.predict(crops)
                batched = list(res) if res is not None else None
                if batched is not None and len(batched) != len(crops):
                    self.logger.warning(
                        f'PaddleOCR batch 回 {len(batched)} 筆 != {len(crops)} crop，退回逐框')
                    batched = None
            except Exception as e:
                self.logger.warning(
                    f'PaddleOCR batch predict failed ({type(e).__name__}: {e})；退回逐框')
                batched = None

        # 信心門檻：DBNet 偶爾把臉/背景誤判成字框，PaddleOCR 仍硬讀出一句通順韓文（莫名冒出的句子）。
        # 取「前端門檻」與「_PADDLE_MIN_PROB 下限」較大者；低於門檻的讀字清空丟棄，並 log 出來方便核對
        # 有沒有誤砍正常字（若 [paddle drop] 冒出正常台詞 → 用 env PADDLE_OCR_MIN_PROB 調低）。
        eff_prob = max(float(prob_threshold or 0.0), _PADDLE_MIN_PROB)
        output_regions = []
        for idx, (q, d) in enumerate(quadrilaterals):
            if batched is not None:
                r = batched[idx]
                r0 = r[0] if isinstance(r, (list, tuple)) and len(r) else r
                txt, prob = self._parse_ocr_result(r0)
            else:
                txt, prob = self._recognize_crop(engine, crops[idx])
            if txt and prob < eff_prob:
                self.logger.info(f'[paddle drop] conf={prob:.3f} < {eff_prob:.2f} text={txt[:30]!r}')
                txt, prob = '', 0.0
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

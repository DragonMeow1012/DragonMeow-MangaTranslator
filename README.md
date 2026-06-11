# DragonMeow-MangaTranslator

漫畫圖片一鍵翻譯：偵測文字 → OCR → Gemini 翻譯 → 抹字重繪 → 嵌字渲染，內建 localhost 網頁介面，拖放上傳即可翻譯。

基於 [zyddnys/manga-image-translator](https://github.com/zyddnys/manga-image-translator) 精簡改造：

- 翻譯後端只保留 **`gemini_2stage`**（Google Gemini API，單一 vision call 同時做 OCR 仲裁 + 翻譯 + 擬聲詞判斷）
- 內建**氣泡偵測**（YOLOv8），嵌字置中、自動換行、縱書直排
- 翻譯風格針對**繁體中文（台灣用語）**深度調校，也支援簡中 / 英文等目標語言
- Release zip 內附全部模型，**解壓縮 → 裝環境 → 填 API key → 開跑**

---

## 快速開始（Windows，release zip）

1. 下載並解壓 release zip
2. 安裝 [Python 3.10 或 3.11](https://www.python.org/downloads/)（安裝時勾選 *Add to PATH*）
3. 雙擊 `setup.bat`（建立 venv + 裝套件，第一次需要幾分鐘）
4. 打開 `.env`，填入你的 Gemini API key（[免費申請](https://aistudio.google.com/apikey)）：
   ```env
   GEMINI_API_KEY=你的key
   ```
5. 雙擊 `start.bat` — 瀏覽器會自動開 <http://127.0.0.1:8001>，把漫畫頁拖進去就開始翻譯

> **GPU 強烈建議**：文字偵測 / OCR / 抹字模型跑 CPU 會非常慢。裝完 setup.bat 後執行：
> ```
> .venv\Scripts\pip install torch==2.6.0 torchvision==0.21.0 --force-reinstall --index-url https://download.pytorch.org/whl/cu124
> ```

---

## 從 git clone 安裝

```bash
git clone https://github.com/DragonMeow1012/DragonMeow-MangaTranslator.git
cd DragonMeow-MangaTranslator

python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # 填入 GEMINI_API_KEY
```

模型取得：

- 文字偵測 / 48px OCR / LaMa 抹字 / 氣泡偵測權重：**首次執行自動下載**到 `./models/`
- manga-ocr 模型：執行一次
  ```bash
  python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='kha-white/manga-ocr-base')"
  ```
  或手動放到 `models/manga-ocr-base/`（release zip 已內附，免此步驟）

啟動：

```bash
python server/main.py --use-gpu --start-instance --host 127.0.0.1 --port 8001 --nonce None
```

- 網頁介面（拖放上傳、即時進度）：<http://127.0.0.1:8001>
- Swagger API docs：<http://127.0.0.1:8001/docs>

---

## 系統需求

- Python 3.10 / 3.11，Windows / Linux / macOS
- 建議 NVIDIA GPU（6GB+ VRAM）+ CUDA 版 PyTorch
- Gemini API key（[Google AI Studio](https://aistudio.google.com/apikey) 免費申請，免費額度即可用）

---

## 環境變數（`.env`）

| 變數 | 預設 | 說明 |
|------|------|------|
| `GEMINI_API_KEY` | （必填） | Gemini API key；可加 `GEMINI_API_KEY1`、`GEMINI_API_KEY2`... 撞 429 自動輪替 |
| `GEMINI_MODEL` | `gemini-2.5-flash` | 翻譯用模型 |
| `GEMINI_VISION_MODEL` | `gemini-2.5-flash` | OCR 階段用的 vision 模型 |
| `MT_NUM_WORKERS` | `1` | worker 進程數；每個各佔一份 VRAM |
| `MT_WORKER_CONCURRENCY` | `5` | 每 worker 並發數；GPU 階段串行但 LLM 階段可重疊 |
| `MANGA_TRANSLATOR_FONT_PATH` | （無） | 渲染字型絕對路徑；未設用內建台北黑體 |
| `GEMINI_2STAGE_TEMP` | `0.0` | 翻譯溫度 |
| `MANGA_OCR_MODEL_DIR` | （無） | 自訂 manga-ocr 模型路徑（一般不用設） |

---

## 啟動參數

```
python server/main.py [選項]
```

| 參數 | 預設 | 說明 |
|------|------|------|
| `--host` | `127.0.0.1` | 綁定位址 |
| `--port` | `8000` | API port；worker 起在 `port+1`、`port+2`... |
| `--start-instance` | 必填 | 自動啟動 worker 子進程 |
| `--use-gpu` | off | 啟用 CUDA / MPS（強烈建議） |
| `--nonce` | random | worker 內部通訊驗證；本機使用設 `None` 停用 |
| `--models-ttl` | `0` | 模型留在記憶體秒數，`0` = 不卸載 |
| `--verbose` | off | debug log + 中間結果圖 |

---

## API

| Method | Path | 說明 |
|--------|------|------|
| `POST` | `/translate/with-form/image/stream` | multipart 上傳圖 + JSON config，串流回傳（網頁介面走這條） |
| `POST` | `/translate/json` | 回 JSON（每個文字框座標、原文、譯文） |
| `POST` | `/translate/image` | 回 PNG（注意：請優先用 stream 版） |
| `POST` | `/translate/batch/{json,images}` | 批次翻譯 |
| `GET`  | `/queue-size` | 排隊長度 |
| `GET`  | `/` | 網頁介面 |

呼叫範例：

```python
import json, requests

with open("page.png", "rb") as f:
    img = f.read()

config = {
    "translator": {"target_lang": "CHT", "translator": "gemini_2stage"},
    "detector":   {"detector": "default", "detection_size": 1536,
                   "text_threshold": 0.20, "box_threshold": 0.20, "unclip_ratio": 1.2},
    "ocr":        {"ocr": "mocr", "min_text_length": 2, "prob": 0.2},
    "inpainter":  {"inpainter": "lama_mpe", "inpainting_size": 1280,
                   "inpainting_precision": "bf16"},
    "render":     {"font_size_minimum": 14, "alignment": "left"},
}

resp = requests.post(
    "http://127.0.0.1:8001/translate/with-form/image/stream",
    files={"image": ("page.png", img, "image/png")},
    data={"config": json.dumps(config)},
    timeout=600, stream=True,
)
```

stream chunk 格式（每筆）：`1 byte status | 4 byte big-endian size | N bytes payload`
（status: 0=最終圖片、1=進度文字、2=錯誤、3=排隊位置、4=等待 worker）

`target_lang`：`CHT`（繁中）/ `CHS`（簡中）/ `ENG` / `JPN` / `KOR` 等。

完整 config schema 見 [`manga_translator/config.py`](manga_translator/config.py)。

---

## 專案結構

```
DragonMeow-MangaTranslator/
├── server/                  # FastAPI HTTP server + 網頁介面
│   ├── main.py              # 入口（python server/main.py）
│   └── index.html           # 拖放上傳網頁
├── manga_translator/
│   ├── manga_translator.py  # 主流程：detection → OCR → 翻譯 → inpaint → render
│   ├── config.py            # config schema
│   ├── detection/           # DBNet 文字偵測
│   ├── ocr/                 # manga-ocr + 48px model
│   ├── translators/         # gemini_2stage（Gemini API）
│   ├── inpainting/          # LaMa 抹字
│   ├── bubble_detection/    # YOLOv8 氣泡偵測
│   └── rendering/           # 嵌字（直排、縱中橫、自動換行）
├── fonts/                   # 開源字型（台北黑體、Noto CJK 等）
├── models/                  # 模型權重（zip 內附；git clone 首跑自動下載）
├── setup.bat / start.bat    # Windows 一鍵安裝 / 啟動
└── .env.example
```

---

## 效能備忘

- 單 worker + `MT_WORKER_CONCURRENCY=5` 對單卡最划算：GPU 階段排隊，但多頁的 Gemini 翻譯可以重疊
- 多 worker（`MT_NUM_WORKERS=2`）讓 GPU 階段真並行，但 VRAM ×N
- 長條 webtoon 建議呼叫端先把最長邊縮到 12000px 以下（OpenCV remap 上限）
- 小圖（< 1280px）建議先放大再送，inpaint 後文字較不糊

---

## 致謝與授權

- 翻譯 pipeline 與模型整合：[zyddnys/manga-image-translator](https://github.com/zyddnys/manga-image-translator)
- 文字偵測 DBNet：[MhLiao/DB](https://github.com/MhLiao/DB)
- OCR：[kha-white/manga-ocr](https://github.com/kha-white/manga-ocr)
- 抹字 LaMa：[advimman/lama](https://github.com/advimman/lama)
- 氣泡偵測權重：[ogkalu/comic-speech-bubble-detector-yolov8m](https://huggingface.co/ogkalu/comic-speech-bubble-detector-yolov8m)
- 字型：[台北黑體](https://sites.google.com/view/jtfoundry/)（SIL OFL）、[Noto Sans CJK](https://github.com/notofonts/noto-cjk)（SIL OFL）

本專案授權 **GPL-3.0**（沿用上游）。翻譯內容請遵守當地著作權法規，僅供個人學習使用。

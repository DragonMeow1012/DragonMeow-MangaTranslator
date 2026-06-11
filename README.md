# 漫畫翻譯器 · DragonMeow-MangaTranslator

把漫畫圖片**一鍵翻譯**成中文（或其他語言）的小工具。
自動偵測對白、抹掉原文、把譯文嵌回氣泡裡。內建網頁操作介面，拖張圖進去就能翻。

> 由 **龍龍喵（DragonMeow）** 製作，**完全免費**的開源專案。任何收費版本都是盜版。

---

## 三步開始用（Windows）

1. **裝 Python** —— 到 [python.org](https://www.python.org/downloads/) 下載 3.10 或 3.11，安裝時記得勾 **Add to PATH**。
2. **雙擊 `setup.bat`** —— 自動裝好環境（第一次要等幾分鐘）。裝完會幫你建一個 `.env` 檔。
3. **填 API key** —— 打開 `app\.env`，把你的 Gemini API key 貼進去（[免費申請](https://aistudio.google.com/apikey)）：
   ```
   GEMINI_API_KEY=你的key
   ```
4. **雙擊 `start.bat`** —— 瀏覽器會自動打開操作介面，把漫畫圖拖進去就開始翻。

就這樣。下載的壓縮包已內附所有模型，不用另外下載。

> 想用 ChatGPT、Claude、DeepSeek 等其他 AI？不必改 `.env`，直接在網頁上選供應商、填那家的 key 就好。

---

## 能做什麼

- **拖放就翻**：單張、多張、整個資料夾，或直接丟 **zip / cbz 整本漫畫**。
- **多家 AI**：Gemini / ChatGPT / Claude / Grok / DeepSeek / Qwen / Kimi / GLM / Mistral / Groq / OpenRouter，或自訂端點。
- **進階編輯**：翻完不滿意？打開「進階編輯」可逐格改譯文、字級、顏色、粗體、字間距、字型、位置、橫書/直書，改完即時重新渲染。
- **打包下載**：翻譯結果可全選打包成 zip。
- **多國介面**：繁中 / 簡中 / 英文 / 日文，翻譯目標語言可自由選。

---

## 需要什麼

- Windows、Python 3.10 或 3.11
- **建議有 NVIDIA 顯卡**（沒有也能跑，但偵測/抹字會很慢）
- 一組 AI API key（Gemini 有免費額度）

裝顯卡加速版（強烈建議，setup 完跑一次）：
```
app\.venv\Scripts\pip install torch==2.6.0 torchvision==0.21.0 --force-reinstall --index-url https://download.pytorch.org/whl/cu124
```

---

## 從原始碼安裝（進階）

```bash
git clone https://github.com/DragonMeow1012/DragonMeow-MangaTranslator.git
cd DragonMeow-MangaTranslator
setup.bat   # 或手動：python -m venv app/.venv 後裝 app/requirements.txt
```
模型權重首次執行會自動下載（manga-ocr 需手動抓一次，見下）；zip release 版已內附、免下載。
```bash
# 只有 git clone 才需要：下載 manga-ocr 模型
app\.venv\Scripts\python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='kha-white/manga-ocr-base')"
```

---

## 資料夾結構

根目錄只放兩個按鈕，其餘都在 `app/`：

```
DragonMeow-MangaTranslator/
├── setup.bat        ← 安裝（雙擊一次）
├── start.bat        ← 啟動（每次用都點這個）
├── README.md
└── app/             ← 程式本體、模型、字型、設定都在這
    ├── .env             你的 API key 填這裡
    ├── server/          網頁介面 + API
    ├── manga_translator/ 翻譯核心
    ├── models/          模型權重
    └── fonts/           字型
```

---

## 支持作者

這個工具完全免費。如果它幫到你，歡迎：

- ⭐ 到 [GitHub](https://github.com/DragonMeow1012/DragonMeow-MangaTranslator) 給顆星星
- ☕ [請我喝杯咖啡](https://buymeacoffee.com/dragonmeow1012)

---

## 致謝與授權

翻譯流程基於 [zyddnys/manga-image-translator](https://github.com/zyddnys/manga-image-translator) 精簡改造。
模型：[manga-ocr](https://github.com/kha-white/manga-ocr)、[LaMa](https://github.com/advimman/lama)、[DBNet](https://github.com/MhLiao/DB)、[氣泡偵測](https://huggingface.co/ogkalu/comic-speech-bubble-detector-yolov8m)。
字型：[台北黑體](https://sites.google.com/view/jtfoundry/)、[Noto Sans CJK](https://github.com/notofonts/noto-cjk)（皆 SIL OFL）。

授權 **GPL-3.0**。請遵守當地著作權法規，僅供個人學習使用。

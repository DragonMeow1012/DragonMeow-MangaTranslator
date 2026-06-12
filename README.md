# 漫畫翻譯器 · DragonMeow-MangaTranslator

**繁體中文** | [简体中文](README.zh-CN.md) | [English](README.en.md) | [日本語](README.ja.md)

把漫畫圖片**一鍵翻譯**成中文（或其他語言）的小工具。
自動偵測對白、抹掉原文、再把譯文嵌回氣泡裡。內建網頁介面，拖張圖進去就能翻。

> 嗨，我是 **龍龍喵**。這個工具是我用 AI 一點一點打磨出來的 —— 整合了幾個優秀的開源專案（主要參考 [zyddnys/manga-image-translator](https://github.com/zyddnys/manga-image-translator)，並借鑑氣泡偵測、嵌字排版等做法），再接上 AI 翻譯。
> 對白翻譯品質相當不錯，少數排版或用字想再講究，可以用內建的「**進階編輯**」自己微調到滿意。做這個是想自己方便，也分享給有需要的人。
>
> 這是**完全免費**的開源專案，任何收費版本都是盜版。

---

## 三步開始用（Windows）

1. **裝 Python** —— 到 [python.org](https://www.python.org/downloads/) 下載 3.10 或 3.11，安裝時記得勾 **Add to PATH**。
2. **雙擊 `setup.bat`** —— 自動裝好環境（第一次要等幾分鐘）。
3. **雙擊 `start.bat`** —— 瀏覽器會自動打開介面，在上面**填一組 API key**，再把漫畫圖拖進去就開始翻。

下載的壓縮包已內附所有模型，不用另外下載。

> **API key 推薦用 Gemini** —— [免費申請](https://aistudio.google.com/apikey)、有免費額度、最好上手。
> 申請好之後直接貼在網頁的 key 欄位即可（多把用逗號分隔可自動輪換，翻大本漫畫比較不會撞額度）。
> 也支援 ChatGPT、Claude、DeepSeek 等，在網頁上選供應商、填那家的 key 就好。

---

## 能做什麼

- **拖放就翻**：單張、多張、整個資料夾，或直接丟 **zip / cbz 整本漫畫**。
- **多家 AI**：Gemini / ChatGPT / Claude / Grok / DeepSeek / Qwen / Kimi / GLM / Mistral / Groq / OpenRouter，或自訂端點。
- **進階編輯**：翻完不滿意？打開「進階編輯」可逐格改譯文、字級、顏色、粗體、字間距、字型、位置、橫書/直書，改完即時重新渲染。
- **打包下載**：翻譯結果可全選打包成 zip。
- **線上更新**：網頁可直接檢查 / 套用最新版（看完更新內容再決定）。
- **多國介面**：繁中 / 簡中 / 英文 / 日文，翻譯目標語言可自由選。

---

## 翻譯效果（前後對比）

直接看圖最有感。左邊原圖（日文）、右邊翻完（中文）：

<table>
  <tr>
    <th>原圖（日文）</th>
    <th>翻譯後（中文）</th>
  </tr>
  <tr>
    <td><img src="docs/example2-before.jpg" width="400"></td>
    <td><img src="docs/example2-after.png" width="400"></td>
  </tr>
</table>

> 對白幾乎都能順利翻出來；擬聲詞（SFX）預設是保留原文。**如果對成品不滿意，可以用下面的「進階編輯」進行調整。**

---

## 不滿意？用「進階編輯」修

翻完打開「進階編輯」，左邊逐格、右邊即時預覽：

<img src="docs/editor.png" width="760">

- 逐格改：**譯文 / 字級 / 顏色 / 粗體 / 字間距 / 字型 / 位置 / 橫書↔直書**
- 擬聲詞、符號、小字預設不翻，想翻就**取消勾選「維持原文」**再填譯文
- **按住「按住看原圖」** 隨時切回原圖比對
- 改完按「**重新渲染**」即時出圖，滿意按「**儲存**」—— 圖庫看到的就會是編輯後版本
- 還能「另存編輯檔」下次載回續編、「還原出廠」回到剛翻完的樣子

像上面編輯器裡那篇四格，調完輸出長這樣：

<img src="docs/example1-after.png" width="400">

---

## 需要什麼

- Windows、Python 3.10 或 3.11
- **建議有 NVIDIA 顯卡**（沒有也能跑，但偵測/抹字會很慢）
- 一組 AI API key（Gemini 有免費額度）

裝顯卡加速版（強烈建議）：setup 完**雙擊 `setup_gpu.bat`** 即可，會自動安裝 CUDA 版 PyTorch 並驗證顯卡可用。

---

## 從原始碼安裝（進階）

```bash
git clone https://github.com/DragonMeow1012/DragonMeow-MangaTranslator.git
cd DragonMeow-MangaTranslator
setup.bat
# 只有 git clone 才需要：下載 manga-ocr 模型
app\.venv\Scripts\python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='kha-white/manga-ocr-base')"
```
其餘模型權重首次執行會自動下載；zip release 版已內附、免下載。

---

## 資料夾結構

根目錄只放兩個按鈕，其餘都在 `app/`：

```
DragonMeow-MangaTranslator/
├── setup.bat        ← 安裝（雙擊一次）
├── setup_gpu.bat    ← 顯卡加速（有 NVIDIA 顯卡再點，雙擊一次）
├── start.bat        ← 啟動（每次用都點這個）
├── README.md
└── app/             ← 程式本體、模型、字型、設定都在這
    ├── .env             （選用）API key 也可寫在這，但通常直接在網頁填就好
    ├── server/          網頁介面 + API
    ├── manga_translator/ 翻譯核心
    ├── models/          模型權重
    └── fonts/           字型
```

---

## 支持作者

這個工具完全免費。如果它有幫到你，歡迎：

- ⭐ 到 [GitHub](https://github.com/DragonMeow1012/DragonMeow-MangaTranslator) 給顆星星（對我是很大的鼓勵）
- ☕ [請我喝杯咖啡](https://buymeacoffee.com/dragonmeow1012)

---

## 致謝與授權

本工具整合並感謝以下優秀的開源專案：
[zyddnys/manga-image-translator](https://github.com/zyddnys/manga-image-translator)、[manga-ocr](https://github.com/kha-white/manga-ocr)、[LaMa](https://github.com/advimman/lama)、[DBNet](https://github.com/MhLiao/DB)、[氣泡偵測](https://huggingface.co/ogkalu/comic-speech-bubble-detector-yolov8m)。
字型：[台北黑體](https://sites.google.com/view/jtfoundry/)、[Noto Sans CJK](https://github.com/notofonts/noto-cjk)（皆 SIL OFL）。

授權 **GPL-3.0**。請遵守當地著作權法規，僅供個人學習使用。

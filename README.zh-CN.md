# 漫画翻译器 · DragonMeow-MangaTranslator

[繁體中文](README.md) | **简体中文** | [English](README.en.md) | [日本語](README.ja.md)

把漫画图片**一键翻译**成中文（或其他语言）的小工具。
自动检测对白、抹掉原文、再把译文嵌回气泡里。内置网页界面，拖张图进去就能翻。

> 嗨，我是 **龙龙喵**。这个工具是我用 AI 一点一点打磨出来的 —— 整合了几个优秀的开源项目（主要参考 [zyddnys/manga-image-translator](https://github.com/zyddnys/manga-image-translator)，并借鉴气泡检测、嵌字排版等做法），再接上 AI 翻译。
> 对白翻译质量相当不错，少数排版或用字想再讲究，可以用内置的「**高级编辑**」自己微调到满意。做这个是想自己方便，也分享给有需要的人。
>
> 这是**完全免费**的开源项目，任何收费版本都是盗版。

---

## 三步开始用（Windows）

1. **装 Python** —— 到 [python.org](https://www.python.org/downloads/) 下载 3.10 或 3.11，安装时记得勾 **Add to PATH**。
2. **双击 `setup.bat`** —— 自动装好环境（第一次要等几分钟）。
3. **双击 `start.bat`** —— 浏览器会自动打开界面，在上面**填一组 API key**，再把漫画图拖进去就开始翻。

下载的压缩包已内附所有模型，不用另外下载。

> **API key 推荐用 Gemini** —— [免费申请](https://aistudio.google.com/apikey)、有免费额度、最好上手。
> 申请好之后直接贴在网页的 key 栏位即可（多把用逗号分隔可自动轮换，翻大本漫画比较不会撞额度）。
> 也支持 ChatGPT、Claude、DeepSeek 等，在网页上选供应商、填那家的 key 就好。

---

## 能做什么

- **拖放就翻**：单张、多张、整个文件夹，或直接丢 **zip / cbz 整本漫画**。
- **多家 AI**：Gemini / ChatGPT / Claude / Grok / DeepSeek / Qwen / Kimi / GLM / Mistral / Groq / OpenRouter，或自定义端点。
- **高级编辑**：翻完不满意？打开「高级编辑」可逐格改译文、字号、颜色、粗体、字间距、字体、位置、横排/竖排，改完即时重新渲染。
- **打包下载**：翻译结果可全选打包成 zip。
- **在线更新**：网页可直接检查 / 套用最新版（看完更新内容再决定）。
- **多国界面**：繁中 / 简中 / 英文 / 日文，翻译目标语言可自由选。

---

## 翻译效果（前后对比）

直接看图最有感。左边原图（日文）、右边翻完（中文）：

<table>
  <tr>
    <th>原图（日文）</th>
    <th>翻译后（中文）</th>
  </tr>
  <tr>
    <td><img src="docs/example2-before.jpg" width="400"></td>
    <td><img src="docs/example2-after.png" width="400"></td>
  </tr>
</table>

> 对白几乎都能顺利翻出来；拟声词（SFX）默认是保留原文。**如果对成品不满意，可以用下面的「高级编辑」进行调整。**

---

## 不满意？用「高级编辑」修

翻完打开「高级编辑」，左边逐格、右边即时预览：

<img src="docs/editor.png" width="760">

- 逐格改：**译文 / 字号 / 颜色 / 粗体 / 字间距 / 字体 / 位置 / 横排↔竖排**
- 拟声词、符号、小字默认不翻，想翻就**取消勾选「保留原文」**再填译文
- **按住「按住看原图」** 随时切回原图比对
- 改完按「**重新渲染**」即时出图，满意按「**保存**」—— 图库看到的就会是编辑后版本
- 还能「另存编辑档」下次载回续编、「还原出厂」回到刚翻完的样子

像上面编辑器里那篇四格，调完输出长这样：

<img src="docs/example1-after.png" width="400">

---

## 需要什么

- Windows、Python 3.10 或 3.11
- **建议有 NVIDIA 显卡**（没有也能跑，但检测/抹字会很慢）
- 一组 AI API key（Gemini 有免费额度）

装显卡加速版（强烈建议）：setup 完**双击 `setup_gpu.bat`** 即可，会自动安装 CUDA 版 PyTorch 并验证显卡可用。

---

## 从源码安装（进阶）

```bash
git clone https://github.com/DragonMeow1012/DragonMeow-MangaTranslator.git
cd DragonMeow-MangaTranslator
setup.bat
# 只有 git clone 才需要：下载 manga-ocr 模型
app\.venv\Scripts\python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='kha-white/manga-ocr-base')"
```
其余模型权重首次运行会自动下载；zip release 版已内附、免下载。

---

## 文件夹结构

根目录只放两个按钮，其余都在 `app/`：

```
DragonMeow-MangaTranslator/
├── setup.bat        ← 安装（双击一次）
├── setup_gpu.bat    ← 显卡加速（有 NVIDIA 显卡再点，双击一次）
├── start.bat        ← 启动（每次用都点这个）
├── README.md
└── app/             ← 程序本体、模型、字体、设置都在这
    ├── .env             （可选）API key 也可写在这，但通常直接在网页填就好
    ├── server/          网页界面 + API
    ├── manga_translator/ 翻译核心
    ├── models/          模型权重
    └── fonts/           字体
```

---

## 支持作者

这个工具完全免费。如果它有帮到你，欢迎：

- ⭐ 到 [GitHub](https://github.com/DragonMeow1012/DragonMeow-MangaTranslator) 给颗星星（对我是很大的鼓励）
- ☕ [请我喝杯咖啡](https://buymeacoffee.com/dragonmeow1012)

---

## 致谢与授权

本工具整合并感谢以下优秀的开源项目：
[zyddnys/manga-image-translator](https://github.com/zyddnys/manga-image-translator)、[manga-ocr](https://github.com/kha-white/manga-ocr)、[LaMa](https://github.com/advimman/lama)、[DBNet](https://github.com/MhLiao/DB)、[气泡检测](https://huggingface.co/ogkalu/comic-speech-bubble-detector-yolov8m)。
字体：[台北黑体](https://sites.google.com/view/jtfoundry/)、[Noto Sans CJK](https://github.com/notofonts/noto-cjk)（皆 SIL OFL）。

授权 **GPL-3.0**。请遵守当地著作权法规，仅供个人学习使用。

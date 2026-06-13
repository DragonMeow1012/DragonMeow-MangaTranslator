# 漫画翻訳ツール · DragonMeow-MangaTranslator

[繁體中文](README.md) | [简体中文](README.zh-CN.md) | [English](README.en.md) | **日本語**

漫画の画像を**ワンクリックで翻訳**する小さなツールです（中国語ほか各言語に対応）。
セリフを自動検出し、原文を消して、訳文を吹き出しに埋め戻します。Web UI 内蔵、画像をドラッグするだけ。

> こんにちは、**龍龍喵（DragonMeow）** です。AI と一緒に少しずつ磨き上げて作りました —— 優れたオープンソースプロジェクトをいくつか統合し（主に [zyddnys/manga-image-translator](https://github.com/zyddnys/manga-image-translator) を参考に、吹き出し検出や植字の手法も活用）、そこに AI 翻訳を繋げています。
> セリフの翻訳品質はかなり良好です。レイアウトや言い回しをもう少しこだわりたいときは、内蔵の「**詳細編集**」で納得いくまで微調整できます。自分用に作って、必要な人にも共有することにしました。
>
> これは**完全無料**のオープンソースプロジェクトです。有料版はすべて海賊版です。

---

## 2 ステップで開始（Windows）

1. **`setup.bat` をダブルクリック** —— 環境を自動構築（初回は数分かかります）。**Python のインストール不要**、zip にポータブル版を同梱済み。
2. **`start.bat` をダブルクリック** —— ブラウザが自動で開くので、**API key を入力**して漫画画像をドラッグすれば翻訳開始。

リリース zip にはモデルがすべて同梱済み。追加ダウンロードは不要です。

> **API key は Gemini がおすすめ** —— [無料で取得](https://aistudio.google.com/apikey)でき、無料枠があり、いちばん簡単。
> 取得したら Web ページの key 欄に貼るだけ（カンマ区切りで複数登録すると自動ローテーションし、長編でもレート制限に当たりにくくなります）。
> ChatGPT・Claude・DeepSeek なども対応 —— ページ上でプロバイダを選んでその key を入れるだけ。

---

## 画面

左サイドバーに設定をまとめて配置（① AI を選んで key を入力 → ② 出力言語を選択）。右側に漫画をドロップすれば翻訳開始。キューと結果はタブで切り替え。
**ダークモード**対応、テーマカラーは**青 / ピンク / アンバー**から選べます。

<table>
  <tr>
    <th>ライト（青）</th>
    <th>ダークモード（ピンク）</th>
  </tr>
  <tr>
    <td><img src="docs/ui-main.png" width="420"></td>
    <td><img src="docs/ui-dark.png" width="420"></td>
  </tr>
</table>

---

## できること

- **ドラッグ＆ドロップ**：1 枚でも複数でもフォルダ丸ごとでも、**zip / cbz の単行本まるごと**でも OK。
- **マルチ AI**：Gemini / ChatGPT / Claude / Grok / DeepSeek / Qwen / Kimi / GLM / Mistral / Groq / OpenRouter、カスタムエンドポイントも。
- **詳細編集**：仕上がりに不満なら、コマごとに訳文・サイズ・色・太字・字間・フォント・位置・縦書き/横書きを調整して即再レンダリング。
- **一括ダウンロード**：結果を選択して zip でダウンロード。
- **オンライン更新**：Web ページから最新版の確認・適用が可能（更新内容を見てから決められます）。
- **多言語 UI**：繁体字/簡体字中国語・英語・日本語。翻訳先言語も自由に選択。

---

## 翻訳例（ビフォー / アフター）

百聞は一見にしかず。左が原画（日本語）、右が翻訳後（中国語）：

<table>
  <tr>
    <th>原画（日本語）</th>
    <th>翻訳後（中国語）</th>
  </tr>
  <tr>
    <td><img src="docs/example2-before.jpg" width="400"></td>
    <td><img src="docs/example2-after.png" width="400"></td>
  </tr>
</table>

> セリフはほぼ問題なく翻訳できます。擬音（SFX）はデフォルトで原文のまま。**仕上がりに不満があれば、下の「詳細編集」で調整できます。**

<sub>サンプル画像：[ツユハ🐈 (@tuyu_ha28)](https://x.com/tuyu_ha28/status/2058480714937663927) さんの作品です。翻訳効果のデモ用途のみに使用しています。著作権は原作者に帰属します。</sub>

---

## 不満なら「詳細編集」で修正

翻訳後に「詳細編集」を開くと、左にコマごとのカード、右にライブプレビュー：

<img src="docs/editor.png" width="760">

- コマごとに編集：**訳文 / サイズ / 色 / 太字 / 字間 / フォント / 位置 / 縦書き↔横書き**
- 擬音・記号・小さい文字はデフォルトでスキップ。訳したければ**「原文のまま」のチェックを外して**訳文を入力
- **「長押しで原画」を押している間**は原画に切り替わり、比較が簡単
- 「**再レンダリング**」で即結果を確認、納得したら「**保存**」—— ギャラリーには編集後のバージョンが表示されます
- 編集ファイルの書き出し / 読み込みで続きから編集、「初期状態に戻す」で翻訳直後に戻すことも可能

上の編集画面で調整中の 4 コマは、こんな仕上がりになります：

<img src="docs/example1-after.png" width="400">

---

## 🧩 Chrome 拡張：漫画サイト上でそのまま翻訳

v1.3 で**ブラウザ拡張**を追加 —— 画像をダウンロードせず、漫画サイト上でそのまま翻訳し、訳文を原画像に重ねます。お使いのローカル AI サーバー経由で動作し、**画像は第三者クラウドに送られません**。

<table>
  <tr>
    <td width="33%"><img src="docs/ext-feat-translate.png"></td>
    <td width="33%"><img src="docs/ext-feat-exp.png"></td>
    <td width="33%"><img src="docs/ext-feat-ai.png"></td>
  </tr>
  <tr>
    <th>基本翻訳</th><th>実験的機能</th><th>AI 設定</th>
  </tr>
</table>

- **複数の翻訳方法**：画像を選んで翻訳、ページ全体、ページ送り翻訳（自動）。
- **結合翻訳**：分割されたコマを枠で囲んで結合し、まとめて翻訳（cmoa などの対策サイト向け）。ホイールでのページ送りにも対応。
- **原画像取得**：レイアウト異常や縮小表示のとき、原寸で取得して翻訳。
- **多言語 UI**：繁体中文 / 簡体中文 / English / 日本語。

### インストール（デベロッパーモード — 審査通過前でも使えます）

> 拡張は現在 **Chrome ウェブストアで審査中**です。承認され次第、ここにワンクリックのインストールリンクを追加します。今はデベロッパーモードで読み込めます：

1. **先にアプリを起動**（`start.bat` または `bash start.sh`）し、`http://127.0.0.1:8501` が開いていることを確認 —— 拡張はこれを使って翻訳します。
2. リリースの **`chrome-extension.zip`** をダウンロードして展開。
3. Chrome で `chrome://extensions` を開く → 右上の「**デベロッパーモード**」をオン。
4. 「**パッケージ化されていない拡張機能を読み込む**」→ `manifest.json` を含む展開済みフォルダを選択。
5. （任意）パズルピースのアイコンから拡張をツールバーに**固定**。
6. 拡張を開く →「🔄 Web設定を取得」で AI プロバイダ / API key を反映（手動入力も可）。
7. 漫画ページで「✨ バブルを有効化」→ 画像上の「譯」バブルを押すと翻訳。「ページ全体を翻訳 / ページ送り翻訳」も使えます。

> 新しいサイトに入るたびに「バブルを有効化」を押し直してください。

---

## 必要なもの

- Windows または macOS（**Python のインストール不要**、zip にポータブル版を同梱）
- **NVIDIA GPU か Apple Silicon（M シリーズ）推奨**（なくても動きますが、検出・修復がかなり遅くなります）
- AI の API key（Gemini は無料枠あり）

GPU 加速版のインストール（強く推奨）：
- **Windows**：setup 後に **`setup_gpu.bat` をダブルクリック**するだけ。CUDA 版 PyTorch を自動インストールし、GPU の認識まで確認します
- **macOS**：`-mac.zip` をダウンロードし、ターミナルで `bash setup.sh` → `bash start.sh`。Apple Silicon は MPS 加速が自動で有効になり、追加インストール不要です

---

## ソースからインストール（上級者向け）

```bash
git clone https://github.com/DragonMeow1012/DragonMeow-MangaTranslator.git
cd DragonMeow-MangaTranslator
setup.bat
# git clone の場合のみ必要：manga-ocr モデルのダウンロード
app\.venv\Scripts\python -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='kha-white/manga-ocr-base')"
```
その他のモデルは初回実行時に自動ダウンロード。zip リリース版は同梱済みで不要です。

> **zip 版は Python のインストール不要**（ポータブル版を同梱）。`git clone` には同梱 Python が含まれないため、自分で Python 3.10–3.12 が必要です（`setup.bat` は同梱 Python が見つからない場合、システムの Python から `.venv` を自動作成します）。

---

## フォルダ構成

ルートにはボタン 2 つだけ。残りは全部 `app/` の中：

```
DragonMeow-MangaTranslator/
├── setup.bat        ← インストール（最初に 1 回）
├── setup_gpu.bat    ← GPU 加速（NVIDIA GPU がある場合のみ、1 回）
├── start.bat        ← 起動（毎回これ）
├── README.md
└── app/             ← 本体・モデル・フォント・設定
    ├── .env             （任意）API key をここに書いても OK。普通は Web ページで入力すれば十分
    ├── server/          Web UI + API
    ├── manga_translator/ 翻訳コア
    ├── models/          モデル
    └── fonts/           フォント
```

---

## 作者を応援

このツールは完全無料です。役に立ったら：

- ⭐ [GitHub](https://github.com/DragonMeow1012/DragonMeow-MangaTranslator) でスターを（とても励みになります）
- ☕ [コーヒーをおごる](https://buymeacoffee.com/dragonmeow1012)

---

## 謝辞とライセンス

本ツールは以下の優れたオープンソースプロジェクトを統合し、感謝しています：
[zyddnys/manga-image-translator](https://github.com/zyddnys/manga-image-translator)、[manga-ocr](https://github.com/kha-white/manga-ocr)、[LaMa](https://github.com/advimman/lama)、[DBNet](https://github.com/MhLiao/DB)、[吹き出し検出](https://huggingface.co/ogkalu/comic-speech-bubble-detector-yolov8m)。
フォント：[Taipei Sans TC](https://sites.google.com/view/jtfoundry/)、[Noto Sans CJK](https://github.com/notofonts/noto-cjk)（いずれも SIL OFL）。

ライセンスは **GPL-3.0**。各地域の著作権法を守り、個人の学習目的でご利用ください。

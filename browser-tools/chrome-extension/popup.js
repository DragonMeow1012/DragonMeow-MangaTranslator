"use strict";

const I18N = {
  zht: {
    auto: "🔁 頁碼翻譯（翻頁自動翻）",
    autoHint: "適用於每頁一個連續網址",
    tpHint: "適用於下拉式長條漫畫；新載入內容會繼續翻譯，再點一次停止",
    pfCount: "預先翻譯頁數",
    pfNotify: "顯示預抓頁數",    enable: "✨ 啟用翻譯泡泡",
    disableBubble: "🚫 關閉翻譯泡泡",
    enableHint: "每次進入新網站需重新啟用",
    pick: "🖼 選取圖片翻譯替換",
    translatePage: "📄 整頁翻譯",
    downloadCurrent: "⬇ 下載此頁翻譯圖",
    downloadAll: "⬇ 下載所有翻譯圖（zip）",
    retry: "翻譯失敗自動重試",
    crawl: "🕷 原圖抓取（圖排版異常時使用）",
    crawlHint: "需授權存取「目前網站」，才能抓到原始解析度",
    debug: "🐞 偵錯：下載送出的圖",
    diagnose: "🔍 診斷快取套用",
    test: "🔌 測試連接",
    testing: "測試中…",
    testOk: "✓ 連接成功",
    testFail: "✗ 連接失敗：",
    syncWeb: "🔄 同步網頁設定",
    syncWebOk: "✓ 已回填網頁設定",
    openWeb: "🌐 開啟翻譯網站",
    cacheInfo: "快取：{n} 張 / {s}",
    viewOriginal: "👁 顯示原圖",
    viewTranslated: "👁 顯示翻譯圖",
    hint: "　",
    secAi: "翻譯 AI",
    fProvider: "服務商",
    fModel: "模型",
    fApikey: "API key",
    fBaseurl: "Base URL",
    fSendimage: "傳圖給 AI 校對",
    secOut: "輸出設定",
    fTargetlang: "翻譯成",
    save: "💾 儲存設定",
    saving: "儲存中…",
    savedLocal: "已儲存（伺服器未連線）",
    savedSynced: "已儲存並同步伺服器",
    apikeyKeep: "已設定（留空不變更）",
    apikeyEmpty: "尚未設定",
    bubbleTitle: "泡泡個性化",
    size: "大小", color: "顏色", text: "文字",
    reset: "恢復預設",
    loading: "設定載入中…",
    noSync: "尚未同步設定。<br>開啟 <b>127.0.0.1:8501</b> 的 MangaTranslator 頁面即會自動同步。",
    syncOk: "已從伺服器同步設定",
    syncFail: "設定讀取失敗",
    serverOn: "伺服器運行中",
    serverOff: "伺服器未啟動",
    serverChecking: "偵測中…",
    clearCurrent: "🧹 清除翻譯",
    clearAll: "🗑 清除所有翻譯",
    clearCacheDone: "已清除",
    errChrome: "此頁面無法使用（chrome:// 或商店頁面不支援這個擴充功能）",
    errFail: "操作失敗：",
    apiSet: "已設定", apiUnset: "未設定",
    targetLang: "目標語言",
    grpTranslate: "翻譯",
    grpView: "檢視 / 原圖",
    grpOutput: "下載 / 清除",
    grpExp: "🧪 實驗功能",
    autoLockHint: "⚠ 需先開啟下方「🕷 原圖抓取」才能用頁碼翻譯（它要爬後面幾頁的圖）",
    box: "🧩 合併翻譯（分割/打散防盜用）",
    boxHint: "把被拆分的漫畫格子一塊塊框起來，合併成一張一起翻譯（cmoa 等防盜站適用）；框選位置會記住，之後每換一頁點「譯」泡泡即可重翻同位置。<br>⚠️ 請一頁翻完再翻下一頁，否則頁碼會對不上；亂掉時清除翻譯重來即可。",
    wheel: "🖱 滾輪翻頁（配合合併翻譯）",
    wheelDir: "翻頁方向",
    wheelRtl: "右到左（日漫）",
    wheelLtr: "左到右",
    wheelVert: "上下",
    wheelHint: "滾輪往下＝下一張、往上＝上一張（被鎖住無法捲動的閱讀器用）",
  },
  zhs: {
    auto: "🔁 页码翻译（翻页自动翻）",
    autoHint: "适用于每页一个连续网址",
    tpHint: "适用于下拉式长条漫画；新加载内容会继续翻译，再点一次停止",
    pfCount: "预先翻译页数",
    pfNotify: "显示预抓页数",    enable: "✨ 启用翻译气泡",
    disableBubble: "🚫 关闭翻译气泡",
    enableHint: "每次进入新网站需重新启用",
    pick: "🖼 选取图片翻译替换",
    translatePage: "📄 整页翻译",
    downloadCurrent: "⬇ 下载此页翻译图",
    downloadAll: "⬇ 下载所有翻译图（zip）",
    retry: "翻译失败自动重试",
    crawl: "🕷 原图抓取（图排版异常时使用）",
    crawlHint: "需授权访问「当前网站」，才能抓到原始分辨率",
    debug: "🐞 调试：下载送出的图",
    diagnose: "🔍 诊断缓存套用",
    test: "🔌 测试连接",
    testing: "测试中…",
    testOk: "✓ 连接成功",
    testFail: "✗ 连接失败：",
    syncWeb: "🔄 同步网页设置",
    syncWebOk: "✓ 已回填网页设置",
    openWeb: "🌐 打开翻译网站",
    cacheInfo: "缓存：{n} 张 / {s}",
    viewOriginal: "👁 显示原图",
    viewTranslated: "👁 显示翻译图",
    hint: "　",
    secAi: "翻译 AI",
    fProvider: "服务商",
    fModel: "模型",
    fApikey: "API key",
    fBaseurl: "Base URL",
    fSendimage: "传图给 AI 校对",
    secOut: "输出设置",
    fTargetlang: "翻译成",
    save: "💾 保存设置",
    saving: "保存中…",
    savedLocal: "已保存（服务器未连线）",
    savedSynced: "已保存并同步服务器",
    apikeyKeep: "已设置（留空不变更）",
    apikeyEmpty: "尚未设置",
    bubbleTitle: "气泡个性化",
    size: "大小", color: "颜色", text: "文字",
    reset: "恢复默认",
    loading: "设置加载中…",
    noSync: "尚未同步设置。<br>打开 <b>127.0.0.1:8501</b> 的 MangaTranslator 页面即会自动同步。",
    syncOk: "已从服务器同步设置",
    syncFail: "设置读取失败",
    serverOn: "服务器运行中",
    serverOff: "服务器未启动",
    serverChecking: "检测中…",
    clearCurrent: "🧹 清除翻译",
    clearAll: "🗑 清除所有翻译",
    clearCacheDone: "已清除",
    errChrome: "此页面无法使用（chrome:// 或商店页面不支持此扩展）",
    errFail: "操作失败：",
    apiSet: "已设置", apiUnset: "未设置",
    targetLang: "目标语言",
    grpTranslate: "翻译",
    grpView: "查看 / 原图",
    grpOutput: "下载 / 清除",
    grpExp: "🧪 实验功能",
    autoLockHint: "⚠ 需先开启下方「🕷 原图抓取」才能用页码翻译（它要爬后面几页的图）",
    box: "🧩 合并翻译（分割/打散防盗用）",
    boxHint: "把被拆分的漫画格子一块块框起来，合并成一张一起翻译（cmoa 等防盗站适用）；框选位置会记住，之后每换一页点「译」气泡即可重翻同位置。<br>⚠️ 请一页翻完再翻下一页，否则页码会对不上；乱掉时清除翻译重来即可。",
    wheel: "🖱 滚轮翻页（配合合并翻译）",
    wheelDir: "翻页方向",
    wheelRtl: "右到左（日漫）",
    wheelLtr: "左到右",
    wheelVert: "上下",
    wheelHint: "滚轮向下＝下一张、向上＝上一张（被锁住无法滚动的阅读器用）",
  },
  en: {
    auto: "🔁 Page-by-page (auto on turn)",
    autoHint: "For sites with one URL per page",
    tpHint: "For long-strip / webtoon; keeps translating newly loaded content, click again to stop",
    pfCount: "Pages ahead to translate",
    pfNotify: "Show prefetch progress",    enable: "✨ Enable bubble",
    disableBubble: "🚫 Disable bubble",
    enableHint: "Re-enable on each new site",
    pick: "🖼 Pick image to translate",
    translatePage: "📄 Translate whole page",
    downloadCurrent: "⬇ Download this page",
    downloadAll: "⬇ Download all (zip)",
    retry: "Auto-retry on failure",
    crawl: "🕷 Fetch original (if layout looks off)",
    crawlHint: "Requires access to the current site to fetch full resolution",
    debug: "🐞 Debug: download sent image",
    diagnose: "🔍 Diagnose cache",
    test: "🔌 Test connection",
    testing: "Testing…",
    testOk: "✓ Connected",
    testFail: "✗ Failed: ",
    syncWeb: "🔄 Pull web settings",
    syncWebOk: "✓ Settings pulled from web",
    openWeb: "🌐 Open web translator",
    cacheInfo: "Cache: {n} imgs / {s}",
    viewOriginal: "👁 Show original",
    viewTranslated: "👁 Show translated",
    hint: "　",
    secAi: "Translation AI",
    fProvider: "Provider",
    fModel: "Model",
    fApikey: "API key",
    fBaseurl: "Base URL",
    fSendimage: "Send image to AI",
    secOut: "Output",
    fTargetlang: "Translate to",
    save: "💾 Save settings",
    saving: "Saving…",
    savedLocal: "Saved (server offline)",
    savedSynced: "Saved & synced to server",
    apikeyKeep: "Set (leave blank to keep)",
    apikeyEmpty: "Not set",
    bubbleTitle: "Bubble style",
    size: "Size", color: "Color", text: "Label",
    reset: "Reset",
    loading: "Loading settings…",
    noSync: "No settings synced.<br>Open <b>127.0.0.1:8501</b> MangaTranslator to auto-sync.",
    syncOk: "Settings synced from server",
    syncFail: "Failed to load settings",
    serverOn: "Server running",
    serverOff: "Server offline",
    serverChecking: "Checking…",
    clearCurrent: "🧹 Clear this page",
    clearAll: "🗑 Clear all translations",
    clearCacheDone: "Cleared",
    errChrome: "Not available on chrome:// or store pages",
    errFail: "Error: ",
    apiSet: "Set", apiUnset: "Not set",
    targetLang: "Target lang",
    grpTranslate: "Translate",
    grpView: "View / Original",
    grpOutput: "Download / Clear",
    grpExp: "🧪 Experimental",
    autoLockHint: "⚠ Enable 「🕷 Fetch original」 below first to use page-by-page (it crawls the next pages' images)",
    box: "🧩 Merge translate (split / scattered anti-piracy)",
    boxHint: "Box the split manga panels one by one and merge them into a single image to translate together (for anti-piracy sites like cmoa). The boxed region is remembered—on each new page just click the 「譯」 bubble to re-translate the same spot.<br>⚠️ Finish one page before the next, or page numbers desync; if it gets messy, clear translations and redo.",
    wheel: "🖱 Wheel page-turn (with merge translate)",
    wheelDir: "Page direction",
    wheelRtl: "Right to left (manga)",
    wheelLtr: "Left to right",
    wheelVert: "Vertical",
    wheelHint: "Wheel down = next, up = previous (for readers that lock scrolling)",
  },
  ja: {
    auto: "🔁 ページ送り翻訳（自動）",
    autoHint: "1ページ1URLのサイト向け",
    tpHint: "縦読み（ウェブトゥーン）向け；新しく読み込まれた内容も継続翻訳、もう一度で停止",
    pfCount: "先に翻訳するページ数",
    pfNotify: "先読みページ数を表示",    enable: "✨ バブルを有効化",
    disableBubble: "🚫 バブルを無効化",
    enableHint: "新しいサイトごとに再有効化が必要",
    pick: "🖼 画像を選んで翻訳",
    translatePage: "📄 ページ全体を翻訳",
    downloadCurrent: "⬇ このページをDL",
    downloadAll: "⬇ すべてDL（zip）",
    retry: "失敗時に自動リトライ",
    crawl: "🕷 原画像取得（レイアウト異常時）",
    crawlHint: "現在のサイトへのアクセス許可が必要（原寸取得用）",
    debug: "🐞 デバッグ：送信画像をDL",
    diagnose: "🔍 キャッシュ診断",
    test: "🔌 接続テスト",
    testing: "テスト中…",
    testOk: "✓ 接続成功",
    testFail: "✗ 接続失敗：",
    syncWeb: "🔄 Web設定を取得",
    syncWebOk: "✓ Web設定を反映しました",
    openWeb: "🌐 翻訳サイトを開く",
    cacheInfo: "キャッシュ：{n} 枚 / {s}",
    viewOriginal: "👁 原画像を表示",
    viewTranslated: "👁 翻訳画像を表示",
    hint: "　",
    secAi: "翻訳 AI",
    fProvider: "プロバイダ",
    fModel: "モデル",
    fApikey: "API key",
    fBaseurl: "Base URL",
    fSendimage: "画像を AI に送る",
    secOut: "出力設定",
    fTargetlang: "翻訳先",
    save: "💾 設定を保存",
    saving: "保存中…",
    savedLocal: "保存しました（サーバー未接続）",
    savedSynced: "保存してサーバーに同期しました",
    apikeyKeep: "設定済み（空欄で変更なし）",
    apikeyEmpty: "未設定",
    bubbleTitle: "バブルのカスタマイズ",
    size: "サイズ", color: "色", text: "ラベル",
    reset: "リセット",
    loading: "設定を読み込み中…",
    noSync: "設定未同期。<br><b>127.0.0.1:8501</b> の MangaTranslator を開くと自動同期します。",
    syncOk: "サーバーから設定を同期しました",
    syncFail: "設定の読み込みに失敗しました",
    serverOn: "サーバー起動中",
    serverOff: "サーバー未起動",
    serverChecking: "確認中…",
    clearCurrent: "🧹 このページを消去",
    clearAll: "🗑 すべての翻訳を消去",
    clearCacheDone: "削除完了",
    errChrome: "このページでは使用できません（chrome:// またはストアページ）",
    errFail: "エラー：",
    apiSet: "設定済み", apiUnset: "未設定",
    targetLang: "翻訳先言語",
    grpTranslate: "翻訳",
    grpView: "表示 / 原画像",
    grpOutput: "ダウンロード / 消去",
    grpExp: "🧪 実験的機能",
    autoLockHint: "⚠ ページ送り翻訳には下の「🕷 原画像取得」を先に有効化してください（次のページの画像を取得します）",
    box: "🧩 結合翻訳（分割・分散コピー対策用）",
    boxHint: "分割されたコマを1つずつ枠で囲み、1枚に結合してまとめて翻訳します（cmoa などの対策サイト向け）。枠の位置は記憶され、ページを変えるたびに「譯」バブルを押せば同じ位置を再翻訳できます。<br>⚠️ 1ページずつ翻訳してください（ページ番号がずれます）。乱れたら翻訳を消去してやり直してください。",
    wheel: "🖱 ホイールでページ送り（結合翻訳と併用）",
    wheelDir: "ページ送り方向",
    wheelRtl: "右から左（漫画）",
    wheelLtr: "左から右",
    wheelVert: "上下",
    wheelHint: "ホイール下＝次、上＝前（スクロールがロックされたビューア用）",
  }
};

const UI_LANG_KEY = "dmmtUiLang";
const SETTINGS_KEY = "dmmtSyncedSettings";
const BUBBLE_PREFS_KEY = "dmmtBubblePrefs";
const DEFAULT_BUBBLE_PREFS = { size: 48, color: "#0f766e", label: "譯" };

const errBox = document.getElementById("err");
const langSelect = document.getElementById("lang-select");

let currentLang = "zht";

function t(key) {
  return (I18N[currentLang] || I18N.zht)[key] || key;
}

let _currentServerStatus = "checking";

function applyLang() {
  document.getElementById("txt-auto").textContent = t("auto");
  document.getElementById("txt-enable-hint").textContent = t("enableHint");
  document.getElementById("txt-pick").textContent = t("pick");
  document.getElementById("txt-translate-page").textContent = t("translatePage");
  document.getElementById("txt-tp-hint").textContent = t("tpHint");
  document.getElementById("txt-auto-hint").textContent = t("autoHint");
  document.getElementById("txt-pf-notify").textContent = t("pfNotify");
  document.getElementById("txt-download-current").textContent = t("downloadCurrent");
  document.getElementById("txt-download-all").textContent = t("downloadAll");
  document.getElementById("txt-retry").textContent = t("retry");
  document.getElementById("txt-crawl").textContent = t("crawl");
  document.getElementById("txt-crawl-hint").textContent = t("crawlHint");
  document.getElementById("txt-debug").textContent = t("debug");
  document.getElementById("txt-diagnose").textContent = t("diagnose");
  document.getElementById("txt-test").textContent = t("test");
  document.getElementById("txt-sync-web").textContent = t("syncWeb");
  document.getElementById("txt-open-web").textContent = t("openWeb");
  document.getElementById("txt-hint").textContent = t("hint");
  document.getElementById("txt-bubble-title").textContent = t("bubbleTitle");
  document.getElementById("txt-size").textContent = t("size");
  document.getElementById("txt-color").textContent = t("color");
  document.getElementById("txt-text").textContent = t("text");
  document.getElementById("bubble-reset").textContent = t("reset");
  document.getElementById("txt-clear-current").textContent = t("clearCurrent");
  document.getElementById("txt-clear-all").textContent = t("clearAll");
  // 設定編輯器標籤
  document.getElementById("txt-sec-ai").textContent = t("secAi");
  document.getElementById("txt-provider").textContent = t("fProvider");
  document.getElementById("txt-model").textContent = t("fModel");
  document.getElementById("txt-apikey").textContent = t("fApikey");
  document.getElementById("txt-baseurl").textContent = t("fBaseurl");
  document.getElementById("txt-sendimage").textContent = t("fSendimage");
  document.getElementById("txt-sec-out").textContent = t("secOut");
  document.getElementById("txt-targetlang").textContent = t("fTargetlang");
  document.getElementById("txt-save").textContent = t("save");
  // 分組標題 + 實驗功能（先前漏譯，補上四語）
  document.getElementById("grp-translate").textContent = t("grpTranslate");
  document.getElementById("grp-view").textContent = t("grpView");
  document.getElementById("grp-output").textContent = t("grpOutput");
  document.getElementById("grp-exp").textContent = t("grpExp");
  document.getElementById("auto-lock-hint").textContent = t("autoLockHint");
  document.getElementById("txt-box").textContent = t("box");
  document.getElementById("txt-box-hint").innerHTML = t("boxHint");
  document.getElementById("txt-wheel").textContent = t("wheel");
  document.getElementById("txt-wheel-dir").textContent = t("wheelDir");
  document.getElementById("txt-wheel-hint").textContent = t("wheelHint");
  document.querySelector('#wheel-dir option[value="rtl"]').textContent = t("wheelRtl");
  document.querySelector('#wheel-dir option[value="ltr"]').textContent = t("wheelLtr");
  document.querySelector('#wheel-dir option[value="vertical"]').textContent = t("wheelVert");
  updateViewButton();
  updateEnableButton();
  updateApiKeyPlaceholder();
  setServerStatus(_currentServerStatus);
}

async function initLang() {
  const stored = await chrome.storage.local.get(UI_LANG_KEY);
  currentLang = stored[UI_LANG_KEY] || "zht";
  langSelect.value = currentLang;
  applyLang();
}

langSelect.addEventListener("change", async () => {
  currentLang = langSelect.value;
  await chrome.storage.local.set({ [UI_LANG_KEY]: currentLang });
  applyLang();
  loadSettings();
});

// ---- Tab / content script helpers ----

async function activeTabId() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab?.id;
}

async function ensureContentScript(tabId) {
  try {
    await chrome.scripting.insertCSS({ target: { tabId }, files: ["content.css"] });
    await chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] });
  } catch {
    // ignore
  }
}

// 背景訊息回應一律包成 { ok, result }，這裡解包並在失敗時拋出，方便上層 try/catch。
async function bg(message) {
  const resp = await chrome.runtime.sendMessage(message);
  if (!resp?.ok) throw new Error(resp?.error || "背景程序沒有回應");
  return resp.result;
}

async function sendCommand(action) {
  errBox.textContent = "";
  try {
    const tabId = await activeTabId();
    if (!tabId) throw new Error("找不到目前分頁");
    let response;
    try {
      response = await chrome.tabs.sendMessage(tabId, { type: "popup-command", action });
    } catch {
      await ensureContentScript(tabId);
      response = await chrome.tabs.sendMessage(tabId, { type: "popup-command", action });
    }
    if (!response?.ok) throw new Error(response?.error || "頁面沒有回應");
    updateButtons(response.state);
    return response.state;
  } catch (error) {
    const detail = String(error?.message || error);
    if (/Receiving end does not exist|Cannot access|chrome:\/\//i.test(detail)) {
      errBox.textContent = t("errChrome");
    } else {
      errBox.textContent = t("errFail") + detail;
    }
    return null;
  }
}

let _lastViewMode = "translated";
let _bubbleVisible = false; // 目前分頁泡泡是否顯示中

function updateViewButton() {
  // viewMode 為 translated 時，按鈕動作是「顯示原圖」，反之顯示翻譯圖。
  document.getElementById("txt-view").textContent =
    _lastViewMode === "translated" ? t("viewOriginal") : t("viewTranslated");
}

function updateEnableButton() {
  // 泡泡顯示中 → 按鈕變「關閉翻譯泡泡」，否則「啟用翻譯泡泡」。
  document.getElementById("txt-enable").textContent =
    _bubbleVisible ? t("disableBubble") : t("enable");
}

function updatePrefetchVisibility() {
  // 翻譯進度提示只在「頁碼翻譯」開啟時顯示。
  const on = document.getElementById("auto").classList.contains("on");
  document.getElementById("prefetch-opts").style.display = on ? "block" : "none";
}

function updateButtons(state) {
  if (!state) return;
  document.getElementById("auto").classList.toggle("on", Boolean(state.auto));
  document.getElementById("page").classList.toggle("on", Boolean(state.pageActive));
  document.getElementById("box-select").classList.toggle("on", Boolean(state.boxActive));
  updatePrefetchVisibility();
  if (state.viewMode) {
    _lastViewMode = state.viewMode;
    updateViewButton();
  }
  if (typeof state.uiVisible === "boolean") {
    _bubbleVisible = state.uiVisible;
    updateEnableButton();
  }
}

document.getElementById("enable-bubble").addEventListener("click", async () => {
  errBox.textContent = "";
  try {
    const tabId = await activeTabId();
    if (!tabId) throw new Error("找不到目前分頁");
    // 先嘗試對已注入的腳本切換顯示；失敗代表尚未注入 → 注入即顯示泡泡。
    try {
      const resp = await chrome.tabs.sendMessage(tabId, { type: "popup-command", action: "toggle-ui" });
      if (resp?.ok) {
        updateButtons(resp.state);
        if (!resp.state.uiVisible) return; // 關閉泡泡：留在 popup
        window.close();                    // 開啟泡泡：關 popup 讓使用者看到
        return;
      }
    } catch {
      // 尚未注入
    }
    await ensureContentScript(tabId);
    _bubbleVisible = true;
    updateEnableButton();
    window.close();
  } catch (error) {
    errBox.textContent = t("errChrome");
  }
});

document.getElementById("pick").addEventListener("click", async () => {
  const state = await sendCommand("toggle-pick");
  if (state) window.close(); // 關閉 popup 讓使用者點選頁面上的圖片
});

document.getElementById("page").addEventListener("click", async () => {
  const st = await sendCommand("toggle-page");
  updateButtons(st);
  if (st && st.pageActive) window.close(); // 開啟時關 popup 讓使用者看進度；關閉時留著
});

document.getElementById("download-current").addEventListener("click", () => {
  sendCommand("download-current");
});

document.getElementById("diagnose-cache").addEventListener("click", () => {
  sendCommand("diagnose-cache");
});

document.getElementById("download-all").addEventListener("click", () => {
  sendCommand("download-all");
});

// ---- 預抓進度提示開關（一律翻到完，不再有頁數設定）----
const PREFETCH_NOTIFY_KEY = "dmmtPrefetchNotify";
const pfNotifyRow = document.getElementById("pf-notify");
async function loadPrefetchPrefs() {
  const s = await chrome.storage.local.get(PREFETCH_NOTIFY_KEY);
  pfNotifyRow.classList.toggle("on", s[PREFETCH_NOTIFY_KEY] !== false); // 預設開
}
pfNotifyRow.addEventListener("click", async () => {
  const on = !pfNotifyRow.classList.contains("on");
  pfNotifyRow.classList.toggle("on", on);
  await chrome.storage.local.set({ [PREFETCH_NOTIFY_KEY]: on });
});

// ---- 滾輪翻頁（配合合併翻譯）----
const WHEEL_NAV_KEY = "dmmtWheelNav";
const wheelRow = document.getElementById("set-wheel");
async function loadWheelPref() {
  const s = await chrome.storage.local.get(WHEEL_NAV_KEY);
  wheelRow.classList.toggle("on", s[WHEEL_NAV_KEY] === true);
}
wheelRow.addEventListener("click", async () => {
  const on = !wheelRow.classList.contains("on");
  wheelRow.classList.toggle("on", on);
  await chrome.storage.local.set({ [WHEEL_NAV_KEY]: on });
});

const WHEEL_DIR_KEY = "dmmtWheelDir";
const wheelDirSel = document.getElementById("wheel-dir");
async function loadWheelDirPref() {
  const s = await chrome.storage.local.get(WHEEL_DIR_KEY);
  wheelDirSel.value = s[WHEEL_DIR_KEY] || "rtl";
}
wheelDirSel.addEventListener("change", async () => {
  await chrome.storage.local.set({ [WHEEL_DIR_KEY]: wheelDirSel.value });
});

document.getElementById("box-select").addEventListener("click", async () => {
  const st = await sendCommand("box-select");
  updateButtons(st);
  if (st && st.boxActive) window.close(); // 進入框選 → 關 popup 讓使用者去頁面選格子
});

document.getElementById("auto").addEventListener("click", async () => {
  // 頁碼翻譯靠爬蟲抓後面頁的圖 → 必須先開啟「原圖抓取」才能用，否則鎖住不啟用。
  const autoRow = document.getElementById("auto");
  const turningOn = !autoRow.classList.contains("on");
  if (turningOn) {
    const origins = await currentSiteOrigins();
    const granted = origins.length ? await chrome.permissions.contains({ origins }).catch(() => false) : false;
    if (!granted) {
      await loadCrawlPref(); // 確保鎖定樣式/提示是最新
      errBox.textContent = "請先開啟「🕷 原圖抓取」才能用頁碼翻譯";
      return;
    }
  }
  errBox.textContent = "";
  await sendCommand("toggle-auto");
});

document.getElementById("view").addEventListener("click", async () => {
  await sendCommand("toggle-view");
});

// ---- Server status indicator ----

const serverDot = document.getElementById("server-dot");
const serverLabel = document.getElementById("server-label");

function setServerStatus(status) {
  _currentServerStatus = status;
  serverDot.className = "dot dot-" + status;
  serverLabel.textContent = status === "online" ? t("serverOn")
    : status === "offline" ? t("serverOff")
    : t("serverChecking");
}

// ---- Editable translation settings ----

const providerSelect = document.getElementById("set-provider");
const modelInput = document.getElementById("set-model");
const apikeyInput = document.getElementById("set-apikey");
const baseurlInput = document.getElementById("set-baseurl");
const baseurlLabel = document.getElementById("txt-baseurl");
const sendimageRow = document.getElementById("set-sendimage");
const langSetSelect = document.getElementById("set-lang");
const saveStatus = document.getElementById("set-status");

let _view = null; // 後端回傳的設定視圖（含 models 與 apiKeySet）

function updateApiKeyPlaceholder() {
  const p = providerSelect.value;
  const isSet = _view?.apiKeySet?.[p];
  apikeyInput.placeholder = isSet ? t("apikeyKeep") : t("apikeyEmpty");
}

function applyViewToFields() {
  if (!_view) return;
  providerSelect.value = _view.llmProvider || "gemini";
  refreshProviderDependentFields();
  langSetSelect.value = _view.targetLanguage || "CHT";
  sendimageRow.classList.toggle("on", _view.llmSendImage !== false);
}

function refreshProviderDependentFields() {
  const p = providerSelect.value;
  const model = _view?.models?.[p];
  modelInput.value = model || _view?.providerDefaults?.[p] || "";
  // 回填該服務商目前的金鑰（密碼遮罩，需點眼睛才看明文）。
  apikeyInput.value = _view?.apiKeys?.[p] || "";
  apikeyInput.type = "password";
  updateApiKeyPlaceholder();
  const isCustom = p === "custom";
  baseurlInput.style.display = isCustom ? "block" : "none";
  baseurlLabel.style.display = isCustom ? "block" : "none";
  if (isCustom) baseurlInput.value = _view?.customBaseUrl || "";
}

async function loadSettings() {
  setServerStatus("checking");
  const stored0 = await chrome.storage.local.get(SETTINGS_KEY).catch(() => ({}));
  const apiBase = stored0[SETTINGS_KEY]?.apiBase || "http://127.0.0.1:8501";

  let serverOnline = false;
  try {
    await bg({ type: "fetch-server-settings", apiBase });
    serverOnline = true;
  } catch (e) {
    // 「伺服器尚未儲存設定」代表伺服器有開但還沒設定檔。
    serverOnline = /尚未儲存設定|伺服器回應/.test(e?.message || "");
  }
  setServerStatus(serverOnline ? "online" : "offline");

  try {
    _view = await bg({ type: "get-settings-view" });
    applyViewToFields();
  } catch {
    // 讀不到就維持預設欄位。
  }
}

providerSelect.addEventListener("change", refreshProviderDependentFields);
sendimageRow.addEventListener("click", () => sendimageRow.classList.toggle("on"));
document.getElementById("set-apikey-eye").addEventListener("click", () => {
  apikeyInput.type = apikeyInput.type === "password" ? "text" : "password";
});

document.getElementById("set-save").addEventListener("click", async () => {
  saveStatus.textContent = t("saving");
  const patch = {
    llmProvider: providerSelect.value,
    model: modelInput.value.trim(),
    llmSendImage: sendimageRow.classList.contains("on"),
    targetLanguage: langSetSelect.value
  };
  if (apikeyInput.value.trim() !== "") patch.apiKey = apikeyInput.value.trim();
  if (providerSelect.value === "custom") patch.customBaseUrl = baseurlInput.value.trim();
  try {
    const result = await bg({ type: "save-settings", patch });
    _view = result;
    // 不要呼叫 applyViewToFields()（會清掉剛輸入的金鑰欄位）；只更新「已設定」標記。
    updateApiKeyPlaceholder();
    saveStatus.textContent = result?.serverSaved ? t("savedSynced") : t("savedLocal");
  } catch {
    saveStatus.textContent = "⚠";
  }
  setTimeout(() => { saveStatus.textContent = ""; }, 2500);
});

// 🔄 同步網頁設定：重新從伺服器拉取設定並回填到欄位。
document.getElementById("sync-web").addEventListener("click", async () => {
  const st = document.getElementById("sync-web-status");
  st.style.color = "#5eead4";
  st.textContent = "…";
  await loadSettings();
  st.textContent = t("syncWebOk");
  setTimeout(() => { st.textContent = ""; }, 2500);
});

// ---- Auto-retry toggle ----
const AUTO_RETRY_KEY = "dmmtAutoRetry";
const retryRow = document.getElementById("set-retry");
async function loadRetryPref() {
  const stored = await chrome.storage.local.get(AUTO_RETRY_KEY);
  retryRow.classList.toggle("on", stored[AUTO_RETRY_KEY] !== false); // 預設開
}
retryRow.addEventListener("click", async () => {
  const on = !retryRow.classList.contains("on");
  retryRow.classList.toggle("on", on);
  await chrome.storage.local.set({ [AUTO_RETRY_KEY]: on });
});

// ---- Crawler: 只對「目前網站」授權去抓跨域原圖（不要求所有網站，商店審核較快）----
const crawlRow = document.getElementById("set-crawl");
async function currentSiteOrigins() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  try {
    const u = new URL(tab.url);
    const parts = u.hostname.split(".");
    const base = parts.length >= 2 ? parts.slice(-2).join(".") : u.hostname; // 例：nhentai.net
    return [`*://${base}/*`, `*://*.${base}/*`]; // 含圖片 CDN 子網域（i.nhentai.net 等）
  } catch { return []; }
}
async function loadCrawlPref() {
  const origins = await currentSiteOrigins();
  const granted = origins.length ? await chrome.permissions.contains({ origins }).catch(() => false) : false;
  crawlRow.classList.toggle("on", granted);
  // 頁碼翻譯綁定原圖抓取：沒授權就鎖住（不能選）並顯示提示
  const autoRow = document.getElementById("auto");
  if (autoRow) autoRow.classList.toggle("locked", !granted);
  const lockHint = document.getElementById("auto-lock-hint");
  if (lockHint) lockHint.style.display = granted ? "none" : "";
}
crawlRow.addEventListener("click", async () => {
  const origins = await currentSiteOrigins();
  if (!origins.length) return;
  const currentlyOn = crawlRow.classList.contains("on");
  try {
    if (currentlyOn) await chrome.permissions.remove({ origins });
    else await chrome.permissions.request({ origins });
  } catch {}
  await loadCrawlPref(); // 同步原圖抓取顯示 + 頁碼翻譯鎖定狀態
  // 關掉原圖抓取時，連帶關掉頁碼翻譯（它需要爬蟲，否則會空轉）
  const autoRow = document.getElementById("auto");
  if (autoRow && autoRow.classList.contains("locked") && autoRow.classList.contains("on")) {
    updateButtons(await sendCommand("toggle-auto"));
  }
});

// ---- Debug: dump the exact image sent to OCR ----
const DEBUG_INPUT_KEY = "dmmtDebugInput";
const debugRow = document.getElementById("set-debug");
async function loadDebugPref() {
  const stored = await chrome.storage.local.get(DEBUG_INPUT_KEY);
  debugRow.classList.toggle("on", stored[DEBUG_INPUT_KEY] === true); // 預設關
}
debugRow.addEventListener("click", async () => {
  const on = !debugRow.classList.contains("on");
  debugRow.classList.toggle("on", on);
  await chrome.storage.local.set({ [DEBUG_INPUT_KEY]: on });
});

// ---- Test connection ----
const testStatus = document.getElementById("test-status");
document.getElementById("test-conn").addEventListener("click", async () => {
  testStatus.style.color = "#5eead4";
  testStatus.textContent = t("testing");
  try {
    const result = await bg({ type: "test-connection" });
    if (result?.ok) {
      testStatus.style.color = "#5eead4";
      testStatus.textContent = t("testOk");
    } else {
      testStatus.style.color = "#fda4af";
      testStatus.textContent = t("testFail") + (result?.error || "");
    }
  } catch (e) {
    testStatus.style.color = "#fda4af";
    testStatus.textContent = t("testFail") + (e?.message || e);
  }
});

// ---- Open / sync web translator ----
document.getElementById("open-web").addEventListener("click", async () => {
  const stored = await chrome.storage.local.get(SETTINGS_KEY).catch(() => ({}));
  const apiBase = stored[SETTINGS_KEY]?.apiBase || "http://127.0.0.1:8501";
  chrome.tabs.create({ url: apiBase });
  window.close();
});

// ---- Cache size / count display ----
async function updateCacheInfo() {
  try {
    const all = await chrome.storage.local.get(null);
    let count = 0, bytes = 0;
    for (const k of Object.keys(all)) {
      if (!k.startsWith("dmmtImgCache:")) continue;
      count++;
      const entry = all[k];
      if (entry?.image) bytes += entry.image.length;
    }
    document.getElementById("cache-info").textContent =
      t("cacheInfo").replace("{n}", count).replace("{s}", formatBytes(bytes));
  } catch {
    document.getElementById("cache-info").textContent = "　";
  }
}
function formatBytes(b) {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}

async function loadState() {
  // 只查詢、不注入：泡泡需由「啟用翻譯泡泡」按鈕主動呼喚。
  // 若該分頁先前已啟用，內容腳本仍在，這裡能讀到目前狀態並反映到按鈕。
  try {
    const tabId = await activeTabId();
    if (!tabId) return;
    const response = await chrome.tabs.sendMessage(tabId, { type: "popup-command", action: "query" });
    if (response?.ok) updateButtons(response.state);
  } catch {
    // 尚未啟用或無法注入的頁面，按鈕保持預設即可。
  }
}

// ---- Bubble prefs ----

const sizeInput = document.getElementById("bubble-size");
const sizeValue = document.getElementById("bubble-size-value");
const colorInput = document.getElementById("bubble-color");
const labelInput = document.getElementById("bubble-label");

function fillPrefsInputs(prefs) {
  sizeInput.value = prefs.size;
  sizeValue.textContent = `${prefs.size}px`;
  colorInput.value = prefs.color;
  labelInput.value = prefs.label;
}

async function loadPrefs() {
  const stored = await chrome.storage.local.get(BUBBLE_PREFS_KEY);
  return { ...DEFAULT_BUBBLE_PREFS, ...(stored[BUBBLE_PREFS_KEY] || {}) };
}

async function savePrefs(partial) {
  const prefs = { ...(await loadPrefs()), ...partial };
  await chrome.storage.local.set({ [BUBBLE_PREFS_KEY]: prefs });
  fillPrefsInputs(prefs);
}

sizeInput.addEventListener("input", () => {
  sizeValue.textContent = `${sizeInput.value}px`;
  savePrefs({ size: Number(sizeInput.value) });
});
colorInput.addEventListener("input", () => savePrefs({ color: colorInput.value }));
labelInput.addEventListener("input", () => savePrefs({ label: labelInput.value.trim() || DEFAULT_BUBBLE_PREFS.label }));
document.getElementById("bubble-reset").addEventListener("click", async () => {
  await chrome.storage.local.set({ [BUBBLE_PREFS_KEY]: DEFAULT_BUBBLE_PREFS });
  fillPrefsInputs(DEFAULT_BUBBLE_PREFS);
});

// 清除翻譯：只還原目前頁面的翻譯並刪掉這些圖的快取。
document.getElementById("clear-current").addEventListener("click", async () => {
  const span = document.getElementById("txt-clear-current");
  try {
    const tabId = await activeTabId();
    if (tabId) await chrome.tabs.sendMessage(tabId, { type: "popup-command", action: "clear-current" });
    span.textContent = t("clearCacheDone");
  } catch {
    span.textContent = "⚠";
  }
  setTimeout(() => { span.textContent = t("clearCurrent"); }, 2000);
});

// 清除所有翻譯：清空整個快取儲存，並還原目前頁面。
document.getElementById("clear-all").addEventListener("click", async () => {
  const span = document.getElementById("txt-clear-all");
  try {
    const all = await chrome.storage.local.get(null);
    const keys = Object.keys(all).filter(k => k.startsWith("dmmtImgCache:") || k === "dmmtPageCacheIndex");
    if (keys.length) await chrome.storage.local.remove(keys);
    try {
      const tabId = await activeTabId();
      if (tabId) await chrome.tabs.sendMessage(tabId, { type: "popup-command", action: "clear-current" });
    } catch {
      // 內容腳本未注入的頁面忽略即可。
    }
    span.textContent = `${t("clearCacheDone")} (${keys.length})`;
    updateCacheInfo();
  } catch {
    span.textContent = "⚠";
  }
  setTimeout(() => { span.textContent = t("clearAll"); }, 2000);
});

loadPrefs().then(fillPrefsInputs);
loadRetryPref();
loadDebugPref();
loadCrawlPref();
loadPrefetchPrefs();
loadWheelPref();
loadWheelDirPref();
updateCacheInfo();
initLang().then(() => {
  loadSettings();
  loadState();
});

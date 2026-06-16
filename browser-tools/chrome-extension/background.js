"use strict";

const DEFAULT_SETTINGS = {
  apiBase: "http://127.0.0.1:8501",
  targetLang: "ENG",
  translator: "gemini_2stage",
  llmProvider: "gemini",
  llmApiKey: "",
  llmModel: "",
  llmBaseUrl: "",
  llmSendImage: true,
  onlyTranslateBubbles: false,
  parallelBands: false,
  fontBorder: false,
  fontPath: "",
  // 以下各項對齊網頁 UI（index.html）預設；翻譯時會即時抓 /ui-settings 覆蓋成你在 127.0.0.1:8501 的設定。
  ocrModel: "mocr/gpu",
  inpainter: "lama_large",       // 漫畫微調版，平塗泡泡抹得乾淨；lama_mpe 是舊版會糊出灰霾
  renderTextDirection: "auto",
  fontSizeMinimum: "0",
  concurrency: "5",
  workers: "1",                  // 唯讀同步：伺服器 worker 進程數（網頁 UI 設定）；餵圖上限 = workers × concurrency
  maskDilationOffset: 20,        // 抹字遮罩外擴像素：大蓋殘字但會抹到框/糊邊，小乾淨但會殘字
  inpaintingSize: "2048"
};

const SETTINGS_KEY = "dmmtSyncedSettings";
const RAW_KEY = "dmmtRawSettings";
const LATIN_LANGS = new Set([
  "ENG", "FRA", "DEU", "ESP", "ITA", "PTB", "NLD", "POL",
  "CSY", "HUN", "ROM", "TRK", "VIN", "IND", "FIL"
]);

// 與本機 UI（index.html）一致的服務商預設模型。
const PROVIDER_DEFAULT_MODELS = {
  gemini: "gemini-3.1-flash-lite",
  openai: "gpt-5.1",
  claude: "claude-sonnet-4-6",
  grok: "grok-4.3",
  deepseek: "deepseek-v4-flash",
  qwen: "qwen3-vl-flash",
  kimi: "kimi-k2.6",
  glm: "glm-4.6v",
  mistral: "mistral-large-latest",
  groq: "meta-llama/llama-4-scout-17b-16e-instruct",
  openrouter: "google/gemini-3.5-flash",
  custom: ""
};

function defaultRawSettings() {
  const models = {};
  const apiKeys = {};
  for (const p of Object.keys(PROVIDER_DEFAULT_MODELS)) {
    models[p] = PROVIDER_DEFAULT_MODELS[p];
    apiKeys[p] = "";
  }
  return {
    llmProvider: "gemini",
    models,
    apiKeys,
    llmSendImage: true,
    targetLanguage: "CHT",
    customBaseUrl: "",
    ocrModel: "mocr/gpu",
    inpainter: "lama_large",
    renderTextDirection: "auto",
    maskDilationOffset: 20,
    inpaintingSize: "2048"
  };
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handleMessage(message, sender).then(
    (result) => sendResponse({ ok: true, result }),
    (error) => sendResponse({ ok: false, error: error?.message || String(error) })
  );
  return true;
});

async function handleMessage(message, sender) {
  if (message?.type === "sync-settings") {
    // 來自本機 UI 頁面 localStorage 的原始格式設定，兩種格式都存起來。
    const raw = mergeRaw(defaultRawSettings(), message.settings || {});
    const settings = normalizeUiSettings(raw, message.apiBase || "");
    await chrome.storage.local.set({ [SETTINGS_KEY]: settings, [RAW_KEY]: raw });
    return settings;
  }

  if (message?.type === "get-settings") {
    return loadSettings();
  }

  if (message?.type === "capture-translate") {
    if (!sender.tab?.windowId) {
      throw new Error("找不到目前分頁，無法截圖");
    }
    const settings = await loadSettings();
    const tabDataUrl = await chrome.tabs.captureVisibleTab(sender.tab.windowId, { format: "png" });
    const cropDataUrl = await cropVisibleTabDataUrl(tabDataUrl, message.rect, message.viewport);
    const r = await translateWithRetry(cropDataUrl, settings);
    return {
      image: await blobToDataUrl(r.blob),
      noText: r.noText
    };
  }

  if (message?.type === "capture-crop") {
    if (!sender.tab?.windowId) {
      throw new Error("找不到目前分頁，無法截圖");
    }
    const tabDataUrl = await chrome.tabs.captureVisibleTab(sender.tab.windowId, { format: "png" });
    return {
      image: await cropVisibleTabDataUrl(tabDataUrl, message.rect, message.viewport)
    };
  }

  if (message?.type === "translate-data-url") {
    const settings = await loadSettings();
    _manualActive += 1; // 手動補翻譯插隊：暫停預抓，把伺服器讓給這個請求
    // 分階段進度回報：帶 taskId 時，把伺服器串流回來的每個階段（detection/ocr/translating/
    // inpainting/rendering…）即時推回原分頁，讓進度面板顯示得跟網頁版一樣（沿用 prefetch-progress 模式）。
    const tabId = sender.tab?.id;
    const taskId = message.taskId;
    const onStage = (tabId != null && taskId)
      ? (status, text) => {
          let stage;
          if (status === 3) stage = text ? `queue:${text}` : "queue"; // 排隊位置
          else if (status === 4) stage = "waiting";                   // 等待翻譯器
          else stage = text;                                          // status 1 = 階段字串
          chrome.tabs.sendMessage(tabId, { type: "translate-progress", taskId, stage }).catch(() => {});
        }
      : null;
    try {
      const r = await translateWithRetry(message.image, settings, onStage);
      return {
        image: await blobToDataUrl(r.blob),
        noText: r.noText
      };
    } finally {
      _manualActive -= 1;
    }
  }

  if (message?.type === "fetch-server-settings") {
    return fetchServerSettings(message.apiBase || DEFAULT_SETTINGS.apiBase);
  }

  if (message?.type === "test-connection") {
    return testConnection();
  }

  if (message?.type === "fetch-original-image") {
    return fetchOriginalImage(message.url, message.referer);
  }

  if (message?.type === "prefetch-translate") {
    return prefetchTranslate(message.items || [], message.referer, sender.tab?.id);
  }

  if (message?.type === "abort-all-tasks") {
    abortAllTasks();
    return { aborted: true };
  }

  if (message?.type === "get-settings-view") {
    return getSettingsView();
  }

  if (message?.type === "save-settings") {
    return saveSettings(message.patch || {});
  }

  throw new Error("Unknown message");
}

async function fetchServerSettings(apiBase) {
  const base = String(apiBase || DEFAULT_SETTINGS.apiBase).replace(/\/+$/, "");
  const response = await fetch(`${base}/ui-settings`, { signal: AbortSignal.timeout(4000) });
  if (!response.ok) throw new Error(`伺服器回應 ${response.status}`);
  const raw = await response.json();
  // 空物件（尚未儲存）不覆蓋已有的正確設定。
  if (!raw || Object.keys(raw).length === 0) throw new Error("伺服器尚未儲存設定");
  // 補齊缺漏欄位，避免覆蓋掉本地已編輯的其他服務商設定。
  const merged = mergeRaw(defaultRawSettings(), raw);
  const settings = normalizeUiSettings(merged, base);
  await chrome.storage.local.set({ [SETTINGS_KEY]: settings, [RAW_KEY]: merged });
  return settings;
}

// 把 patch 疊到 base 上（models/apiKeys 為物件需逐鍵合併）。
function mergeRaw(base, patch) {
  const out = { ...base, ...patch };
  out.models = { ...(base.models || {}), ...(patch.models || {}) };
  out.apiKeys = { ...(base.apiKeys || {}), ...(patch.apiKeys || {}) };
  return out;
}

async function loadRawSettings() {
  const stored = await chrome.storage.local.get([RAW_KEY, SETTINGS_KEY]);
  if (stored[RAW_KEY]) return mergeRaw(defaultRawSettings(), stored[RAW_KEY]);
  // 沒有 raw 但有正規化設定（舊版同步）→ 反推回 raw，避免編輯器顯示空白。
  const norm = stored[SETTINGS_KEY];
  const raw = defaultRawSettings();
  if (norm) {
    const p = norm.llmProvider || raw.llmProvider;
    raw.llmProvider = p;
    if (norm.llmModel) raw.models[p] = norm.llmModel;
    if (norm.llmApiKey) raw.apiKeys[p] = norm.llmApiKey;
    if (typeof norm.llmSendImage === "boolean") raw.llmSendImage = norm.llmSendImage;
    if (typeof norm.onlyTranslateBubbles === "boolean") raw.onlyTranslateBubbles = norm.onlyTranslateBubbles;
    if (typeof norm.fontBorder === "boolean") raw.fontBorder = norm.fontBorder;
    if (typeof norm.parallelBands === "boolean") raw.parallelBands = norm.parallelBands;
    if (norm.maskDilationOffset != null) raw.maskDilationOffset = norm.maskDilationOffset;
    if (norm.inpaintingSize != null) raw.inpaintingSize = norm.inpaintingSize;
    if (norm.inpainter) raw.inpainter = norm.inpainter;
    if (norm.ocrModel) raw.ocrModel = norm.ocrModel;
    if (norm.targetLang) raw.targetLanguage = norm.targetLang;
    if (norm.llmBaseUrl) raw.customBaseUrl = norm.llmBaseUrl;
  }
  return raw;
}

// 給 popup（擴充功能自己的私有 UI）用的設定視圖，含實際金鑰以便回填到編輯欄位。
// 金鑰在 popup 預設以密碼遮罩顯示，需點眼睛才顯示明文（與網頁 UI 行為一致）。
async function getSettingsView() {
  const raw = await loadRawSettings();
  const apiKeySet = {};
  for (const p of Object.keys(raw.apiKeys || {})) {
    apiKeySet[p] = Boolean(raw.apiKeys[p]);
  }
  return {
    llmProvider: raw.llmProvider,
    models: raw.models,
    apiKeys: raw.apiKeys,
    apiKeySet,
    llmSendImage: raw.llmSendImage,
    onlyTranslateBubbles: raw.onlyTranslateBubbles,
    fontBorder: raw.fontBorder,
    parallelBands: raw.parallelBands,
    targetLanguage: raw.targetLanguage,
    customBaseUrl: raw.customBaseUrl,
    ocrModel: raw.ocrModel || DEFAULT_SETTINGS.ocrModel,
    inpainter: (raw.inpainter === "lama_mpe" ? "lama_large" : raw.inpainter) || DEFAULT_SETTINGS.inpainter,
    renderTextDirection: raw.renderTextDirection || DEFAULT_SETTINGS.renderTextDirection,
    maskDilationOffset: (raw.maskDilationOffset != null) ? raw.maskDilationOffset : DEFAULT_SETTINGS.maskDilationOffset,
    inpaintingSize: raw.inpaintingSize || DEFAULT_SETTINGS.inpaintingSize,
    providerDefaults: PROVIDER_DEFAULT_MODELS
  };
}

// 儲存 patch：更新本地 raw + normalized，並盡力回寫伺服器 /ui-settings。
async function saveSettings(patch) {
  const raw = await loadRawSettings();
  const provider = patch.llmProvider || raw.llmProvider;
  raw.llmProvider = provider;
  if (typeof patch.model === "string") raw.models[provider] = patch.model;
  // 金鑰留空代表「沿用原本的」，只有非空才覆蓋。
  if (typeof patch.apiKey === "string" && patch.apiKey !== "") raw.apiKeys[provider] = patch.apiKey;
  if (typeof patch.llmSendImage === "boolean") raw.llmSendImage = patch.llmSendImage;
  if (typeof patch.onlyTranslateBubbles === "boolean") raw.onlyTranslateBubbles = patch.onlyTranslateBubbles;
  if (typeof patch.fontBorder === "boolean") raw.fontBorder = patch.fontBorder;
  if (typeof patch.parallelBands === "boolean") raw.parallelBands = patch.parallelBands;
  if (typeof patch.targetLanguage === "string") raw.targetLanguage = patch.targetLanguage;
  if (typeof patch.customBaseUrl === "string") raw.customBaseUrl = patch.customBaseUrl;
  if (typeof patch.ocrModel === "string") raw.ocrModel = patch.ocrModel;
  if (typeof patch.inpainter === "string") raw.inpainter = patch.inpainter;
  if (typeof patch.renderTextDirection === "string") raw.renderTextDirection = patch.renderTextDirection;
  if (patch.maskDilationOffset != null && patch.maskDilationOffset !== "") raw.maskDilationOffset = parseInt(patch.maskDilationOffset);
  if (patch.inpaintingSize != null && patch.inpaintingSize !== "") raw.inpaintingSize = String(patch.inpaintingSize);

  const stored = await chrome.storage.local.get(SETTINGS_KEY);
  const apiBase = stored[SETTINGS_KEY]?.apiBase || DEFAULT_SETTINGS.apiBase;
  const normalized = normalizeUiSettings(raw, apiBase);
  await chrome.storage.local.set({ [SETTINGS_KEY]: normalized, [RAW_KEY]: raw });

  // 盡力回寫伺服器，讓本機 UI 也同步；失敗（伺服器沒開）不影響擴充功能。
  let serverSaved = false;
  try {
    const base = String(apiBase).replace(/\/+$/, "");
    // 回寫整包 raw（含使用者在擴充剛改的 OCR/抹字/排版）。popup 開啟時已先抓伺服器現值
    // 回填，故送出的是「當前或剛改的」值、不會用過時值蓋掉；伺服器端 /ui-settings 亦做合併，
    // 只更新有送的欄位。
    const resp = await fetch(`${base}/ui-settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(raw),
      signal: AbortSignal.timeout(4000)
    });
    serverSaved = resp.ok;
  } catch {
    // ignore
  }
  return { ...await getSettingsView(), serverSaved };
}

async function loadSettings() {
  const stored = await chrome.storage.local.get(SETTINGS_KEY);
  return {
    ...DEFAULT_SETTINGS,
    ...(stored[SETTINGS_KEY] || {})
  };
}

function normalizeUiSettings(raw, apiBase) {
  const provider = raw.llmProvider || DEFAULT_SETTINGS.llmProvider;
  const models = raw.models || {};
  const apiKeys = raw.apiKeys || {};
  // 相容兩種格式：UI 原始格式（targetLanguage / apiKeys[provider]）
  // 和已正規化格式（targetLang / llmApiKey），讓 user_settings.json
  // 無論是哪種來源都能正確讀取。
  return {
    apiBase: apiBase || raw.apiBase || DEFAULT_SETTINGS.apiBase,
    targetLang: raw.targetLanguage || raw.targetLang || DEFAULT_SETTINGS.targetLang,
    translator: raw.translator || DEFAULT_SETTINGS.translator,
    llmProvider: provider,
    llmApiKey: apiKeys[provider] || raw.llmApiKey || "",
    llmModel: models[provider] || raw.llmModel || "",
    llmBaseUrl: raw.customBaseUrl || raw.llmBaseUrl || "",
    llmSendImage: typeof raw.llmSendImage === "boolean" ? raw.llmSendImage : true,
    onlyTranslateBubbles: typeof raw.onlyTranslateBubbles === "boolean" ? raw.onlyTranslateBubbles : false,
    fontBorder: typeof raw.fontBorder === "boolean" ? raw.fontBorder : false,
    parallelBands: typeof raw.parallelBands === "boolean" ? raw.parallelBands : false,
    fontPath: raw.fontPath || "",
    // OCR / 抹字 / 輸出排版：完全跟隨網頁 UI（user_settings.json），不在擴充寫死。
    ocrModel: raw.ocrModel || DEFAULT_SETTINGS.ocrModel,
    inpainter: (raw.inpainter === "lama_mpe" ? "lama_large" : raw.inpainter) || DEFAULT_SETTINGS.inpainter,
    renderTextDirection: raw.renderTextDirection || DEFAULT_SETTINGS.renderTextDirection,
    fontSizeMinimum: raw.fontSizeMinimum || DEFAULT_SETTINGS.fontSizeMinimum,
    concurrency: raw.concurrency || DEFAULT_SETTINGS.concurrency,
    workers: raw.workers || DEFAULT_SETTINGS.workers,   // 唯讀同步自網頁 UI，用來算餵圖上限
    maskDilationOffset: (raw.maskDilationOffset != null) ? raw.maskDilationOffset : DEFAULT_SETTINGS.maskDilationOffset,
    inpaintingSize: raw.inpaintingSize || DEFAULT_SETTINGS.inpaintingSize
  };
}

async function cropVisibleTabDataUrl(dataUrl, rect, viewport) {
  const blob = await dataUrlToBlob(dataUrl);
  const bitmap = await createImageBitmap(blob);
  const scaleX = bitmap.width / Math.max(1, Number(viewport?.width || 1));
  const scaleY = bitmap.height / Math.max(1, Number(viewport?.height || 1));

  const sx = clamp(Math.round(Number(rect.left) * scaleX), 0, bitmap.width);
  const sy = clamp(Math.round(Number(rect.top) * scaleY), 0, bitmap.height);
  const sw = clamp(Math.round(Number(rect.width) * scaleX), 1, bitmap.width - sx);
  const sh = clamp(Math.round(Number(rect.height) * scaleY), 1, bitmap.height - sy);

  const canvas = new OffscreenCanvas(sw, sh);
  const ctx = canvas.getContext("2d");
  ctx.drawImage(bitmap, sx, sy, sw, sh, 0, 0, sw, sh);
  const cropped = await canvas.convertToBlob({ type: "image/png" });
  return blobToDataUrl(cropped);
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

async function dataUrlToBlob(dataUrl) {
  const response = await fetch(dataUrl);
  return response.blob();
}

async function blobToDataUrl(blob) {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  const chunkSize = 0x8000;
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }
  return `data:${blob.type || "image/png"};base64,${btoa(binary)}`;
}

function buildConfig(settings) {
  const targetLang = String(settings.targetLang || "ENG").trim().toUpperCase();
  const isLatin = LATIN_LANGS.has(targetLang);
  return {
    translator: {
      translator: settings.translator || "gemini_2stage",
      target_lang: targetLang,
      llm_provider: settings.llmProvider || "gemini",
      llm_api_key: settings.llmApiKey || null,
      llm_model: settings.llmModel || null,
      llm_base_url: settings.llmProvider === "custom" ? (settings.llmBaseUrl || null) : null,
      llm_send_image: Boolean(settings.llmSendImage),
      parallel_bands: Boolean(settings.parallelBands),
      post_check_max_retry_attempts: 0,
      enable_post_translation_check: false
    },
    translate_only_in_bubbles: Boolean(settings.onlyTranslateBubbles),
    detector: {
      detector: "default",
      detection_size: 2048,
      unclip_ratio: 2.3,
      text_threshold: 0.35,
      box_threshold: 0.35,
      det_invert: false,
      det_auto_rotate: false,
      det_rotate: false,
      det_gamma_correct: false
    },
    ocr: {
      ocr: (settings.ocrModel || "mocr/gpu").split("/")[0],
      paddle_lang: (settings.ocrModel || "").startsWith("paddle/") ? ((settings.ocrModel.split("/")[1]) || "auto") : "korean",
      ocr_device: ["cpu", "gpu"].includes((settings.ocrModel || "").split("/").pop()) ? (settings.ocrModel || "").split("/").pop() : "auto",
      use_mocr_merge: false,
      min_text_length: 1,
      prob: 0.08,
      ignore_bubble: 0
    },
    inpainter: {
      inpainter: settings.inpainter || "lama_large",
      inpainting_size: parseInt(settings.inpaintingSize) || 2048,
      inpainting_precision: "bf16"
    },
    render: {
      renderer: "manga2eng",
      alignment: "auto",
      disable_font_border: !settings.fontBorder,
      direction: (settings.renderTextDirection && settings.renderTextDirection !== "auto") ? settings.renderTextDirection : (isLatin ? "horizontal" : "auto"),
      bubble_layout_english: isLatin,
      font_path: settings.fontPath || null,
      uppercase: false,
      lowercase: false,
      font_color: null,
      line_spacing: 1.0,
      letter_spacing: 1.0,
      font_size: null,
      auto_rotate_symbols: true,
      rtl: true,
      layout_mode: "balloon_fill",
      max_font_size: 0,
      font_scale_ratio: 1.0,
      disable_auto_wrap: false,
      center_text_in_bubble: true,
      optimize_line_breaks: false,
      check_br_and_retry: false,
      strict_smart_scaling: false,
      font_size_offset: 0,
      font_size_minimum: 0,
      font_size_min_ratio: ((parseFloat(settings.fontSizeMinimum) || 0) <= 1) ? (parseFloat(settings.fontSizeMinimum) || 0) : 0,
      no_hyphenation: true,
      stroke_width: 0.07,
      enable_template_alignment: false,
      paste_mask_dilation_pixels: 10,
      ai_renderer_concurrency: 1
    },
    mask_dilation_offset: (settings.maskDilationOffset != null && settings.maskDilationOffset !== "") ? parseInt(settings.maskDilationOffset) : 20
  };
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// 「爬蟲」抓原圖：背景 fetch 可繞過 CORS（canvas 跨域被污染讀不到時的解法）。
// 對防盜圖站（pixiv 等會檢查 Referer）用 declarativeNetRequest 暫時偽造 Referer 才抓得到。
const FETCH_IMG_RULE_ID = 9911;
async function fetchOriginalImage(url, referer) {
  if (!url) throw new Error("缺少圖片網址");
  // 必須先取得「該圖片網域」的主機權限（使用者在 popup 對目前網站授權「原圖抓取」）。
  let originPattern = "";
  try { const u = new URL(url); originPattern = `${u.protocol}//${u.hostname}/*`; } catch {}
  const granted = originPattern
    ? await chrome.permissions.contains({ origins: [originPattern] }).catch(() => false)
    : false;
  if (!granted) throw new Error("尚未授權原圖抓取（請在目前網站開啟「原圖抓取」）");

  let host = "";
  try { host = new URL(url).hostname; } catch {}

  let ruleAdded = false;
  try {
    if (referer && host) {
      await chrome.declarativeNetRequest.updateSessionRules({
        removeRuleIds: [FETCH_IMG_RULE_ID],
        addRules: [{
          id: FETCH_IMG_RULE_ID,
          priority: 1,
          action: {
            type: "modifyHeaders",
            requestHeaders: [{ header: "referer", operation: "set", value: referer }]
          },
          condition: {
            // 比對該圖片網域的請求（pixiv 的 i.pximg.net 等），這段期間內把 Referer 設成來源頁。
            requestDomains: [host],
            resourceTypes: ["xmlhttprequest"]
          }
        }]
      });
      ruleAdded = true;
    }
    const resp = await fetch(url, { credentials: "include" });
    if (!resp.ok) throw new Error(`圖片回應 ${resp.status}`);
    const dataUrl = await blobToDataUrl(await resp.blob());
    return { image: dataUrl };
  } finally {
    if (ruleAdded) {
      try { await chrome.declarativeNetRequest.updateSessionRules({ removeRuleIds: [FETCH_IMG_RULE_ID] }); } catch {}
    }
  }
}

const AUTO_RETRY_KEY = "dmmtAutoRetry";

// 翻譯失敗自動重試（可由 popup 勾選關閉，預設開啟）。逾時/網路抖動再試 2 次。
async function translateWithRetry(dataUrl, settings, onStage) {
  const stored = await chrome.storage.local.get(AUTO_RETRY_KEY);
  const enabled = stored[AUTO_RETRY_KEY] !== false; // 預設開啟
  const maxAttempts = enabled ? 3 : 1;
  let lastErr;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await translateImageDataUrl(dataUrl, settings, onStage);
    } catch (e) {
      lastErr = e;
      // 使用者中止 → 立即停止，不重試。
      if (e?.name === "AbortError") throw e;
      // 金鑰/參數錯誤重試也沒用，直接拋出。
      if (/API 4\d\d|invalid|api[_\s-]?key|unauthor/i.test(e?.message || "")) throw e;
      if (attempt < maxAttempts) await sleep(700 * attempt);
    }
  }
  throw lastErr;
}

// 連續翻譯預抓：依序抓後面幾頁的圖、翻譯、寫進快取（沿用 content.js 的快取格式）。
// 已快取的跳過；遇到 404（沒有下一頁）就停止後續預抓。需使用者已授權「原圖抓取」。
const PREFETCH_INDEX_KEY = "dmmtPageCacheIndex";
const PREFETCH_MAX = 120;
const _prefetchInFlight = new Set();

// 中止機制：開關關掉時把進行中的翻譯請求真的 abort，並讓預抓迴圈停止。
let _abortGen = 0;
const _activeTranslateAborts = new Set();
function abortAllTasks() {
  _abortGen++;
  for (const c of _activeTranslateAborts) { try { c.abort(); } catch {} }
  _activeTranslateAborts.clear();
  _prefetchInFlight.clear();
  _pfActive = 0; _pfDone = 0; _pfTotal = 0;
}

// 頁碼翻譯預抓進度（跨多次翻頁累計；整輪全部閒置後才重新計數），供泡泡 tooltip 顯示 done/total。
let _pfActive = 0;
let _pfDone = 0;
let _pfTotal = 0;
let _manualActive = 0; // 手動補翻譯進行中的數量；>0 時預抓暫停讓出伺服器（手動插隊到最上面）
function notifyPrefetchProgress(tabId) {
  if (tabId == null) return;
  chrome.tabs.sendMessage(tabId, { type: "prefetch-progress", done: _pfDone, total: _pfTotal }).catch(() => {});
}

async function prefetchTranslate(items, referer, tabId) {
  const settings = await loadSettings();
  // 餵圖上限 = 伺服器 slot 總數 = worker 進程數 × 並發數（每個 worker 各註冊「並發數」個 slot）。
  // 只用 concurrency 的話，開了多 worker 時會餵不滿、多出來的 slot 空等（使用者回報的「等待處理中」）。
  const baseConc = Math.max(1, Math.min(parseInt(settings.concurrency) || 5, 16));
  const workers = Math.max(1, Math.min(parseInt(settings.workers) || 1, 4));
  const conc = baseConc * workers;
  // Over-send：實際同時送 conc+2，讓伺服器佇列永遠有下一張等著 → GPU 一放鎖立刻有活，不必等
  // client round-trip。對齊 SDMDCBOT「pipeline 深度 + 2 buffer」的餵滿策略（client.py:77）。
  const inflightCap = Math.min(conc + 2, 66);
  let lastPage = 0; // 已預翻到的最遠頁碼（含這次新翻的）
  let prevOrig = null; // 上一張抓到的原圖，用來偵測「站一直回同一張＝已到底」
  const myGen = _abortGen;
  const valid = items.filter((it) => it?.cacheKey && it?.imageUrl);
  if (_pfActive === 0) { _pfDone = 0; _pfTotal = 0; } // 上一輪已全部結束 → 重新計數
  _pfActive += 1;
  _pfTotal += valid.length;
  notifyPrefetchProgress(tabId);

  // 並發翻譯池：抓圖維持「序列」（fetchOriginalImage 共用 referer 偽造的 session rule，並行會互踩；
  // 且重複頁偵測 prevOrig 需順序），但「翻譯」（真正的瓶頸）並發。_sem 限制最多 inflightCap 個翻譯
  // 同時送出，並對抓圖迴圈形成背壓（每張抓圖前先取槽 → 最多領先 inflightCap 張，不會吃爆記憶體）。
  let _semActive = 0;
  const _semWaiters = [];
  const _semAcquire = () => (_semActive < inflightCap
    ? (_semActive++, Promise.resolve())
    : new Promise((r) => _semWaiters.push(r)));
  const _semRelease = () => {
    _semActive--;
    const w = _semWaiters.shift();
    if (w) { _semActive++; w(); }
  };
  const _pending = []; // 進行中的翻譯 promise

  try {
    for (let i = 0; i < valid.length; i++) {
      if (_abortGen !== myGen) break; // 使用者中止 → 停止後續預抓
      // 手動補翻譯插隊：有手動翻譯進行中時暫停預抓，等它做完再繼續（不搶伺服器）。
      while (_manualActive > 0 && _abortGen === myGen) {
        await new Promise((r) => setTimeout(r, 120));
      }
      if (_abortGen !== myGen) break;
      const item = valid[i];
      // 先同步搶占 in-flight，避免兩批同時搶同一張重複翻。
      if (_prefetchInFlight.has(item.cacheKey)) { _pfDone += 1; notifyPrefetchProgress(tabId); continue; }
      _prefetchInFlight.add(item.cacheKey);
      // 取並發槽（背壓）：conc 個翻譯都在跑時，這裡會等到有翻譯完成釋放槽才繼續抓下一張。
      await _semAcquire();
      if (_abortGen !== myGen) { _prefetchInFlight.delete(item.cacheKey); _semRelease(); break; }
      let stop = false, fired = false;
      try {
        const existing = await chrome.storage.local.get(item.cacheKey);
        if (existing[item.cacheKey]) continue; // 已翻過（finally 釋放槽 + in-flight + done）
        const fetched = await fetchOriginalImage(item.imageUrl, referer);
        // 重複頁偵測：有些站對「不存在的頁」不回 404，而一直回同一張 → 已到底，停止後續預抓。
        if (prevOrig !== null && fetched.image === prevOrig) {
          stop = true;
        } else {
          prevOrig = fetched.image;
          // 非同步翻譯：沿用上面取得的槽，完成時釋放槽 + in-flight + done（不在此 await）。
          fired = true;
          _pending.push((async () => {
            try {
              // 手動補翻譯插隊中：尚未送出的預抓先讓位（已送出的無法收回），把伺服器讓給手動。
              while (_manualActive > 0 && _abortGen === myGen) {
                await new Promise((r) => setTimeout(r, 120));
              }
              if (_abortGen !== myGen) return; // 已中止 → 不再送出（finally 仍會收尾）
              const r = await translateWithRetry(fetched.image, settings);
              if (item.page) lastPage = Math.max(lastPage, item.page);
              const translated = await blobToDataUrl(r.blob);
              await storePrefetchCache(item.cacheKey, { src: item.imageUrl, image: translated });
            } catch (e) {
              // 翻譯失敗略過
            } finally {
              _prefetchInFlight.delete(item.cacheKey);
              _pfDone += 1;
              notifyPrefetchProgress(tabId);
              _semRelease();
            }
          })());
        }
      } catch (e) {
        // 404 = 沒有下一頁了，停止後續預抓；其他錯誤也停（避免空轉）。
        if (/40\d|沒有|not.?found/i.test(e?.message || "")) stop = true;
      } finally {
        // 沒有 fire 翻譯的（已翻快取／重複頁／404／錯誤）：在此釋放槽 + in-flight + done。
        if (!fired) {
          _prefetchInFlight.delete(item.cacheKey);
          _pfDone += 1;
          notifyPrefetchProgress(tabId);
          _semRelease();
        }
      }
      if (stop) { _pfTotal -= (valid.length - 1 - i); break; } // 後面的頁不存在，扣掉還沒做的
    }
    await Promise.all(_pending); // 等所有已 fire 的並發翻譯收尾
  } finally {
    _pfActive -= 1;
    // 整輪預抓全部結束 → 帶 idle 旗標讓前端把進度面板收尾。不能只靠 done==total，因為遇 404/
    // 重複頁會砍 _pfTotal，done 可能永遠不等於 total，面板就會卡在最後的數字（如 27/29）。
    if (_pfActive <= 0) {
      _pfActive = 0;
      chrome.tabs.sendMessage(tabId, { type: "prefetch-progress", done: _pfDone, total: _pfTotal, idle: true }).catch(() => {});
    } else {
      notifyPrefetchProgress(tabId);
    }
  }
  return { prefetched: _pfDone, lastPage };
}

async function storePrefetchCache(key, entry) {
  // 預抓與 content.js 翻譯快取共用同一索引（dmmtPageCacheIndex）；上限統一讀使用者自訂的
  // dmmtCacheMax（popup「快取上限」），未設則沿用 PREFETCH_MAX 預設，兩邊一致不再互相打架。
  const stored = await chrome.storage.local.get([PREFETCH_INDEX_KEY, "dmmtCacheMax"]);
  let index = Array.isArray(stored[PREFETCH_INDEX_KEY]) ? stored[PREFETCH_INDEX_KEY] : [];
  const cn = parseInt(stored.dmmtCacheMax);
  const maxN = (cn >= 1 && cn <= 9999) ? cn : PREFETCH_MAX;
  index = index.filter((e) => e.key !== key);
  index.push({ key, ts: Date.now() });
  const evicted = index.length > maxN ? index.splice(0, index.length - maxN) : [];
  await chrome.storage.local.set({ [key]: entry, [PREFETCH_INDEX_KEY]: index });
  if (evicted.length) await chrome.storage.local.remove(evicted.map((e) => e.key));
}

// 測試連接：用一張含日文的小圖實際打一次翻譯流程，回報成功或錯誤訊息。
async function testConnection() {
  const settings = await loadSettings();
  try {
    const canvas = new OffscreenCanvas(96, 64);
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, 96, 64);
    ctx.fillStyle = "#000000";
    ctx.font = "24px sans-serif";
    ctx.fillText("テスト", 6, 40);
    const blob = await canvas.convertToBlob({ type: "image/png" });
    const tiny = await blobToDataUrl(blob);
    await translateImageDataUrl(tiny, settings);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e?.message || String(e) };
  }
}

async function translateImageDataUrl(dataUrl, settings, onStage) {
  const apiBase = String(settings.apiBase || DEFAULT_SETTINGS.apiBase).replace(/\/+$/, "");
  // 永遠以 http://127.0.0.1:8501 的最新設定為準：OCR / 抹字 / 排版 / 翻譯 / 目標語言全部跟網頁 UI
  // 即時同步，不在擴充寫死。取不到時（伺服器未存設定或暫時離線）才沿用本地快取的 settings。
  try {
    const fresh = await fetchServerSettings(apiBase);
    settings = { ...settings, ...fresh };
  } catch (_) { /* 沿用傳入的 settings */ }
  // 必須用 /translate/image/stream：它會把「真正的成品圖」直接放進串流回傳。
  // 不能用網頁的 /web 端點——/web 是「佔位符優化」，只把成品存到伺服器硬碟（final.png）、
  // 串流裡只送一張 1×1 白色佔位圖，真正的圖要另外去抓檔案。擴充功能沒抓檔案，就會得到全白圖。
  const controller = new AbortController();
  _activeTranslateAborts.add(controller);
  try {
    const response = await fetch(`${apiBase}/translate/image/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        image: dataUrl,
        config: buildConfig(settings)
      }),
      signal: controller.signal
    });

    if (!response.ok) {
      throw new Error(`API ${response.status}`);
    }
    return await readTranslationStream(response, onStage);
  } finally {
    _activeTranslateAborts.delete(controller);
  }
}

function concatU8(a, b) {
  if (!a.length) return b;
  if (!b.length) return a;
  const out = new Uint8Array(a.length + b.length);
  out.set(a, 0);
  out.set(b, a.length);
  return out;
}

// 邊收邊解析串流：伺服器每完成一個階段就送一個 status-1 文字框（detection/ocr/translating/
// inpainting/rendering…）。舊版用 response.arrayBuffer() 整包收完才解析 → 中間階段全被丟掉，
// 擴充只看得到「處理中」。改成 response.body.getReader() 逐塊解析（比照網頁 UI processChunk），
// 每解到一個階段就即時 onStage 回報，最後一張 status-0 才是成品圖。
async function readTranslationStream(response, onStage) {
  const reader = response.body.getReader();
  let buf = new Uint8Array(0);
  let lastProgress = "";
  let lastImage = null;
  let noText = false; // 伺服器偵測不到文字會送 skip-no-text / skip-no-regions 進度訊息
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    if (value && value.length) buf = concatU8(buf, value);
    let offset = 0;
    while (offset + 5 <= buf.length) {
      const status = buf[offset];
      const size = new DataView(buf.buffer, buf.byteOffset + offset + 1, 4).getUint32(0, false);
      if (offset + 5 + size > buf.length) break; // 這一框還沒收完，等下一塊
      const data = buf.slice(offset + 5, offset + 5 + size);
      offset += 5 + size;
      if (status === 0) {
        lastImage = new Blob([data], { type: detectImageMime(data) });
      } else if (status === 1 || status === 3 || status === 4) {
        lastProgress = decodeUtf8(data);
        if (/skip-no-text|skip-no-regions/i.test(lastProgress)) noText = true;
        if (onStage) { try { onStage(status, lastProgress); } catch {} }
      } else if (status === 2) {
        throw new Error(decodeUtf8(data) || "翻譯失敗");
      }
    }
    if (offset > 0) buf = offset >= buf.length ? new Uint8Array(0) : buf.slice(offset);
  }
  if (lastImage) return { blob: lastImage, noText };
  throw new Error(lastProgress ? `翻譯未完成：${lastProgress}` : "API 沒有回傳翻譯圖片");
}

function detectImageMime(bytes) {
  if (bytes.length >= 8 && bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47) {
    return "image/png";
  }
  if (bytes.length >= 3 && bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) {
    return "image/jpeg";
  }
  if (bytes.length >= 12 && bytes[0] === 0x52 && bytes[1] === 0x49 && bytes[2] === 0x46 && bytes[3] === 0x46) {
    return "image/webp";
  }
  return "image/png";
}

function decodeUtf8(bytes) {
  try {
    return new TextDecoder("utf-8").decode(bytes);
  } catch {
    return "";
  }
}

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
  serverSlots: 0,                 // 伺服器實際註冊 slot 數；有值時優先用它，避免本地快取低估
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
    serverSlots: raw.serverSlots || DEFAULT_SETTINGS.serverSlots,
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
      inpainting_precision: "bf16"  // bf16 autocast 是 lama 建議路徑（權重仍 fp32、不會變暗），快又省顯存。實測 fp32 也一樣髒 → 髒不是精度問題（真因是 flat_fill banding + 長條寬度壓垮，已於伺服器端修）
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
// 對防盜圖站（pixiv 等會檢查 Referer）用 declarativeNetRequest 偽造 Referer 才抓得到。
// 並行抓圖：同一 host 共用「一條」referer rule + 引用計數，不再每張抓完就裝/拆——以前固定 rule id 9911
// 每抓一張就 add/remove 一次，並行會互踩同一條 rule（這正是過去抓圖只能序列的主因）。現在第一張抓圖
// 裝 rule、最後一張抓完才拆，期間同 host 的並行下載全部共用同一條。
const _refererRules = new Map(); // host -> { count, ruleId, referer, ready }
let _refererRuleSeq = 9911;
async function _acquireRefererRule(host, referer) {
  if (!host || !referer) return null;
  let e = _refererRules.get(host);
  if (!e) {
    const ruleId = _refererRuleSeq++;
    if (_refererRuleSeq > 19000) _refererRuleSeq = 9911; // 循環用，避免 id 無限長
    e = { count: 0, ruleId, referer, ready: null };
    _refererRules.set(host, e); // 同步先佔位，避免兩個並發 acquire 同時 !e 而重複建 rule（id leak）
    e.ready = chrome.declarativeNetRequest.updateSessionRules({
      removeRuleIds: [ruleId],
      addRules: [{
        id: ruleId, priority: 1,
        action: { type: "modifyHeaders", requestHeaders: [{ header: "referer", operation: "set", value: referer }] },
        condition: { requestDomains: [host], resourceTypes: ["xmlhttprequest"] }
      }]
    }).catch(() => {});
  }
  e.count++;
  await e.ready; // 等 rule 真的裝好再回，後續 fetch 才帶得到偽造 referer
  return e;
}
async function _releaseRefererRule(host) {
  const e = _refererRules.get(host);
  if (!e) return;
  e.count--;
  if (e.count <= 0) {
    _refererRules.delete(host);
    try { await chrome.declarativeNetRequest.updateSessionRules({ removeRuleIds: [e.ruleId] }); } catch {}
  }
}
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

  let acquired = null;
  try {
    if (referer && host) acquired = await _acquireRefererRule(host, referer);
    const resp = await fetch(url, { credentials: "include" });
    if (!resp.ok) throw new Error(`圖片回應 ${resp.status}`);
    const dataUrl = await blobToDataUrl(await resp.blob());
    return { image: dataUrl };
  } finally {
    if (acquired && host) await _releaseRefererRule(host);
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
const IMG_CACHE_PREFIX = "dmmtImgCache:";

function absoluteFrom(baseUrl, value) {
  try { return new URL(String(value || "").trim(), baseUrl).href; } catch { return ""; }
}

function normalizedImageUrl(src) {
  const clean = String(src || "").split(/[?#]/)[0];
  try {
    const u = new URL(clean);
    const host = /\.nhentai\.net$/i.test(u.host)
      ? u.host.replace(/^(?:[a-z]+\d+|i)\./i, "")
      : u.host.replace(/^[a-z]+\d+\./i, "");
    return u.protocol + "//" + host + u.pathname;
  } catch {
    return clean;
  }
}

function imgCacheKey(src) {
  return IMG_CACHE_PREFIX + normalizedImageUrl(src);
}

function decodeHtmlAttr(value) {
  return String(value || "")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, "\"")
    .replace(/&#39;|&apos;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

function srcsetBest(value) {
  const parts = String(value || "").split(",").map((p) => p.trim()).filter(Boolean);
  if (!parts.length) return "";
  return parts[parts.length - 1].split(/\s+/)[0] || "";
}

function imageCandidateScore(url, attrName) {
  const lower = String(url || "").toLowerCase();
  if (!/^https?:\/\//.test(lower)) return -1000;
  if (/\b(logo|icon|avatar|banner|ads?|sprite|thumb|thumbnail|cover)\b/.test(lower)) return -80;
  let score = 0;
  if (/\.(?:avif|webp|jpe?g|png)(?:$|[?#])/.test(lower)) score += 40;
  if (lower.includes("/galleries/")) score += 35;
  if (/\/galleries\/\d+\/\d+\.(?:avif|webp|jpe?g|png)(?:$|[?#])/.test(lower)) score += 45;
  if (/\b(page|pages|manga|chapter|comic|image|img|viewer|reader)\b/.test(lower)) score += 20;
  if (/data-original|data-src|data-lazy|srcset/i.test(attrName || "")) score += 12;
  if (lower.includes("/uploads/") || lower.includes("/media/") || lower.includes("/images/")) score += 8;
  return score;
}

async function fetchReaderPageImageUrl(pageUrl, referer, imageSlot = -1) {
  if (!pageUrl) throw new Error("Missing page URL");
  let host = "";
  try { host = new URL(pageUrl).hostname; } catch {}
  let acquired = null;
  try {
    if (referer && host) acquired = await _acquireRefererRule(host, referer);
    const resp = await fetch(pageUrl, {
      credentials: "include",
      headers: { "Accept": "text/html,application/xhtml+xml" }
    });
    if (!resp.ok) throw new Error(`Page HTTP ${resp.status}`);
    const html = await resp.text();
    const candidates = [];

    for (const m of html.matchAll(/<meta\b[^>]*(?:property|name)=["'](?:og:image|twitter:image)["'][^>]*content=["']([^"']+)["'][^>]*>/gi)) {
      candidates.push({ url: absoluteFrom(pageUrl, decodeHtmlAttr(m[1])), attr: "meta", dom: false });
    }
    for (const tag of html.matchAll(/<(?:img|source)\b[^>]*>/gi)) {
      const text = tag[0];
      for (const attr of ["data-original", "data-src", "data-lazy-src", "data-url", "data-cfsrc", "src"]) {
        const m = text.match(new RegExp(`\\b${attr}=["']([^"']+)["']`, "i"));
        if (m) candidates.push({ url: absoluteFrom(pageUrl, decodeHtmlAttr(m[1])), attr, dom: true });
      }
      const ss = text.match(/\bsrcset=["']([^"']+)["']/i);
      if (ss) candidates.push({ url: absoluteFrom(pageUrl, decodeHtmlAttr(srcsetBest(ss[1]))), attr: "srcset", dom: true });
    }

    const seen = new Set();
    const ranked = candidates
      .filter((c) => c.url && !seen.has(c.url) && seen.add(c.url))
      .map((c, idx) => ({ ...c, idx, score: imageCandidateScore(c.url, c.attr) }))
      .filter((c) => c.score >= 0)
      .sort((a, b) => (b.score - a.score) || (a.idx - b.idx));
    if (!ranked.length) throw new Error("No page image found");
    const domRanked = ranked.filter((c) => c.dom).sort((a, b) => a.idx - b.idx);
    if (imageSlot >= 0 && imageSlot < domRanked.length) return domRanked[imageSlot].url;
    return ranked[0].url;
  } finally {
    if (acquired && host) await _releaseRefererRule(host);
  }
}

// 中止機制：開關關掉時把進行中的翻譯請求真的 abort，並讓預抓迴圈停止。
let _abortGen = 0;
const _activeTranslateAborts = new Set();
function abortAllTasks() {
  _abortGen++;
  for (const c of _activeTranslateAborts) { try { c.abort(); } catch {} }
  _activeTranslateAborts.clear();
  _prefetchInFlight.clear();
  _pfActive = 0; _pfDone = 0; _pfTotal = 0; _pfCurrentPage = 0; _pfCrawled = 0; _pfPlanned = 0;
}

// 頁碼翻譯預抓進度（跨多次翻頁累計；整輪全部閒置後才重新計數），供泡泡 tooltip 顯示 done/total。
let _pfActive = 0;
let _pfDone = 0;
let _pfTotal = 0;
let _pfCurrentPage = 0;
let _pfCrawled = 0;
let _pfPlanned = 0;
let _manualActive = 0; // 手動補翻譯進行中的數量；>0 時預抓暫停讓出伺服器（手動插隊到最上面）
function notifyPrefetchProgress(tabId) {
  if (tabId == null) return;
  chrome.tabs.sendMessage(tabId, {
    type: "prefetch-progress",
    done: _pfDone,
    total: Math.max(_pfCrawled, _pfDone),
    crawled: _pfCrawled,
    planned: _pfPlanned,
    currentPage: _pfCurrentPage
  }).catch(() => {});
}

// 每頁一列的即時進度（縮圖＋階段徽章），讓頁碼翻譯面板顯示得跟整頁翻譯一樣。
// page 當列 key；stage=null 不動徽章（只送縮圖）；done=true 收尾移除該列。
function notifyPrefetchPage(tabId, page, stage, thumb, done) {
  if (tabId == null || !page) return;
  const msg = { type: "prefetch-page", page };
  if (stage != null) msg.stage = stage;
  if (thumb) msg.thumb = thumb;
  if (done) msg.done = true;
  chrome.tabs.sendMessage(tabId, msg).catch(() => {});
}

// 把原圖縮成小縮圖（webp，預設寬 96）→ 面板那一列顯示；縮過再送，messaging 才不會被整張原圖塞爆。
async function makeThumbDataUrl(dataUrl, maxW = 96) {
  try {
    const blob = await (await fetch(dataUrl)).blob();
    const bmp = await createImageBitmap(blob);
    const scale = Math.min(1, maxW / (bmp.width || maxW));
    const w = Math.max(1, Math.round((bmp.width || maxW) * scale));
    const h = Math.max(1, Math.round((bmp.height || maxW) * scale));
    const canvas = new OffscreenCanvas(w, h);
    canvas.getContext("2d").drawImage(bmp, 0, 0, w, h);
    bmp.close?.();
    return await blobToDataUrl(await canvas.convertToBlob({ type: "image/webp", quality: 0.6 }));
  } catch { return ""; }
}

async function prefetchTranslate(items, referer, tabId) {
  let settings = await loadSettings();
  try {
    settings = { ...settings, ...await fetchServerSettings(settings.apiBase || DEFAULT_SETTINGS.apiBase) };
  } catch (_) {}
  // 餵圖上限 = 伺服器 slot 總數 = worker 進程數 × 並發數（每個 worker 各註冊「並發數」個 slot）。
  // 只用 concurrency 的話，開了多 worker 時會餵不滿、多出來的 slot 空等（使用者回報的「等待處理中」）。
  const baseConc = Math.max(1, Math.min(parseInt(settings.concurrency) || 5, 16));
  const workers = Math.max(1, Math.min(parseInt(settings.workers) || 1, 4));
  const serverSlots = Math.max(0, Math.min(parseInt(settings.serverSlots) || 0, 64));
  const conc = serverSlots || (baseConc * workers);
  // Over-send：實際同時送 conc+2，讓伺服器佇列永遠有下一張等著 → GPU 一放鎖立刻有活，不必等
  // client round-trip。對齊 SDMDCBOT「pipeline 深度 + 2 buffer」的餵滿策略（client.py:77）。
  const inflightCap = Math.min(conc + 2, 66);
  let lastPage = 0; // 已預翻到的最遠頁碼（含這次新翻的）
  const myGen = _abortGen;
  const valid = items.filter((it) => (it?.cacheKey && it?.imageUrl) || it?.pageUrl);
  if (_pfActive === 0) { _pfDone = 0; _pfTotal = 0; _pfCrawled = 0; _pfCurrentPage = 0; _pfPlanned = 0; } // 上一輪已全部結束 → 重新計數
  _pfActive += 1;
  _pfTotal += valid.length;
  _pfPlanned += valid.length;
  notifyPrefetchProgress(tabId);

  // 並發池：「抓圖 + 翻譯」整包並發（以前抓圖在迴圈內 await ＝序列瓶頸，翻譯 worker 餓著等圖）。
  // fetchOriginalImage 已改成 per-host 共用 referer rule，可安全並行。_sem 限制最多 inflightCap 個
  // 工作（下載或翻譯）同時進行，並對排頁迴圈形成背壓（最多領先 inflightCap 張，不會吃爆記憶體）。
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

  // 偵測「站一直回同一張原圖＝已到底」：並行抓圖無法用「上一張」比對，改存指紋集合
  // （長度+頭尾片段，足以分辨不同圖、又不必存整張 base64 吃記憶體）。命中＝重複頁 → 停排後面。
  const _seenFp = new Set();
  const _fp = (img) => img ? (img.length + ":" + img.slice(0, 64) + ":" + img.slice(-64)) : "";
  let stop = false;          // 偵測到 404 / 重複頁 → 不再排後面的頁（已排出去的並行工作照常收尾）
  let brokeAt = valid.length;

  try {
    for (let i = 0; i < valid.length; i++) {
      if (_abortGen !== myGen || stop) { brokeAt = i; break; }
      // 手動補翻譯插隊：有手動翻譯進行中時暫停「排新頁」，等它做完再繼續（不搶伺服器）。
      while (_manualActive > 0 && _abortGen === myGen) {
        await new Promise((r) => setTimeout(r, 120));
      }
      if (_abortGen !== myGen || stop) { brokeAt = i; break; }
      const item = valid[i];
      const page = item.page || 0;
      if (page) { _pfCurrentPage = Math.max(_pfCurrentPage, page); }
      // 取並發槽要在「爬圖」之前 → 連爬 HTML 解圖網址也並行（這次提速核心：以前爬圖在排程迴圈裡
      // 序列 await，一頁一頁爬，GPU 翻譯 worker 餓著等爬蟲餵圖）。背壓：conc+2 個工作都在跑時，
      // 這裡擋到有一個收尾釋放槽才排下一頁，最多領先 inflightCap 頁，不會吃爆記憶體或狂爬到底之外。
      await _semAcquire();
      if (_abortGen !== myGen || stop) { _semRelease(); brokeAt = i; break; }
      // 「爬圖 + 下載 + 翻譯」整包進並發工作；每頁的階段/縮圖即時回報該列徽章。
      _pending.push((async () => {
        let claimedKey = "";
        try {
          // 1) reader 站：取得這頁的真正圖網址。圖檔名連號的站（nhentai 等）content 會附 guessImageUrl
          //    → 先直接用推算的圖網址（免開 HTML，省一次往返）；下載階段猜錯(404)再退回爬 HTML。
          //    沒附 guess 的站照舊開 HTML 解圖。圖網址可直接推算（無 pageUrl）的站跳過整步。
          let guessed = false;
          if (item.pageUrl) {
            if (item.guessImageUrl) {
              item.imageUrl = item.guessImageUrl;
              guessed = true;
            } else {
              notifyPrefetchPage(tabId, page, "crawl");
              try {
                item.imageUrl = await fetchReaderPageImageUrl(item.pageUrl, referer, Number(item.imageSlot));
              } catch (e) {
                if (item.fallbackImageUrl) item.imageUrl = item.fallbackImageUrl;
                else { stop = true; return; } // 爬不到下一頁＝到底，標記停排後面
              }
            }
            item.cacheKey = imgCacheKey(item.imageUrl);
          }
          if (!item.cacheKey || !item.imageUrl) return;
          _pfCrawled += 1; notifyPrefetchProgress(tabId);
          // 2) 同步搶占 in-flight，避免兩批同時搶同一張重複翻。
          if (_prefetchInFlight.has(item.cacheKey)) return;
          _prefetchInFlight.add(item.cacheKey); claimedKey = item.cacheKey;
          // 已翻過就跳過（頁碼不會亂：每頁用自己解析出的圖網址當 key，捲到那頁時用網址比對套上）。
          const existing = await chrome.storage.local.get(item.cacheKey);
          if (existing[item.cacheKey]) { if (page) lastPage = Math.max(lastPage, page); return; }
          // 手動補翻譯插隊中：尚未送出的先讓位，把伺服器讓給手動。
          while (_manualActive > 0 && _abortGen === myGen) {
            await new Promise((r) => setTimeout(r, 120));
          }
          if (_abortGen !== myGen) return;
          // 3) 下載原圖（並行）。
          notifyPrefetchPage(tabId, page, "download");
          let fetched;
          try {
            fetched = await fetchOriginalImage(item.imageUrl, item.pageUrl || referer);
          } catch (e) {
            // 猜的圖網址 404（混副檔名/換 CDN 那幾頁）→ 退回爬該頁 HTML 找真圖，再下載一次。
            if (guessed && item.pageUrl) {
              notifyPrefetchPage(tabId, page, "crawl");
              try {
                item.imageUrl = await fetchReaderPageImageUrl(item.pageUrl, referer, Number(item.imageSlot));
              } catch (e2) { stop = true; return; }
              item.cacheKey = imgCacheKey(item.imageUrl);
              const ex2 = await chrome.storage.local.get(item.cacheKey);
              if (ex2[item.cacheKey]) { if (page) lastPage = Math.max(lastPage, page); return; } // 真圖已翻過
              notifyPrefetchPage(tabId, page, "download");
              try {
                fetched = await fetchOriginalImage(item.imageUrl, item.pageUrl || referer);
              } catch (e2) {
                if (/40\d|沒有|Page HTTP|not.?found|No page image/i.test(e2?.message || "")) stop = true;
                return;
              }
            } else {
              // 404 = 沒有下一頁了 → 標記停排（其他抓圖錯誤也停，避免空轉）
              if (/40\d|沒有|Page HTTP|not.?found|No page image/i.test(e?.message || "")) stop = true;
              return;
            }
          }
          const fp = _fp(fetched.image);
          if (fp && _seenFp.has(fp)) { stop = true; return; } // 站回同一張＝到底
          if (fp) _seenFp.add(fp);
          if (_abortGen !== myGen) return;
          // 縮圖縮小後送一次 → 該列顯示原圖縮圖，跟整頁翻譯的縮圖列一樣。
          makeThumbDataUrl(fetched.image).then((t) => { if (t) notifyPrefetchPage(tabId, page, null, t); });
          // 4) 翻譯（onStage 把伺服器階段即時回報到該列徽章）+ 寫快取。
          const r = await translateWithRetry(fetched.image, settings, (status, text) => {
            let stage;
            if (status === 3) stage = text ? `queue:${text}` : "queue";
            else if (status === 4) stage = "waiting";
            else stage = text;
            notifyPrefetchPage(tabId, page, stage);
          });
          if (page) lastPage = Math.max(lastPage, page);
          const translated = await blobToDataUrl(r.blob);
          if (_abortGen !== myGen) return; // 已被「清除所有翻譯」/中止 → 別寫回快取（否則清完又冒出來）
          await storePrefetchCache(item.cacheKey, { src: item.imageUrl, image: translated });
        } catch (e) {
          // 單頁爬圖/下載/翻譯/儲存失敗略過
        } finally {
          if (claimedKey) _prefetchInFlight.delete(claimedKey);
          _pfDone += 1;
          notifyPrefetchPage(tabId, page, null, null, true); // 該列收尾移除
          notifyPrefetchProgress(tabId);
          _semRelease();
        }
      })());
    }
    // 到底/中止：把「還沒排出去」的頁從 total 扣掉（已排的不論成功/404/重複都會 _pfDone++）。
    if (brokeAt < valid.length) {
      _pfTotal -= (valid.length - brokeAt);
      if (_pfTotal < _pfDone) _pfTotal = _pfDone;
    }
    await Promise.all(_pending); // 等所有並發「爬圖+下載+翻譯」收尾
  } finally {
    _pfActive -= 1;
    // 整輪預抓全部結束 → 帶 idle 旗標讓前端把進度面板收尾。不能只靠 done==total，因為遇 404/
    // 重複頁會砍 _pfTotal，done 可能永遠不等於 total，面板就會卡在最後的數字（如 27/29）。
    if (_pfActive <= 0) {
      _pfActive = 0;
      chrome.tabs.sendMessage(tabId, {
        type: "prefetch-progress",
        done: _pfDone,
        total: Math.max(_pfCrawled, _pfDone),
        crawled: _pfCrawled,
        planned: _pfPlanned,
        currentPage: _pfCurrentPage,
        idle: true
      }).catch(() => {});
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
  const controller = new AbortController();
  _activeTranslateAborts.add(controller);
  try {
    return await translateViaJob(apiBase, dataUrl, settings, onStage, controller.signal);
  } finally {
    _activeTranslateAborts.delete(controller);
  }
}

// async-job 模型（對齊網頁 UI 的 /translate/.../async-web）：上傳完連線立刻關閉，進度改用
// jobId 短輪詢、成品再抓檔案。如此就不會像舊的 /translate/image/stream 那樣「整段翻譯期間
// held 著一條長連線」——N 張同時翻會撞 Chrome『每來源 6 條 HTTP/1.1 連線』上限、把伺服器
// slot 餓著。改成短請求後，有效並發 = 伺服器 slot（workers×concurrency），突破 6 的天花板。
async function translateViaJob(apiBase, dataUrl, settings, onStage, signal) {
  // 1) 上傳 multipart（image 檔 + config 字串）→ 立刻拿到 jobId，連線即關
  const srcBlob = await (await fetch(dataUrl)).blob();
  const form = new FormData();
  form.append("image", srcBlob, "page.png");
  form.append("config", JSON.stringify(buildConfig(settings)));
  form.append("advanced", "0");
  form.append("priority", "0");
  const submit = await fetch(`${apiBase}/translate/with-form/image/async-web`, {
    method: "POST", body: form, signal,
  });
  if (!submit.ok) throw new Error(`API ${submit.status}`);
  const { jobId } = await submit.json();
  if (!jobId) throw new Error("伺服器未回傳 jobId");

  // 2) 短輪詢 jobId（650ms，對齊網頁 UI），把 code/status 轉成 onStage 進度；done 才往下。
  let noText = false;
  let folder = null;
  for (;;) {
    await sleep(650);
    if (signal.aborted) { const e = new Error("aborted"); e.name = "AbortError"; throw e; }
    const poll = await fetch(`${apiBase}/translate/jobs/${jobId}`, { signal });
    if (!poll.ok) throw new Error(`Job 狀態 HTTP ${poll.status}`);
    const job = await poll.json();
    const code = Number(job.code);
    const text = job.message || job.status || "";
    if (job.folder && !folder) folder = job.folder;
    if (/skip-no-text|skip-no-regions/i.test(text)) noText = true;
    if (code === 2 || job.status === "error") throw new Error(job.error || text || "翻譯失敗");
    if (onStage && (code === 1 || code === 3 || code === 4)) { try { onStage(code, text); } catch {} }
    if (job.done) { folder = job.folder || folder; break; }
  }

  // 3) 取成品：async-web 是「佔位符優化」，成品存伺服器硬碟 /result/{folder}/final.png。
  //    無 folder（偵測不到文字 → pipeline 在 render 前就結束、不產生成品夾）→ 結果＝原圖未動，
  //    回原圖 blob，呼叫者依 noText 自行處理（沿用舊 stream 版「no-text 回原圖」行為）。
  if (!folder) return { blob: srcBlob, noText: true };
  const imgResp = await fetch(`${apiBase}/result/${folder}/final.png`, { signal });
  if (!imgResp.ok) throw new Error(`成品圖 HTTP ${imgResp.status}`);
  return { blob: await imgResp.blob(), noText };
}

function concatU8(a, b) {
  if (!a.length) return b;
  if (!b.length) return a;
  const out = new Uint8Array(a.length + b.length);
  out.set(a, 0);
  out.set(b, a.length);
  return out;
}

// [legacy / 目前未使用] 舊的 /translate/image/stream 串流解析；已改走 translateViaJob（async-job
// 短輪詢）以突破 Chrome 每來源 6 連線上限。保留以備需要時參考；如確定不回退可整段刪除。
// 邊收邊解析串流：伺服器每完成一個階段就送一個 status-1 文字框（detection/ocr/translating/
// inpainting/rendering…）。改成 response.body.getReader() 逐塊解析，每解到一個階段就 onStage 回報，
// 最後一張 status-0 才是成品圖。
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

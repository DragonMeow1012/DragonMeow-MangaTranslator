"use strict";

const state = {
  root: null,
  button: null,
  status: null,
  progress: null,
  progressText: null,
  layer: null,
  highlight: null,
  label: null,
  picking: false,
  currentCandidate: null,
  overlays: new Set(),
  replacements: new Map(),
  autoArming: false,
  autoTargets: [],
  autoTargetLastRects: [],
  autoBusy: false,
  autoTimer: 0,
  autoGen: 0,
  viewMode: "translated", // "translated" | "original"
  bubbleHidden: false,
  bubblePrefs: { size: 48, color: "#0f766e", label: "譯" },
  lastSettingsText: ""
};

const BUBBLE_POS_KEY = "dmmt-ext-bubble-pos";
const BUBBLE_PREFS_KEY = "dmmtBubblePrefs";
const DEFAULT_BUBBLE_PREFS = { size: 48, color: "#0f766e", label: "譯" };
const IMG_CACHE_PREFIX = "dmmtImgCache:";
const IMG_CACHE_INDEX_KEY = "dmmtPageCacheIndex";
const IMG_CACHE_MAX_ENTRIES = 60;

function init() {
  removeExistingUi();
  createUi();
  installNavigationCleanup();
  syncSettingsIfOnMangaTranslatorUi();
  loadBubblePrefs();
  loadDebugFlag();
  startImgCacheScanner();
  installCacheRescan();
  resumePrefetchOnLoad();
}

// 每次「換頁類」互動（方向鍵/翻頁鍵/滾輪/點擊）後，連續快掃幾次快取，
// 確保快取有這頁的翻譯圖就立即覆蓋上（補足固定間隔掃描偶爾漏掉的情況）。
function installCacheRescan() {
  let burstId = 0;
  const burst = () => {
    window.clearInterval(burstId);
    let ticks = 0;
    burstId = window.setInterval(() => {
      try {
        if (!isContextValid()) { window.clearInterval(burstId); return; }
        scanAndApplyImgCache();
      } catch (e) {
        if (isExtContextError(e)) window.clearInterval(burstId);
      }
      if (++ticks >= 6) window.clearInterval(burstId); // 約 1.2s 內掃 6 次
    }, 200);
  };
  document.addEventListener("keyup", (event) => {
    if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "PageUp", "PageDown", " ", "Enter"].includes(event.key)) burst();
  }, true);
  document.addEventListener("pointerup", (event) => {
    if (state.root?.contains(event.target)) return;
    burst();
  }, true);
  let wheelTimer = 0;
  document.addEventListener("wheel", () => {
    window.clearTimeout(wheelTimer);
    wheelTimer = window.setTimeout(burst, 250);
  }, true);
}

// ---- 診斷 + 預抓設定：從 storage 載入，並隨 popup 變更即時更新 ----
let _debugOn = false;
let _imgDiag = "";
let _wheelNav = false;  // 滾輪翻頁（配合合併翻譯）
let _wheelDir = "rtl";  // 翻頁方向：rtl(右到左,日漫) / ltr(左到右) / vertical(上下)
let _autoPersistEnabled = false; // 頁碼翻譯啟用中（持久化；換頁/重載後自動續抓，讓進度往後滑動）
let _pagePersistEnabled = false; // 整頁翻譯啟用中（持久化）
const PREFETCH_TO_END_CAP = 200; // 預抓往後猜的上限（一律翻到完；背景遇 404 自然停）
let _showPrefetch = true;   // 顯示預抓進度（指泡泡時的 tooltip）
let _lastPrefetchPage = 0;
let _pfProg = null;         // 頁碼翻譯預抓即時進度 {done,total}，顯示在泡泡 tooltip
function loadDebugFlag() {
  chromeSafeGet(["dmmtDebugInput", "dmmtPrefetchNotify", "dmmtBoxMode", "dmmtBoxOrigin", "dmmtBoxRects", "dmmtWheelNav", "dmmtWheelDir"], (s) => {
    _debugOn = s?.dmmtDebugInput === true;
    if (typeof s?.dmmtWheelNav === "boolean") _wheelNav = s.dmmtWheelNav;
    if (typeof s?.dmmtWheelDir === "string") _wheelDir = s.dmmtWheelDir;
    if (s?.dmmtBoxMode === true && s?.dmmtBoxOrigin === location.origin && Array.isArray(s?.dmmtBoxRects)) {
      _boxMode = true; _boxRects = s.dmmtBoxRects;
    }
    if (typeof s?.dmmtPrefetchNotify === "boolean") _showPrefetch = s.dmmtPrefetchNotify;
  });
  try {
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area !== "local") return;
      if (changes.dmmtDebugInput) _debugOn = changes.dmmtDebugInput.newValue === true;
      if (changes.dmmtWheelNav && typeof changes.dmmtWheelNav.newValue === "boolean") _wheelNav = changes.dmmtWheelNav.newValue;
      if (changes.dmmtWheelDir && typeof changes.dmmtWheelDir.newValue === "string") _wheelDir = changes.dmmtWheelDir.newValue;
      if (changes.dmmtPrefetchNotify && typeof changes.dmmtPrefetchNotify.newValue === "boolean") {
        _showPrefetch = changes.dmmtPrefetchNotify.newValue;
        refreshBubbleTitle();
      }
    });
  } catch {}
}

const DEFAULT_BUBBLE_TITLE = "點選頁面上的圖片或漫畫畫布並翻譯（按住可拖曳）";
// 「顯示預抓頁數」開啟且頁碼翻譯啟用時，泡泡 tooltip 顯示預抓狀態；否則回到預設說明。
function refreshBubbleTitle() {
  if (!state.button) return;
  const autoOn = state.autoTargets.length > 0 || state.autoArming || _autoPersistEnabled;
  if (state.boxEditing || (_boxMode && _boxRects.length)) {
    state.button.title = "點一下翻譯這頁（合併翻譯）";
  } else if (_showPrefetch && autoOn) {
    state.button.title = _pfProg ? `頁碼翻譯：已完成 ${_pfProg.done} 頁` : "頁碼翻譯啟用中";
  } else {
    state.button.title = DEFAULT_BUBBLE_TITLE;
  }
}
function updateBubblePrefetchTitle(lastPage) {
  if (lastPage > _lastPrefetchPage) _lastPrefetchPage = lastPage;
  refreshBubbleTitle();
}

// 背景預抓的即時進度 → 顯示在泡泡 tooltip（頁碼翻譯中… done/total）。
chrome.runtime.onMessage.addListener((message) => {
  if (message?.type !== "prefetch-progress") return;
  _pfProg = { done: message.done, total: message.total };
  if (_showPrefetch && message.done > 0) {
    showStatus(`頁碼翻譯：已完成 ${message.done} 頁`, 1600);
  }
  refreshBubbleTitle();
});
function imageDims(dataUrl) {
  return new Promise((resolve, reject) => {
    const im = new Image();
    im.onload = () => resolve({ w: im.naturalWidth, h: im.naturalHeight });
    im.onerror = () => reject(new Error("dim load failed"));
    im.src = dataUrl;
  });
}
async function reportDiag(method, dataUrl) {
  let dims = "";
  try { const d = await imageDims(dataUrl); dims = ` ${d.w}×${d.h}`; } catch {}
  const msg = `[診斷] ${method}${dims}`;
  try { console.log("%c[DMMT] " + msg, "color:#14b8a6;font-weight:bold"); } catch {}
  if (_debugOn) showStatus(msg, 5000);
}

// ---- 翻譯結果快取：以圖片網址為 key，切回已翻譯的頁面時自動復原。

function absoluteImageUrl(src) {
  try {
    return new URL(src, location.href).href;
  } catch {
    return "";
  }
}

// 去掉 query/hash：很多站圖片網址帶旋轉 token（?token=...），同一張圖每次網址都不同，
// 會導致快取 key 不同 → 重複翻譯、存重複檔、掃描器又對不上而沒套用。正規化後同頁同 key。
function normalizedImageUrl(src) {
  const clean = absoluteImageUrl(src).split(/[?#]/)[0];
  try {
    const u = new URL(clean);
    // 去掉 CDN 分流子網域的編號（i4.nhentai.net / i1.nhentai.net → nhentai.net、img3.x.com → x.com）。
    // 同一張圖常被分流到不同編號的子網域，網址不同卻是同一張，不正規化會害快取/預測對不上。
    // 只剝「字母+數字」開頭的子網域（i4、img3、cdn2…），不動 www、IP（1.2.3.4）等。
    const host = u.host.replace(/^[a-z]+\d+\./i, "");
    return u.protocol + "//" + host + u.pathname;
  } catch {
    return clean;
  }
}

function imgCacheKey(src) {
  return IMG_CACHE_PREFIX + normalizedImageUrl(src);
}

// 取「真正顯示的圖片網址」當快取依據：lazy-load 時 getAttribute("src") 常是佔位圖，
// 真正載入的是 currentSrc。優先用 currentSrc，沒有才用 src 屬性。
function bestImageUrl(img) {
  const cs = img.currentSrc || "";
  if (cs && !cs.startsWith("data:")) return cs;
  const a = img.getAttribute("src") || "";
  return (a && !a.startsWith("data:")) ? a : "";
}

function saveTranslationToImgCache(originalSrc, dataUrl) {
  if (!originalSrc || String(originalSrc).startsWith("data:")) return;
  const key = imgCacheKey(originalSrc);
  chromeSafeGet(IMG_CACHE_INDEX_KEY, (stored) => {
    let index = Array.isArray(stored?.[IMG_CACHE_INDEX_KEY]) ? stored[IMG_CACHE_INDEX_KEY] : [];
    index = index.filter((entry) => entry.key !== key);
    index.push({ key, ts: Date.now() });
    const evicted = index.length > IMG_CACHE_MAX_ENTRIES ? index.splice(0, index.length - IMG_CACHE_MAX_ENTRIES) : [];
    chromeSafeSet({
      [key]: { src: originalSrc, image: dataUrl },
      [IMG_CACHE_INDEX_KEY]: index
    });
    if (evicted.length) {
      chromeSafeRemove(evicted.map((entry) => entry.key));
    }
  });
}

function dropImgCacheEntry(originalSrc) {
  if (originalSrc) chromeSafeRemove(imgCacheKey(originalSrc));
}

// 連續翻譯時，若網址列尾碼是頁數、且圖檔名也是同一個頁數（nhentai 等），
// 就推算後面 10 頁的圖網址，交給背景「爬蟲」預先抓圖+翻譯+寫快取。
// 跳過已排過/已快取的；背景遇到 404 代表沒有下一頁就停。
const _prefetchedKeys = new Set();
let _predictedNext = "";   // 上一頁推算出的「下一頁」絕對網址，供翻頁後驗證
let _prefetchMisses = 0;   // 連續預測失敗次數
let _prefetchOff = false;  // 預測連續失敗就停用本頁面的預抓

function schedulePrefetchNextPages(originalSrc, countOverride) {
  if (_prefetchOff || !originalSrc) return;
  if (!state.autoTargets.length && !_pageTranslate && !_autoPersistEnabled && !_pagePersistEnabled) return;
  // 不驗證網址頁碼——直接抓圖檔名「副檔名前的最後一組數字」往後加。
  // 猜錯的網址背景抓到 404 就停，不會有副作用。保留前導零位數（0005 → 0006）。
  const clean = String(originalSrc).split(/[?#]/)[0];
  const fileMatch = clean.match(/^(.*?)(\d+)(\D*\.[A-Za-z0-9]+)$/);
  if (!fileMatch) {
    if (_debugOn) console.log("[DMMT 預抓] 圖檔名沒有數字，略過", clean);
    return;
  }
  const filePageStr = fileMatch[2];
  const pageNum = Number(filePageStr);
  if (!pageNum) return;

  const count = clamp(typeof countOverride === "number" ? countOverride : PREFETCH_TO_END_CAP, 0, PREFETCH_TO_END_CAP);
  if (count <= 0) return;
  const pad = filePageStr.length;
  const buildUrl = (n) => absoluteImageUrl(fileMatch[1] + String(n).padStart(pad, "0") + fileMatch[3]);
  _predictedNext = buildUrl(pageNum + 1); // 記住「下一頁」預測，翻頁後驗證

  const items = [];
  for (let i = 1; i <= count; i++) {
    const page = pageNum + i;
    const imageUrl = buildUrl(page);
    const cacheKey = imgCacheKey(imageUrl); // 正規化 key（去 query），和掃描器/快取一致
    if (!imageUrl || _prefetchedKeys.has(cacheKey)) continue;
    _prefetchedKeys.add(cacheKey);
    items.push({ cacheKey, imageUrl, page });
  }
  if (_debugOn) console.log("[DMMT 預抓] 排入", items.length, "頁，從", clean, "→", items[0]?.imageUrl);
  if (items.length) {
    sendMessage({ type: "prefetch-translate", items, referer: location.href }).then((result) => {
      // 不跳 toast；改成更新泡泡 tooltip，指著泡泡就能看到已預翻到第幾頁。
      if (result?.lastPage) updateBubblePrefetchTitle(result.lastPage);
    }).catch(() => {});
  }
}

// 翻頁後驗證：實際的新頁圖網址有沒有命中上一頁的「下一頁」預測。
// 連續猜錯兩次就停用預抓（這網站的網址規則不是單純遞增），避免一直白抓。
function verifyPrefetchPrediction(newSrc) {
  if (!_predictedNext) return;
  // 用正規化網址比對（去掉分流子網域編號），否則 i4→i1 之類的換伺服器會被誤判成「猜錯」而停用預抓。
  const predicted = normalizedImageUrl(_predictedNext);
  _predictedNext = "";
  const actual = normalizedImageUrl(String(newSrc));
  if (!actual) return;
  if (actual === predicted) {
    _prefetchMisses = 0;
    if (_debugOn) console.log("[DMMT 預抓] 翻頁驗證 ✓ 預測正確", actual);
  } else {
    _prefetchMisses += 1;
    if (_debugOn) console.log(`[DMMT 預抓] 翻頁驗證 ✗ (${_prefetchMisses}/2) 預測`, predicted, "實際", actual);
    if (_prefetchMisses >= 2) {
      _prefetchOff = true;
      if (_debugOn) console.log("[DMMT 預抓] 連續預測失敗，本頁面停用預抓");
    }
  }
}

function startImgCacheScanner() {
  scanAndApplyImgCache();
  // 初始 3 秒內每 120ms 快掃，確保切回已翻頁面時能立即復原；之後降頻到 1500ms 節省資源。
  const fastId = window.setInterval(() => {
    try {
      if (!isContextValid()) { window.clearInterval(fastId); return; }
      scanAndApplyImgCache();
    } catch (e) {
      if (isExtContextError(e)) { window.clearInterval(fastId); } else { throw e; }
    }
  }, 60);
  window.setTimeout(() => {
    window.clearInterval(fastId);
    const id = window.setInterval(() => {
      try {
        if (!isContextValid()) { window.clearInterval(id); return; }
        scanAndApplyImgCache();
      } catch (e) {
        if (isExtContextError(e)) { window.clearInterval(id); } else { throw e; }
      }
    }, 1500);
  }, 3000);
}

function scanAndApplyImgCache() {
  if (!isContextValid()) return;
  try { _scanAndApplyImgCache(); } catch (e) { if (!isExtContextError(e)) throw e; }
}

function _scanAndApplyImgCache() {
  // 若已替換的圖 src 被網站換掉（SPA 翻頁重用同一元素），清出 replacements 讓掃描器接手。
  for (const [img, record] of Array.from(state.replacements)) {
    if (record.kind !== "img") continue;
    const current = img.getAttribute("src");
    if (current && current !== record.src && !current.startsWith("data:")) {
      record.observer?.disconnect();
      state.replacements.delete(img);
    }
  }
  const candidates = [];
  for (const img of document.images) {
    if (state.replacements.has(img)) continue;
    if (!img.complete || img.naturalWidth < 200 || img.naturalHeight < 200) continue;
    // 同時收集 currentSrc 與 src 屬性兩種 key（lazy-load 兩者常不同），任一命中就套用。
    const keys = [];
    const cs = img.currentSrc || "";
    if (cs && !cs.startsWith("data:")) keys.push(imgCacheKey(cs));
    const a = img.getAttribute("src") || "";
    if (a && !a.startsWith("data:")) {
      const k = imgCacheKey(a);
      if (!keys.includes(k)) keys.push(k);
    }
    if (keys.length) candidates.push({ img, keys });
  }
  if (!candidates.length) return;

  const allKeys = [...new Set(candidates.flatMap((c) => c.keys))];
  chromeSafeGet(allKeys, (stored) => {
    let applied = 0;
    for (const { img, keys } of candidates) {
      if (state.replacements.has(img)) continue;
      const hitKey = keys.find((k) => stored?.[k]?.image);
      if (!hitKey) continue;
      try { replaceImgElement(img, stored[hitKey].image); applied++; } catch {}
    }
    if (_debugOn && applied) console.log(`[DMMT 快取] 套用 ${applied} 張`);
  });
}

// 快取套用診斷：列出本頁每張大圖的 key 與快取裡的 key，方便看出為什麼沒對上。
function diagnoseCacheApply() {
  chromeSafeGet(null, (all) => {
    const cacheKeys = Object.keys(all || {}).filter((k) => k.startsWith(IMG_CACHE_PREFIX));
    const lines = ["==== DMMT 快取診斷 ====", `快取共 ${cacheKeys.length} 張`];
    let hit = 0, bigCount = 0;
    for (const img of document.images) {
      const r = img.getBoundingClientRect();
      if ((img.naturalWidth || 0) < 200 && r.width < 200) continue;
      bigCount++;
      const cs = img.currentSrc || "";
      const a = img.getAttribute("src") || "";
      const keyCs = cs && !cs.startsWith("data:") ? imgCacheKey(cs) : "";
      const keyA = a && !a.startsWith("data:") ? imgCacheKey(a) : "";
      const inCache = Boolean((keyCs && all[keyCs]) || (keyA && all[keyA]));
      if (inCache) hit++;
      lines.push(
        `圖 ${img.naturalWidth}x${img.naturalHeight} complete=${img.complete} 已替換=${state.replacements.has(img)} 命中=${inCache}\n` +
        `  currentSrc = ${cs}\n  src屬性   = ${a}\n  key(cs)=${keyCs}\n  key(src)=${keyA}`
      );
    }
    lines.push(`本頁大圖 ${bigCount} 張，命中快取 ${hit} 張`);
    lines.push("快取 key 樣本（前 12 個）:");
    cacheKeys.slice(0, 12).forEach((k) => lines.push("  " + k));
    console.log(lines.join("\n"));
    showStatus(`快取診斷：快取 ${cacheKeys.length} 張、本頁命中 ${hit}/${bigCount}（詳見 F12 console）`, 7000);
  });
}

function loadBubblePrefs() {
  if (!isContextValid()) return;
  chromeSafeGet(BUBBLE_PREFS_KEY, (stored) => {
    applyBubblePrefs(stored?.[BUBBLE_PREFS_KEY]);
  });
  try {
    chrome.storage.onChanged.addListener((changes, area) => {
      if (!isContextValid()) return;
      if (area === "local" && changes[BUBBLE_PREFS_KEY]) {
        applyBubblePrefs(changes[BUBBLE_PREFS_KEY].newValue);
      }
    });
  } catch {}
}

function applyBubblePrefs(prefs) {
  state.bubblePrefs = { ...DEFAULT_BUBBLE_PREFS, ...(prefs || {}) };
  const size = clamp(Number(state.bubblePrefs.size) || DEFAULT_BUBBLE_PREFS.size, 28, 96);
  state.bubblePrefs.size = size;
  state.root.style.setProperty("--dmmt-bubble-size", `${size}px`);
  state.root.style.setProperty("--dmmt-bubble-bg", state.bubblePrefs.color || DEFAULT_BUBBLE_PREFS.color);
  if (!state.picking) {
    state.button.textContent = state.bubblePrefs.label || DEFAULT_BUBBLE_PREFS.label;
  }
  applyBubblePosition(state.button, loadBubblePosition());
}

function bubbleSize() {
  return state.bubblePrefs.size || DEFAULT_BUBBLE_PREFS.size;
}

// 整頁批次翻譯：直接讀取每張圖片的像素（canvas）送翻譯，並行處理、不需捲動、原解析度。
// 跨域防盜圖無法讀取像素（canvas 受污染），這類圖會被略過並在結尾統計回報。
// 持續模式：完成首批後仍持續監看，網頁延遲載入（lazy-load）或無限捲動載入的新圖會接著
// 自動翻譯，直到使用者再次點「整頁翻譯」關閉，或執行清除／離開頁面。
const PAGE_TRANSLATE_CONCURRENCY = 3;
let _pageTranslate = null; // 持續模式狀態物件；null = 未啟用

// 是否為「值得整頁翻譯」的圖：已載入、自然或顯示尺寸夠大（過濾圖示/頭像/廣告），且尚未替換。
function pageImageTranslatable(el) {
  if (state.replacements.has(el)) return false;
  const natW = el.naturalWidth || 0;
  const natH = el.naturalHeight || 0;
  const r = el.getBoundingClientRect();
  const bigEnough = (natW >= 300 && natH >= 300) || (r.width >= 200 && r.height >= 200);
  return bigEnough && el.complete && natW > 0;
}

function translatePage() {
  // 已在啟用 → 關閉，並終止所有進行中的任務。
  if (_pageTranslate) {
    terminateAllTasks();
    showStatus("已停止整頁翻譯，已終止所有進行中的翻譯", 2000);
    return;
  }
  if (state.picking) stopPickMode();

  const pt = {
    seen: new WeakSet(), // 已排入佇列的圖（避免重複排入；防盜圖/失敗也不再重試）
    queue: [],
    active: 0,
    total: 0, done: 0, ok: 0, blocked: 0, failed: 0,
    observer: null, onScroll: null, rescanTimer: 0
  };
  _pageTranslate = pt;
  _pagePersistEnabled = true;
  chromeSafeSet({ dmmtPageEnabled: true, dmmtPageOrigin: location.origin });

  // 監看新載入內容：DOM 變動（新增 <img>）＋ 捲動（觸發 lazy-load）＋ 低頻定時補掃
  //（圖片在 DOM 內慢慢載入完成、未必伴隨 DOM 變動或捲動）。
  pt.observer = new MutationObserver(schedulePageRescan);
  try { pt.observer.observe(document.documentElement, { childList: true, subtree: true }); } catch {}
  pt.onScroll = schedulePageRescan;
  window.addEventListener("scroll", pt.onScroll, true);
  pt.rescanTimer = window.setInterval(collectNewPageImages, 2000);

  const found = collectNewPageImages();
  if (!found) {
    showStatus("整頁翻譯：目前沒有可翻譯的圖片，已開始監看，載入後會自動翻譯（再點一次可停止）", 3500);
  }
  schedulePageTranslatePrefetch();
}

// 整頁翻譯也「往後預先翻 N 頁」：挑一張代表圖（面積最大、檔名有頁碼），預抓後面 N 頁。
// webtoon（圖名沒頁碼）會自然 no-op。
// 取本頁「主圖的原始網址」當預抓基準。重點：圖被翻譯替換成 data: 之後，
// 要改用替換記錄裡保存的原網址，否則換頁後算不出頁碼、預抓就停了（滑不動）。
function mainPageImageUrl() {
  let bestUrl = "", best = 0;
  for (const img of document.images) {
    if ((img.naturalWidth || 0) < 200 || (img.naturalHeight || 0) < 200) continue;
    const rec = state.replacements.get(img);
    const url = (rec && rec.kind === "img" && rec.cacheUrl) ? rec.cacheUrl : bestImageUrl(img);
    if (!url || url.startsWith("data:")) continue;
    const area = img.naturalWidth * img.naturalHeight;
    if (area > best) { best = area; bestUrl = url; }
  }
  return bestUrl;
}

function schedulePageTranslatePrefetch() {
  if (!_pageTranslate) return;
  const url = mainPageImageUrl();
  if (url) schedulePrefetchNextPages(url, PREFETCH_TO_END_CAP);
}

// 換頁/重新載入後，若頁碼翻譯或整頁翻譯仍啟用，從本頁主圖往後續抓，
// 讓「預先翻譯頁數」隨閱讀進度持續往後滑動（全重載站點靠這個維持，例如 nhentai）。
function resumePrefetchOnLoad() {
  chromeSafeGet(["dmmtAutoEnabled", "dmmtAutoOrigin", "dmmtPageEnabled", "dmmtPageOrigin"], (s) => {
    // 只在「啟用當下的網站」自動續抓，避免你之後逛別的網站也被預抓燒額度。
    _autoPersistEnabled = s?.dmmtAutoEnabled === true && s?.dmmtAutoOrigin === location.origin;
    _pagePersistEnabled = s?.dmmtPageEnabled === true && s?.dmmtPageOrigin === location.origin;
    if (_autoPersistEnabled || _pagePersistEnabled) kickResumePrefetch(PREFETCH_TO_END_CAP, 0);
  });
}

// 等本頁主圖載入完成再續抓（init 跑得早，圖可能還沒載好）。
function kickResumePrefetch(count, attempt) {
  const url = mainPageImageUrl();
  if (url) {
    if (_debugOn) console.log("[DMMT 續抓] 本頁主圖", url, "往後", count, "頁");
    schedulePrefetchNextPages(url, count);
  } else if (attempt < 30) {
    window.setTimeout(() => kickResumePrefetch(count, attempt + 1), 300);
  }
}

// 把目前 DOM 中「尚未處理過、且已載入夠大」的圖片排入佇列，回傳本次新增數量。
function collectNewPageImages() {
  const pt = _pageTranslate;
  if (!pt) return 0;
  const fresh = [];
  for (const el of document.querySelectorAll("img")) {
    if (pt.seen.has(el)) continue;
    if (!pageImageTranslatable(el)) continue;
    pt.seen.add(el);
    fresh.push(el);
  }
  if (!fresh.length) return 0;
  // 由上而下排序，符合閱讀順序。
  fresh.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
  pt.queue.push(...fresh);
  pt.total += fresh.length;
  updatePageStatus();
  pumpPageTranslate();
  return fresh.length;
}

let _pageRescanScheduled = false;
function schedulePageRescan() {
  if (!_pageTranslate || _pageRescanScheduled) return;
  _pageRescanScheduled = true;
  window.setTimeout(() => {
    _pageRescanScheduled = false;
    collectNewPageImages();
  }, 300);
}

// 確保最多 N 個工作者在消化佇列；每個工作者會持續取用，直到佇列清空。
function pumpPageTranslate() {
  const pt = _pageTranslate;
  if (!pt) return;
  while (pt.active < PAGE_TRANSLATE_CONCURRENCY && pt.queue.length) {
    pt.active++;
    pageTranslateWorker(pt).finally(() => {
      pt.active--;
      if (_pageTranslate !== pt) return;
      if (pt.queue.length) pumpPageTranslate();
      else if (pt.active === 0) onPageQueueDrained();
    });
  }
}

async function pageTranslateWorker(pt) {
  while (_pageTranslate === pt && pt.queue.length) {
    const el = pt.queue.shift();
    if (!el || state.replacements.has(el) || !document.contains(el)) { pt.done++; updatePageStatus(); continue; }
    const dataUrl = await getFullResImageDataUrl(el);
    if (_pageTranslate !== pt) return;          // 期間已關閉
    if (!dataUrl) { pt.blocked++; pt.done++; updatePageStatus(); continue; } // 防盜圖，無法讀取像素
    try {
      const resp = await sendMessage({ type: "translate-data-url", image: dataUrl });
      if (_pageTranslate !== pt) return;        // 期間已關閉，別套用
      if (!state.replacements.has(el) && document.contains(el)) {
        replaceImgElement(el, resp.image);
        pt.ok++;
      }
    } catch {
      pt.failed++;
    }
    pt.done++;
    updatePageStatus();
  }
}

function updatePageStatus() {
  const pt = _pageTranslate;
  if (pt && pt.done < pt.total) showStatus(`整頁翻譯中… ${pt.done}/${pt.total}`);
}

// 佇列清空（暫時沒有待翻圖）→ 顯示成果並提示仍在監看，不關閉，等新內容載入後自動接續。
function onPageQueueDrained() {
  const pt = _pageTranslate;
  if (!pt) return;
  let msg = `整頁翻譯：已完成 ${pt.ok}`;
  if (pt.blocked) msg += `，防盜圖無法擷取 ${pt.blocked}`;
  if (pt.failed) msg += `，失敗 ${pt.failed}`;
  msg += "；持續監看中，捲動載入新內容會自動翻譯（再點一次可停止）";
  showStatus(msg, 4000);
}

function stopPageTranslate() {
  const pt = _pageTranslate;
  if (!pt) return;
  _pageTranslate = null; // 進行中的工作者會在下次檢查時自行停止，不再套用
  try { pt.observer?.disconnect(); } catch {}
  if (pt.onScroll) window.removeEventListener("scroll", pt.onScroll, true);
  window.clearInterval(pt.rescanTimer);
}

// 把已載入的 <img> 以原解析度畫到 canvas 取出 dataURL；跨域受污染時回傳 null。
function imageElementToDataUrl(img) {
  try {
    const w = img.naturalWidth || img.width;
    const h = img.naturalHeight || img.height;
    if (!w || !h) return null;
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(img, 0, 0, w, h);
    return canvas.toDataURL("image/png"); // 跨域防盜圖會丟 SecurityError
  } catch {
    return null;
  }
}

// 取得原始解析度圖片，依序嘗試：
// 1) 直接讀（同源）2) CORS 重新載入（部分 CDN 允許）3) 背景「爬蟲」抓原圖（需使用者授權）。
// 都拿不到才回 null，由呼叫端退回截圖。
async function getFullResImageDataUrl(img) {
  _imgDiag = "";
  const direct = imageElementToDataUrl(img);
  if (direct) { _imgDiag = "同源直讀原圖"; return direct; }

  const src = img.currentSrc || img.getAttribute("src") || "";
  if (!src || src.startsWith("data:")) { _imgDiag = "無有效圖片網址"; return null; }

  // 2) CORS 重新載入
  try {
    const corsImg = await new Promise((resolve, reject) => {
      const im = new Image();
      im.crossOrigin = "anonymous";
      im.onload = () => resolve(im);
      im.onerror = () => reject(new Error("CORS 載入失敗"));
      im.src = src;
    });
    const w = corsImg.naturalWidth, h = corsImg.naturalHeight;
    if (w && h) {
      const canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = h;
      canvas.getContext("2d").drawImage(corsImg, 0, 0, w, h);
      _imgDiag = "CORS原圖";
      return canvas.toDataURL("image/png");
    }
  } catch {
    // 不給 CORS → 試爬蟲
  }

  // 3) 背景爬蟲抓原圖（背景 fetch 繞過 CORS，並偽造 Referer 過防盜圖）
  try {
    const resp = await sendMessage({ type: "fetch-original-image", url: src, referer: location.href });
    if (resp?.image) { _imgDiag = "爬蟲原圖"; return resp.image; }
    _imgDiag = "爬蟲無回應";
  } catch (e) {
    _imgDiag = "爬蟲失敗:" + (e?.message || e);
  }
  return null;
}

// 下載目前頁面所有翻譯圖（原地替換 + 覆蓋層）。
// 當前頁面上已套用的翻譯圖（原地替換 + 覆蓋層）。
function collectCurrentImages() {
  const urls = [];
  for (const [, rec] of state.replacements) {
    if (rec.dataUrl) urls.push(rec.dataUrl);
  }
  for (const holder of state.overlays) {
    const img = holder.querySelector("img");
    if (img?.src) urls.push(img.src);
  }
  return urls;
}

// 下載「當前頁面」翻譯圖：1 張直接存 PNG，多張壓成 zip（避免瀏覽器擋多檔下載）。
function downloadCurrentTranslations() {
  const urls = collectCurrentImages();
  if (!urls.length) { showStatus("此頁沒有可下載的翻譯圖", 2000); return; }
  if (urls.length === 1) {
    downloadDataUrl(urls[0], "manga-translated.png");
    showStatus("已下載翻譯圖", 1800);
    return;
  }
  zipAndDownloadImages(urls, "manga-current-page.zip");
}

// 下載「所有」翻譯圖：當前頁面 + 所有快取（各頁讀過的），壓成 zip。
function downloadAllTranslations() {
  chromeSafeGet(null, (all) => {
    const seen = new Set();
    const urls = [];
    const push = (u) => { if (u && !seen.has(u)) { seen.add(u); urls.push(u); } };
    // 快取裡所有頁的翻譯圖
    for (const k of Object.keys(all || {})) {
      if (k.startsWith(IMG_CACHE_PREFIX) && all[k]?.image) push(all[k].image);
    }
    // 加上當前頁面（覆蓋層不在快取裡）
    for (const u of collectCurrentImages()) push(u);
    if (!urls.length) { showStatus("沒有可下載的翻譯圖", 2000); return; }
    zipAndDownloadImages(urls, "manga-all-translations.zip");
  });
}

function downloadDataUrl(dataUrl, name) {
  const a = document.createElement("a");
  a.href = dataUrl;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function downloadBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 5000);
}

function dataUrlToBytes(dataUrl) {
  const base64 = String(dataUrl).split(",")[1] || "";
  const bin = atob(base64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

// CRC32（zip 需要）。
const _crcTable = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
    t[n] = c >>> 0;
  }
  return t;
})();
function crc32(bytes) {
  let crc = 0xFFFFFFFF;
  for (let i = 0; i < bytes.length; i++) crc = _crcTable[(crc ^ bytes[i]) & 0xFF] ^ (crc >>> 8);
  return (crc ^ 0xFFFFFFFF) >>> 0;
}

// 最小化 zip 產生器（store 模式、不壓縮），把多張 PNG 包成一個 zip 一次下載。
function zipAndDownloadImages(dataUrls, zipName) {
  showStatus(`打包 ${dataUrls.length} 張翻譯圖…`);
  const enc = new TextEncoder();
  const localChunks = [];
  const centralChunks = [];
  let offset = 0;
  dataUrls.forEach((dataUrl, i) => {
    const data = dataUrlToBytes(dataUrl);
    const name = `translated-${String(i + 1).padStart(3, "0")}.png`;
    const nameBytes = enc.encode(name);
    const crc = crc32(data);
    const size = data.length;

    const lfh = new DataView(new ArrayBuffer(30));
    lfh.setUint32(0, 0x04034b50, true);
    lfh.setUint16(4, 20, true);
    lfh.setUint16(8, 0, true);   // store
    lfh.setUint32(14, crc, true);
    lfh.setUint32(18, size, true);
    lfh.setUint32(22, size, true);
    lfh.setUint16(26, nameBytes.length, true);
    localChunks.push(new Uint8Array(lfh.buffer), nameBytes, data);

    const cdh = new DataView(new ArrayBuffer(46));
    cdh.setUint32(0, 0x02014b50, true);
    cdh.setUint16(4, 20, true);
    cdh.setUint16(6, 20, true);
    cdh.setUint16(10, 0, true);  // store
    cdh.setUint32(16, crc, true);
    cdh.setUint32(20, size, true);
    cdh.setUint32(24, size, true);
    cdh.setUint16(28, nameBytes.length, true);
    cdh.setUint32(42, offset, true);
    centralChunks.push(new Uint8Array(cdh.buffer), nameBytes);

    offset += 30 + nameBytes.length + size;
  });
  let centralSize = 0;
  for (const c of centralChunks) centralSize += c.length;

  const eocd = new DataView(new ArrayBuffer(22));
  eocd.setUint32(0, 0x06054b50, true);
  eocd.setUint16(8, dataUrls.length, true);
  eocd.setUint16(10, dataUrls.length, true);
  eocd.setUint32(12, centralSize, true);
  eocd.setUint32(16, offset, true);

  const blob = new Blob([...localChunks, ...centralChunks, new Uint8Array(eocd.buffer)], { type: "application/zip" });
  downloadBlob(blob, zipName);
  showStatus(`已下載 ${dataUrls.length} 張翻譯圖（zip）`, 2500);
}

// 關閉/開啟翻譯泡泡：只隱藏浮動按鈕，不影響已套用的翻譯。
function toggleBubbleVisibility() {
  state.bubbleHidden = !state.bubbleHidden;
  if (state.bubbleHidden) {
    if (state.picking) stopPickMode();
    state.button.classList.add("dmmt-ext-hidden");
    showStatus("已關閉翻譯泡泡", 1500);
  } else {
    state.button.classList.remove("dmmt-ext-hidden");
    showStatus("已開啟翻譯泡泡", 1500);
  }
}

function removeExistingUi() {
  for (const element of document.querySelectorAll("#dmmt-ext-root, .dmmt-ext-result")) {
    element.remove();
  }
}

function createUi() {
  state.root = document.createElement("div");
  state.root.id = "dmmt-ext-root";

  state.button = document.createElement("button");
  state.button.className = "dmmt-ext-button";
  state.button.type = "button";
  state.button.textContent = state.bubblePrefs.label;
  state.button.title = DEFAULT_BUBBLE_TITLE;
  makeBubbleDraggable(state.button);

  installAutoTriggers();

  state.status = document.createElement("div");
  state.status.className = "dmmt-ext-status dmmt-ext-hidden";

  state.progress = document.createElement("div");
  state.progress.className = "dmmt-ext-progress dmmt-ext-hidden";
  state.progressText = document.createElement("div");
  state.progressText.className = "dmmt-ext-progress-text";
  const progressTrack = document.createElement("div");
  progressTrack.className = "dmmt-ext-progress-track";
  const progressBar = document.createElement("div");
  progressBar.className = "dmmt-ext-progress-bar";
  progressTrack.append(progressBar);
  state.progress.append(progressTrack, state.progressText);

  state.highlight = document.createElement("div");
  state.highlight.className = "dmmt-ext-highlight dmmt-ext-hidden";

  state.label = document.createElement("div");
  state.label.className = "dmmt-ext-label dmmt-ext-hidden";

  state.root.append(state.button, state.status, state.progress, state.highlight, state.label);
  document.documentElement.append(state.root);
}

function makeBubbleDraggable(button) {
  applyBubblePosition(button, loadBubblePosition());

  let dragging = false;
  let moved = false;
  let startX = 0;
  let startY = 0;
  let originLeft = 0;
  let originTop = 0;

  button.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 && event.pointerType === "mouse") return;
    dragging = true;
    moved = false;
    startX = event.clientX;
    startY = event.clientY;
    const rect = button.getBoundingClientRect();
    originLeft = rect.left;
    originTop = rect.top;
    button.setPointerCapture(event.pointerId);
  });

  button.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    const dx = event.clientX - startX;
    const dy = event.clientY - startY;
    if (!moved && Math.hypot(dx, dy) < 5) return;
    moved = true;
    button.classList.add("dmmt-ext-dragging");
    applyBubblePosition(button, { left: originLeft + dx, top: originTop + dy });
  });

  button.addEventListener("pointerup", (event) => {
    if (!dragging) return;
    dragging = false;
    button.classList.remove("dmmt-ext-dragging");
    if (moved) {
      const rect = button.getBoundingClientRect();
      saveBubblePosition({ left: rect.left, top: rect.top });
    } else {
      togglePickMode();
    }
  });

  button.addEventListener("pointercancel", () => {
    dragging = false;
    button.classList.remove("dmmt-ext-dragging");
  });

  window.addEventListener("resize", () => {
    const rect = button.getBoundingClientRect();
    applyBubblePosition(button, { left: rect.left, top: rect.top });
  });
}

function applyBubblePosition(button, pos) {
  const hasLeft = pos && typeof pos.left === "number";
  const hasTop = pos && typeof pos.top === "number";
  const left = clamp(hasLeft ? pos.left : window.innerWidth - bubbleSize() - 24, 0, Math.max(0, window.innerWidth - bubbleSize()));
  const top = clamp(hasTop ? pos.top : window.innerHeight - bubbleSize() - 24, 0, Math.max(0, window.innerHeight - bubbleSize()));
  button.style.left = `${left}px`;
  button.style.top = `${top}px`;
}

function loadBubblePosition() {
  try {
    return JSON.parse(localStorage.getItem(BUBBLE_POS_KEY));
  } catch {
    return null;
  }
}

function saveBubblePosition(pos) {
  try {
    localStorage.setItem(BUBBLE_POS_KEY, JSON.stringify(pos));
  } catch {
    // 無痕模式等情況寫不進去就算了，位置只是便利性。
  }
}

function toggleAutoMode() {
  if (state.autoTargets.length > 0 || state.autoArming) {
    terminateAllTasks();
    showStatus("已關閉頁碼翻譯，已終止所有進行中的翻譯", 1800);
    return;
  }
  state.autoArming = true;
  if (!state.picking) startPickMode();
  refreshBubbleTitle();
  showStatus("連續翻譯：點選漫畫顯示區域（可點多個，點泡泡確認）");
}

function stopAutoMode() {
  state.autoArming = false;
  state.autoTargets = [];
  state.autoTargetLastRects = [];
  state.autoBusy = false;
  _prefetchedKeys.clear();
  _predictedNext = "";
  _prefetchMisses = 0;
  _prefetchOff = false;
  window.clearTimeout(state.autoTimer);
}

// 任一開關（整頁翻譯／頁碼翻譯）關掉 → 終止目前所有任務：
// 停掉本地佇列與自動模式，並請背景把進行中的翻譯請求真的 abort 掉（不只是丟棄結果）。
function terminateAllTasks() {
  // 使用者主動關掉 → 連持久化的「啟用中」一起清掉，下次載入不再自動續抓。
  _autoPersistEnabled = false;
  _pagePersistEnabled = false;
  chromeSafeSet({ dmmtAutoEnabled: false, dmmtPageEnabled: false });
  stopPageTranslate();
  stopAutoMode();
  _pfProg = null;
  refreshBubbleTitle();
  try { sendMessage({ type: "abort-all-tasks" }).catch(() => {}); } catch {}
}

function confirmAutoTargets() {
  state.autoArming = false;
  stopPickMode();
  const count = state.autoTargets.length;
  _autoPersistEnabled = true;
  chromeSafeSet({ dmmtAutoEnabled: true, dmmtAutoOrigin: location.origin });
  showStatus(`連續翻譯已鎖定 ${count} 個區域，翻頁會自動翻譯`, 2500);
  runAutoTranslateAll();
}

function installAutoTriggers() {
  const trigger = (event) => {
    if (!state.autoTargets.length || state.picking) return;
    if (state.root?.contains(event.target)) return;
    scheduleAutoTranslate();
  };
  document.addEventListener("pointerup", trigger, true);
  document.addEventListener("keyup", (event) => {
    if (!state.autoTargets.length) return;
    if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "PageUp", "PageDown", " ", "Enter"].includes(event.key)) {
      scheduleAutoTranslate();
    }
  }, true);
  let wheelTimer = 0;
  document.addEventListener("wheel", () => {
    if (!state.autoTargets.length) return;
    window.clearTimeout(wheelTimer);
    wheelTimer = window.setTimeout(scheduleAutoTranslate, 450);
  }, true);
}

function scheduleAutoTranslate() {
  window.clearTimeout(state.autoTimer);
  state.autoTimer = window.setTimeout(runAutoTranslateAll, 600);
}

async function runAutoTranslateAll() {
  if (!state.autoTargets.length || state.autoBusy) return;
  state.autoBusy = true;
  const gen = state.autoGen;
  try {
    await Promise.all(state.autoTargets.map((target, i) => runAutoTranslateOne(target, i, gen)));
  } catch (error) {
    if (state.autoGen === gen) showStatus(`連續翻譯失敗：${error.message || error}`, 5000);
  } finally {
    if (state.autoGen === gen) state.autoBusy = false;
  }
}

async function runAutoTranslateOne(element, index, gen) {
  // 若元素已被移除（SPA 換頁），改用位置找最近的同類元素。
  if (!document.contains(element)) {
    const rect = state.autoTargetLastRects[index];
    if (rect) {
      const found = findImageCandidateAt(rect.left + rect.width / 2, rect.top + rect.height / 2)?.element;
      if (found) { state.autoTargets[index] = found; element = found; }
      else return;
    } else return;
  }

  const rect = getVisibleRect(element);
  if (rect.width < 24 || rect.height < 24) return;
  state.autoTargetLastRects[index] = rect;

  if (element.tagName?.toLowerCase() === "img") {
    await waitForImgLoad(element);
    if (state.autoGen !== gen) return; // 等待期間使用者已換頁，放棄此次翻譯。
  }

  // 先查快取再決定要不要重翻：currentSrc 與 src 屬性都當 key 試。
  // 上面已 waitForImgLoad，currentSrc 此時是「真正載入的新圖網址」（lazy-load 時 src 屬性常還是佔位圖），
  // 預抓快取是用真圖網址存的，所以必須連 currentSrc 一起比對，任一命中就直接套用、不重翻。
  if (element.tagName?.toLowerCase() === "img" && !state.replacements.has(element)) {
    const src = element.getAttribute("src") || "";
    if (src && !src.startsWith("data:")) {
      // 先用本頁網址驗證上一頁的預測，再排後面 10 頁預先翻譯。
      verifyPrefetchPrediction(src);
      schedulePrefetchNextPages(src);
    }
    const keys = [];
    const cs = element.currentSrc || "";
    if (cs && !cs.startsWith("data:")) keys.push(imgCacheKey(cs));
    if (src && !src.startsWith("data:")) {
      const k = imgCacheKey(src);
      if (!keys.includes(k)) keys.push(k);
    }
    if (keys.length) {
      const stored = await new Promise((resolve) => chromeSafeGet(keys, resolve));
      if (state.autoGen !== gen) return;
      const hitKey = keys.find((k) => stored?.[k]?.image);
      if (hitKey) {
        replaceImgElement(element, stored[hitKey].image);
        return;
      }
    }
  }

  if (state.autoGen !== gen) return;
  await translateRect(rect, element);
}

function waitForImgLoad(img) {
  if (img.complete && img.naturalWidth > 0) return Promise.resolve();
  return new Promise((resolve) => {
    const done = () => {
      img.removeEventListener("load", done);
      img.removeEventListener("error", done);
      resolve();
    };
    img.addEventListener("load", done);
    img.addEventListener("error", done);
    window.setTimeout(resolve, 5000);
  });
}

function togglePickMode() {
  // 框選翻譯：編輯中 → 點泡泡＝合併翻譯並記住位置；已記住位置 → 點泡泡＝重翻同位置。
  if (state.boxEditing) { finalizeBoxEditing(); return; }
  if (_boxMode && _boxRects.length && !state.picking) { translateBoxRects(_boxRects); return; }
  if (state.picking) {
    // 若已選了目標，點泡泡 = 確認；若尚未選，點泡泡 = 取消。
    if (state.autoArming && state.autoTargets.length > 0) {
      confirmAutoTargets();
    } else {
      stopPickMode();
      if (state.autoArming) stopAutoMode();
    }
  } else {
    startPickMode();
  }
}

function startPickMode() {
  clearOverlays();
  state.picking = true;
  state.currentCandidate = null;
  state.button.classList.add("dmmt-ext-active");
  state.button.textContent = "✕";
  showStatus("移到圖片上會高亮，點一下開始翻譯，按 Esc 取消");

  state.layer = document.createElement("div");
  state.layer.className = "dmmt-ext-pick-layer";
  state.layer.addEventListener("pointermove", onPickPointerMove);
  state.layer.addEventListener("click", onPickClick);
  state.root.append(state.layer);
}

function stopPickMode() {
  state.picking = false;
  state.currentCandidate = null;
  state.button.classList.remove("dmmt-ext-active");
  state.button.textContent = state.bubblePrefs.label;
  state.layer?.remove();
  state.layer = null;
  hideHighlight();
  hideStatus();
}

function onPickPointerMove(event) {
  if (!state.picking) return;
  event.preventDefault();
  const candidate = findImageCandidateAt(event.clientX, event.clientY);
  state.currentCandidate = candidate;
  if (candidate) {
    showHighlight(candidate);
  } else {
    hideHighlight();
  }
}

function onPickClick(event) {
  if (!state.picking) return;
  event.preventDefault();
  event.stopPropagation();

  const candidate = findImageCandidateAt(event.clientX, event.clientY) || state.currentCandidate;
  if (!candidate) {
    showStatus("這裡找不到可截圖的圖片或漫畫畫布", 2400);
    return;
  }

  // 框選翻譯編輯模式：點一下加入格子、再點一下取消。
  if (state.boxEditing) { toggleBoxRect(candidate); return; }

  const rect = candidate.rect;
  const arming = state.autoArming;

  if (arming) {
    // 加入目標陣列，保持選取模式讓使用者繼續選。
    state.autoTargets.push(candidate.element);
    state.autoTargetLastRects.push(rect);
    const n = state.autoTargets.length;
    showStatus(`已選 ${n} 個區域，繼續點選可新增，點「${state.bubblePrefs.label}」泡泡完成`);
    translateRect(rect, candidate.element).catch((error) => {
      showStatus(`圖片翻譯失敗：${error.message || error}`, 8000);
    });
    return;
  }

  stopPickMode();

  if (state.replacements.has(candidate.element)) {
    restoreInPlaceReplacement(candidate.element);
    hideStatus();
    return;
  }

  translateRect(rect, candidate.element).catch((error) => {
    showStatus(`圖片翻譯失敗：${error.message || error}`, 8000);
  });
}

// ===== 框選翻譯（防盜分割圖）=====
// 選被拆分的格子 → 各自截圖 → 依位置合併成一張 → 翻譯 → 覆蓋回整片。
// 位置記住（綁定網站），之後每換一頁點「譯」泡泡就重翻同位置。
let _boxMode = false;   // 框選翻譯啟用中（持久化）
let _boxRects = [];     // 已記住的格子位置（viewport 座標）
let _pageIdx = 0;            // 合併翻譯：目前第幾頁（相對起點），供滾輪翻頁的快取對應
const _boxCache = new Map(); // pageIdx → { image, union }：翻好的結果，滾回來時重貼回去

function toggleBoxMode() {
  if (_boxMode || state.boxEditing) {
    stopBoxEditing();
    _boxMode = false;
    _boxRects = [];
    chromeSafeSet({ dmmtBoxMode: false });
    showStatus("已關閉框選翻譯", 1500);
    return;
  }
  _boxMode = true;
  startBoxEditing();
}

function startBoxEditing() {
  clearOverlays();
  _pageIdx = 0;       // 重新框選 = 新的一輪，頁碼歸零、清掉舊翻譯快取
  _boxCache.clear();
  state.boxEditing = true;
  state.picking = true;
  state.boxSel = [];
  state.currentCandidate = null;
  state.button.classList.add("dmmt-ext-active");
  state.button.textContent = "✕";
  showStatus("點選被拆分的漫畫格子（再點一次取消），選好點「譯」泡泡＝合併翻譯並記住位置");
  for (const r of _boxRects) addBoxEl(r, null); // 用上次記住的位置先框起來，方便微調
  state.layer = document.createElement("div");
  state.layer.className = "dmmt-ext-pick-layer";
  state.layer.addEventListener("pointermove", onPickPointerMove);
  state.layer.addEventListener("click", onPickClick);
  state.root.append(state.layer);
}

function stopBoxEditing() {
  state.boxEditing = false;
  state.picking = false;
  state.currentCandidate = null;
  state.button.classList.remove("dmmt-ext-active");
  state.button.textContent = state.bubblePrefs.label;
  for (const s of (state.boxSel || [])) s.box?.remove();
  state.boxSel = [];
  state.layer?.remove();
  state.layer = null;
  hideHighlight();
  hideStatus();
}

function addBoxEl(rect, element) {
  const box = document.createElement("div");
  box.className = "dmmt-ext-selbox";
  Object.assign(box.style, { left: `${rect.left}px`, top: `${rect.top}px`, width: `${rect.width}px`, height: `${rect.height}px` });
  state.root.append(box);
  (state.boxSel = state.boxSel || []).push({ element, rect, box });
  renumberBoxes();
}

function renumberBoxes() {
  (state.boxSel || []).forEach((s, k) => { if (s.box) s.box.setAttribute("data-n", String(k + 1)); });
}

function toggleBoxRect(candidate) {
  const sel = state.boxSel || (state.boxSel = []);
  const i = sel.findIndex((s) => (s.element && s.element === candidate.element) || rectsOverlapRatio(s.rect, candidate.rect) > 0.6);
  if (i >= 0) {
    sel[i].box?.remove();
    sel.splice(i, 1);
    renumberBoxes();
  } else {
    addBoxEl(candidate.rect, candidate.element);
  }
  showStatus(`已選 ${sel.length} 格，點「譯」泡泡＝合併翻譯`);
}

async function finalizeBoxEditing() {
  const rects = (state.boxSel || []).map((s) => s.rect);
  stopBoxEditing();
  if (!rects.length) {
    _boxMode = false;
    chromeSafeSet({ dmmtBoxMode: false });
    showStatus("沒有選任何格子", 2000);
    return;
  }
  _boxRects = rects;
  _boxMode = true;
  chromeSafeSet({ dmmtBoxMode: true, dmmtBoxOrigin: location.origin, dmmtBoxRects: rects });
  await translateBoxRects(rects);
}

async function translateBoxRects(rects) {
  if (!rects || !rects.length) return;
  showProgress(`截取 ${rects.length} 格`);
  state.root.classList.add("dmmt-ext-capture-hidden");
  await waitForPaint();
  const parts = [];
  try {
    for (const r of rects) {
      const crop = await sendMessage({ type: "capture-crop", rect: r, viewport: { width: window.innerWidth, height: window.innerHeight } });
      if (crop?.image) parts.push({ rect: r, image: crop.image });
    }
  } finally {
    state.root.classList.remove("dmmt-ext-capture-hidden");
  }
  if (!parts.length) { showStatus("截圖失敗", 3000); hideProgressSoon(); return; }
  try {
    const minL = Math.min(...parts.map((p) => p.rect.left));
    const minT = Math.min(...parts.map((p) => p.rect.top));
    const maxR = Math.max(...parts.map((p) => p.rect.left + p.rect.width));
    const maxB = Math.max(...parts.map((p) => p.rect.top + p.rect.height));
    const bmps = await Promise.all(parts.map((p) => loadImage(p.image)));
    const scale = (bmps[0]?.width || parts[0].rect.width) / (parts[0].rect.width || 1); // 截圖像素 / CSS px
    const W = Math.max(1, Math.round((maxR - minL) * scale));
    const H = Math.max(1, Math.round((maxB - minT) * scale));
    const canvas = document.createElement("canvas");
    canvas.width = W; canvas.height = H;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, W, H);
    parts.forEach((p, k) => {
      ctx.drawImage(bmps[k], Math.round((p.rect.left - minL) * scale), Math.round((p.rect.top - minT) * scale));
    });
    const composite = canvas.toDataURL("image/png");
    showProgress("翻譯中");
    const resp = await sendMessage({ type: "translate-data-url", image: composite });
    const union = { left: minL, top: minT, width: maxR - minL, height: maxB - minT };
    addResultOverlay(resp.image, union, null, null);
    _boxCache.set(_pageIdx, { image: resp.image, union }); // 記住這頁翻譯，滾回來能重貼
    if (_boxCache.size > 30) _boxCache.delete(_boxCache.keys().next().value);
    hideStatus();
  } catch (e) {
    showStatus(`框選翻譯失敗：${e.message || e}`, 6000);
  } finally {
    hideProgressSoon();
  }
}

function findImageCandidateAt(x, y) {
  const stack = document.elementsFromPoint(x, y)
    .filter((element) => element !== state.layer && !state.root.contains(element) && isVisibleElement(element));

  const direct = smallestCandidate(stack.map(candidateFromElement).filter(Boolean), x, y);
  if (direct) return direct;

  const nested = [];
  for (const element of stack) {
    for (const child of element.querySelectorAll?.("img, canvas, picture, svg") || []) {
      const candidate = candidateFromElement(child);
      if (candidate) nested.push(candidate);
    }
  }
  const nestedCandidate = smallestCandidate(nested, x, y);
  if (nestedCandidate) return nestedCandidate;

  const background = smallestCandidate(stack.map(candidateFromBackground).filter(Boolean), x, y);
  if (background) return background;

  const documentCandidates = [];
  for (const element of document.querySelectorAll("img, canvas, picture, svg")) {
    const candidate = candidateFromElement(element);
    if (candidate) documentCandidates.push(candidate);
  }
  return smallestCandidate(documentCandidates, x, y);
}

function candidateFromElement(element) {
  if (!element || !isVisibleElement(element)) return null;
  const tagName = element.tagName?.toLowerCase();
  if (!["img", "canvas", "picture", "svg"].includes(tagName)) return null;
  const rect = getVisibleRect(element);
  if (rect.width < 24 || rect.height < 24) return null;
  return { element, rect, label: tagName };
}

function candidateFromBackground(element) {
  if (!element || !isVisibleElement(element)) return null;
  const bg = getComputedStyle(element).backgroundImage;
  if (!bg || bg === "none" || !/url\(/.test(bg)) return null;
  const rect = getVisibleRect(element);
  if (rect.width < 24 || rect.height < 24) return null;
  return { element, rect, label: "background" };
}

function smallestCandidate(candidates, x, y) {
  return candidates
    .filter((candidate) => rectContainsPoint(candidate.rect, x, y))
    .sort((a, b) => rectArea(a.rect) - rectArea(b.rect))[0] || null;
}

function showHighlight(candidate) {
  const rect = candidate.rect;
  Object.assign(state.highlight.style, {
    left: `${rect.left}px`,
    top: `${rect.top}px`,
    width: `${rect.width}px`,
    height: `${rect.height}px`
  });

  state.label.textContent = `${Math.round(rect.width)} x ${Math.round(rect.height)} ${candidate.label}`;
  Object.assign(state.label.style, {
    left: `${Math.max(8, rect.left)}px`,
    top: `${Math.max(8, rect.top - 28)}px`
  });
  state.highlight.classList.remove("dmmt-ext-hidden");
  state.label.classList.remove("dmmt-ext-hidden");
}

function hideHighlight() {
  state.highlight.classList.add("dmmt-ext-hidden");
  state.label.classList.add("dmmt-ext-hidden");
}

function isVisibleElement(element) {
  const style = getComputedStyle(element);
  if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) return false;
  const rect = element.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

function getVisibleRect(element) {
  const rect = element.getBoundingClientRect();
  const left = clamp(rect.left, 0, window.innerWidth);
  const top = clamp(rect.top, 0, window.innerHeight);
  const right = clamp(rect.right, 0, window.innerWidth);
  const bottom = clamp(rect.bottom, 0, window.innerHeight);
  return {
    left,
    top,
    width: Math.max(0, right - left),
    height: Math.max(0, bottom - top)
  };
}

function rectContainsPoint(rect, x, y) {
  return rect.width > 0 && rect.height > 0 &&
    x >= rect.left && x <= rect.left + rect.width &&
    y >= rect.top && y <= rect.top + rect.height;
}

function rectArea(rect) {
  return rect.width * rect.height;
}

// 兩矩形的交集面積佔「較小矩形」面積的比例，用來判斷是否為同一塊翻譯區域。
function rectsOverlapRatio(a, b) {
  const left = Math.max(a.left, b.left);
  const top = Math.max(a.top, b.top);
  const right = Math.min(a.left + a.width, b.left + b.width);
  const bottom = Math.min(a.top + a.height, b.top + b.height);
  const iw = right - left;
  const ih = bottom - top;
  if (iw <= 0 || ih <= 0) return 0;
  const inter = iw * ih;
  const smaller = Math.min(rectArea(a), rectArea(b)) || 1;
  return inter / smaller;
}

function clamp(value, min, max) {
  return Math.min(Math.max(Number(value), min), max);
}

// 圖片若有部分被捲出畫面，先捲到完整顯示再截圖；圖比視窗大時無法完整顯示，提示使用者縮小頁面。
async function ensureFullyVisible(element) {
  if (!element || !document.contains(element)) return;
  const r = element.getBoundingClientRect();
  const fullyVisible = r.left >= -2 && r.top >= -2 &&
    r.right <= window.innerWidth + 2 && r.bottom <= window.innerHeight + 2;
  if (fullyVisible) return;
  if (r.height > window.innerHeight || r.width > window.innerWidth) {
    showStatus("圖片超出畫面，僅翻可見範圍；可用 Ctrl+- 縮小頁面後再翻完整圖", 4000);
    return;
  }
  element.scrollIntoView({ block: "center", inline: "center" });
  await waitForPaint();
  await waitForPaint();
}

async function translateRect(rect, targetElement) {
  showProgress("處理中"); // 立即顯示進度，避免取得原圖期間畫面看似沒反應
  // 最佳路徑：能讀到像素的 <img> 直接用「原始解析度」翻譯，畫質等同把原圖複製貼到網頁，
  // 不走截圖（截圖只有螢幕解析度，顯示縮小時細節大量流失，OCR/翻譯品質會差很多）。
  if (targetElement?.tagName?.toLowerCase() === "img") {
    const fullRes = await getFullResImageDataUrl(targetElement);
    if (fullRes) {
      await reportDiag(_imgDiag, fullRes);
      await translateImgFullRes(targetElement, fullRes);
      return;
    }
    // 讀不到像素（跨域防盜圖且不給 CORS）才退回截圖路徑。
  }
  // 先確保圖片完整顯示，再以最新位置重新取得截圖區域。
  if (targetElement) {
    await ensureFullyVisible(targetElement);
    const fresh = getVisibleRect(targetElement);
    if (fresh.width >= 24 && fresh.height >= 24) rect = fresh;
  }
  // 在「截圖當下」記錄翻譯區域相對於目標元素的偏移。翻譯需數秒，期間頁面可能捲動，
  // 套用覆蓋層時改用「元素目前位置 + 此偏移」定位，避免貼到舊的視窗座標（pixiv 等）。
  let anchor = null;
  if (targetElement?.getBoundingClientRect) {
    const er = targetElement.getBoundingClientRect();
    anchor = { offsetX: rect.left - er.left, offsetY: rect.top - er.top, w: rect.width, h: rect.height };
  }
  // 記錄翻譯開始當下的網址與元素 src，套用時雙重確認仍是同一頁同一張圖。
  const pageToken = location.href;
  // img 元素的 src；canvas/background 為 null（不做元素層級比對）。
  const srcToken = targetElement?.tagName?.toLowerCase() === "img"
    ? (targetElement.getAttribute("src") || "")
    : null;
  showProgress("截圖中");
  try {
    const response = await captureAndTranslateWithoutExtensionUi(rect);
    // URL 已換（有些閱讀器翻頁時更新 hash/pathname）。
    if (location.href !== pageToken) return;
    // SPA 閱讀器翻頁：URL 不變但已把 img src 換成下一張圖。
    if (srcToken !== null) {
      const currentSrc = targetElement.getAttribute("src") || "";
      if (currentSrc !== srcToken && !currentSrc.startsWith("data:")) return;
    }
    showProgress("套用翻譯圖");
    const replaced = await applyInPlaceReplacement(targetElement, response.image, rect);
    if (replaced) {
      hideStatus();
    } else {
      addResultOverlay(response.image, rect, targetElement, anchor);
    }
  } finally {
    hideProgressSoon();
  }
}

// 偵錯：把實際要送給 OCR 的圖下載下來，方便和手動截圖比對。
function maybeDumpInput(dataUrl) {
  try {
    chromeSafeGet("dmmtDebugInput", (s) => {
      if (s?.dmmtDebugInput) downloadDataUrl(dataUrl, "dmmt-sent-to-ocr.png");
    });
  } catch {}
}

// 用原解析度的圖片像素直接翻譯並原地替換（畫質最佳路徑）。
async function translateImgFullRes(img, dataUrl) {
  const pageToken = location.href;
  const srcToken = img.getAttribute("src") || "";
  maybeDumpInput(dataUrl);
  showProgress("翻譯中");
  try {
    const resp = await sendMessage({ type: "translate-data-url", image: dataUrl });
    // 翻譯期間若已換頁或換圖就放棄，避免貼錯。
    if (location.href !== pageToken) return;
    const curSrc = img.getAttribute("src") || "";
    if (curSrc !== srcToken && !curSrc.startsWith("data:")) return;
    if (!state.replacements.has(img) && document.contains(img)) {
      replaceImgElement(img, resp.image);
    }
    hideStatus();
  } finally {
    hideProgressSoon();
  }
}

async function captureAndTranslateWithoutExtensionUi(rect) {
  state.root.classList.add("dmmt-ext-capture-hidden");
  await waitForPaint();
  let crop;
  try {
    crop = await sendMessage({
      type: "capture-crop",
      rect,
      viewport: {
        width: window.innerWidth,
        height: window.innerHeight
      }
    });
  } finally {
    state.root.classList.remove("dmmt-ext-capture-hidden");
  }

  await reportDiag("截圖" + (_imgDiag ? `（無法取原圖：${_imgDiag}）` : ""), crop.image);
  maybeDumpInput(crop.image);
  showProgress("翻譯中");
  return sendMessage({
    type: "translate-data-url",
    image: crop.image
  });
}

function waitForPaint() {
  return new Promise((resolve) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(resolve);
    });
  });
}

async function applyInPlaceReplacement(element, dataUrl, rect) {
  if (!element || !document.contains(element)) return false;
  if (!isFullyInViewport(element, rect)) return false;

  const tagName = element.tagName?.toLowerCase();
  try {
    if (tagName === "img") return replaceImgElement(element, dataUrl);
    if (tagName === "canvas") return await replaceCanvasElement(element, dataUrl);
    if (getComputedStyle(element).backgroundImage !== "none") return replaceBackgroundElement(element, dataUrl);
  } catch {
    return false;
  }
  return false;
}

function isFullyInViewport(element, capturedRect) {
  const rect = element.getBoundingClientRect();
  const tolerance = 2;
  return rect.left >= -tolerance &&
    rect.top >= -tolerance &&
    rect.right <= window.innerWidth + tolerance &&
    rect.bottom <= window.innerHeight + tolerance &&
    Math.abs(rect.width - capturedRect.width) <= tolerance * 2 &&
    Math.abs(rect.height - capturedRect.height) <= tolerance * 2;
}

function replaceImgElement(img, dataUrl) {
  if (state.replacements.has(img)) return false;

  // 在改 src 之前先記下「真正顯示的圖片網址」當快取依據（lazy-load 用 currentSrc）。
  const cacheUrl = bestImageUrl(img);

  const record = {
    kind: "img",
    src: img.getAttribute("src"),
    srcset: img.getAttribute("srcset"),
    sizes: img.getAttribute("sizes"),
    sources: [],
    observer: null,
    cacheUrl, // 快取 key 用的真實網址
    dataUrl // 翻譯圖，供「顯示原圖／翻譯圖」切換用
  };

  const picture = img.parentElement?.tagName?.toLowerCase() === "picture" ? img.parentElement : null;
  if (picture) {
    for (const source of picture.querySelectorAll("source")) {
      record.sources.push({ source, srcset: source.getAttribute("srcset") });
      source.removeAttribute("srcset");
    }
  }

  img.removeAttribute("srcset");
  img.removeAttribute("sizes");
  img.addEventListener("error", function onError() {
    img.removeEventListener("error", onError);
    if (state.replacements.get(img) === record) {
      restoreInPlaceReplacement(img);
      showStatus("此網站不允許原地替換，請改用覆蓋模式", 4000);
    }
  });
  img.src = dataUrl;

  record.observer = new MutationObserver(() => {
    const current = img.getAttribute("src");
    if (current === dataUrl) return;
    if (current === record.src || !current) {
      img.removeAttribute("srcset");
      img.src = dataUrl;
    } else {
      record.observer.disconnect();
      state.replacements.delete(img);
    }
  });
  record.observer.observe(img, { attributes: true, attributeFilter: ["src", "srcset"] });

  state.replacements.set(img, record);
  saveTranslationToImgCache(record.cacheUrl || record.src, dataUrl);
  // 全域檢視為「顯示原圖」時，這張剛翻好的也立即回到原圖（記錄保留，切回翻譯圖會套用）。
  if (state.viewMode === "original") _setRecordView(img, record, true);
  return true;
}

async function replaceCanvasElement(canvas, dataUrl) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return false;

  let snapshot = null;
  try {
    snapshot = canvas.toDataURL("image/png");
  } catch {
    // Canvas 被跨域內容污染時無法快照，仍然替換但無法還原像素。
  }

  const bitmap = await loadImage(dataUrl);
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  const record = { kind: "canvas", snapshot, dataUrl };
  state.replacements.set(canvas, record);
  if (state.viewMode === "original") _setRecordView(canvas, record, true);
  return true;
}

function replaceBackgroundElement(element, dataUrl) {
  const record = {
    kind: "background",
    backgroundImage: element.style.backgroundImage,
    backgroundSize: element.style.backgroundSize,
    backgroundRepeat: element.style.backgroundRepeat,
    backgroundPosition: element.style.backgroundPosition,
    dataUrl
  };
  state.replacements.set(element, record);
  element.style.backgroundImage = `url("${dataUrl}")`;
  element.style.backgroundSize = "100% 100%";
  element.style.backgroundRepeat = "no-repeat";
  element.style.backgroundPosition = "0 0";
  if (state.viewMode === "original") _setRecordView(element, record, true);
  return true;
}

function restoreInPlaceReplacement(element, dropCache = true) {
  const record = state.replacements.get(element);
  if (!record) return;
  state.replacements.delete(element);

  if (record.kind === "img") {
    record.observer?.disconnect();
    if (dropCache) dropImgCacheEntry(record.cacheUrl || record.src);
    if (record.srcset !== null) element.setAttribute("srcset", record.srcset);
    if (record.sizes !== null) element.setAttribute("sizes", record.sizes);
    if (record.src !== null) element.setAttribute("src", record.src);
    else element.removeAttribute("src");
    for (const { source, srcset } of record.sources) {
      if (srcset !== null) source.setAttribute("srcset", srcset);
    }
  } else if (record.kind === "canvas") {
    if (record.snapshot) {
      loadImage(record.snapshot).then((bitmap) => {
        element.getContext("2d")?.drawImage(bitmap, 0, 0, element.width, element.height);
      }).catch(() => {});
    }
  } else if (record.kind === "background") {
    element.style.backgroundImage = record.backgroundImage;
    element.style.backgroundSize = record.backgroundSize;
    element.style.backgroundRepeat = record.backgroundRepeat;
    element.style.backgroundPosition = record.backgroundPosition;
  }
}

function releaseAllReplacements() {
  for (const element of Array.from(state.replacements.keys())) {
    // 換頁清理不刪快取——切回這頁時快取掃描器會自動復原。
    restoreInPlaceReplacement(element, false);
  }
}

// 把單一替換記錄切到原圖或翻譯圖（只改顯示，記錄保留，可重複切換）。
function _setRecordView(element, record, showOriginal) {
  if (record.kind === "img") {
    if (showOriginal) {
      record.observer?.disconnect();
      if (record.srcset !== null) element.setAttribute("srcset", record.srcset);
      if (record.sizes !== null) element.setAttribute("sizes", record.sizes);
      if (record.src !== null) element.setAttribute("src", record.src);
      for (const { source, srcset } of record.sources) {
        if (srcset !== null) source.setAttribute("srcset", srcset);
      }
    } else {
      element.removeAttribute("srcset");
      element.removeAttribute("sizes");
      for (const { source } of record.sources) source.removeAttribute("srcset");
      element.src = record.dataUrl;
      record.observer?.observe(element, { attributes: true, attributeFilter: ["src", "srcset"] });
    }
  } else if (record.kind === "canvas") {
    const img = showOriginal ? record.snapshot : record.dataUrl;
    if (img) {
      loadImage(img).then((bitmap) => {
        element.getContext("2d")?.drawImage(bitmap, 0, 0, element.width, element.height);
      }).catch(() => {});
    }
  } else if (record.kind === "background") {
    if (showOriginal) {
      element.style.backgroundImage = record.backgroundImage;
      element.style.backgroundSize = record.backgroundSize;
      element.style.backgroundRepeat = record.backgroundRepeat;
      element.style.backgroundPosition = record.backgroundPosition;
    } else {
      element.style.backgroundImage = `url("${record.dataUrl}")`;
      element.style.backgroundSize = "100% 100%";
      element.style.backgroundRepeat = "no-repeat";
      element.style.backgroundPosition = "0 0";
    }
  }
}

// 把單一覆蓋層切到顯示/隱藏（原圖模式藏覆蓋層、露出原元素）。
function _setOverlayView(holder, showOriginal) {
  const target = holder.__dmmtTargetElement;
  if (showOriginal) {
    holder.style.display = "none";
    if (target?.style) {
      target.style.visibility = holder.__dmmtPreviousInlineVisibility || "";
      target.style.opacity = holder.__dmmtPreviousInlineOpacity || "";
    }
  } else {
    holder.style.display = "";
    if (target?.style) {
      target.style.visibility = "hidden";
      target.style.opacity = "0";
    }
  }
}

// 「顯示原圖／顯示翻譯圖」是全域狀態：切換時套用到所有現有記錄；
// 新翻譯的圖也會在套用當下遵守目前模式（見 replaceImgElement / addResultOverlay 等）。
function toggleViewMode() {
  setViewMode(state.viewMode === "translated" ? "original" : "translated");
}

function setViewMode(mode) {
  state.viewMode = mode;
  const showOriginal = mode === "original";
  for (const [element, record] of Array.from(state.replacements)) {
    _setRecordView(element, record, showOriginal);
  }
  for (const holder of Array.from(state.overlays)) {
    _setOverlayView(holder, showOriginal);
  }
  showStatus(showOriginal ? "已切換為原圖" : "已切換為翻譯圖", 1500);
}

function loadImage(dataUrl) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("圖片載入失敗"));
    img.src = dataUrl;
  });
}

function addResultOverlay(dataUrl, rect, targetElement, anchor) {
  // 以「元素目前位置 + 截圖當下記錄的偏移」決定實際擺放位置；翻譯期間有捲動也不會貼歪。
  let place = { left: rect.left, top: rect.top, width: rect.width, height: rect.height };
  if (anchor && targetElement?.getBoundingClientRect) {
    const er = targetElement.getBoundingClientRect();
    place = {
      left: er.left + anchor.offsetX,
      top: er.top + anchor.offsetY,
      width: anchor.w,
      height: anchor.h
    };
  }

  // 避免重複疊圖：移除指向同一元素、或與新區域明顯重疊的舊覆蓋層。
  for (const old of Array.from(state.overlays)) {
    if (old.__dmmtTargetElement && old.__dmmtTargetElement === targetElement) {
      removeOverlay(old);
      continue;
    }
    const oldRect = old.getBoundingClientRect();
    if (rectsOverlapRatio(oldRect, place) > 0.5) {
      removeOverlay(old);
    }
  }

  const holder = document.createElement("div");
  holder.className = "dmmt-ext-result";
  Object.assign(holder.style, {
    left: `${place.left}px`,
    top: `${place.top}px`,
    width: `${place.width}px`,
    height: `${place.height}px`
  });

  // 記錄偏移供滾動時重新定位：優先用截圖當下的 anchor（最準），否則用目前位置推算。
  if (anchor) {
    holder.__dmmtOffsetX = anchor.offsetX;
    holder.__dmmtOffsetY = anchor.offsetY;
    holder.__dmmtCapW = anchor.w;
    holder.__dmmtCapH = anchor.h;
  } else if (targetElement?.getBoundingClientRect) {
    const tr = targetElement.getBoundingClientRect();
    holder.__dmmtOffsetX = rect.left - tr.left;
    holder.__dmmtOffsetY = rect.top - tr.top;
    holder.__dmmtCapW = rect.width;
    holder.__dmmtCapH = rect.height;
  }

  const tools = document.createElement("div");
  tools.className = "dmmt-ext-tools";

  const download = document.createElement("button");
  download.className = "dmmt-ext-icon";
  download.type = "button";
  download.textContent = "DL";
  download.title = "下載翻譯圖";
  download.addEventListener("click", () => {
    const a = document.createElement("a");
    a.href = dataUrl;
    a.download = "manga-selection-translated.png";
    a.click();
  });

  const close = document.createElement("button");
  close.className = "dmmt-ext-icon";
  close.type = "button";
  close.textContent = "X";
  close.title = "移除翻譯圖";
  close.addEventListener("click", () => {
    removeOverlay(holder);
  });

  const img = document.createElement("img");
  img.alt = "Translated manga selection";
  img.addEventListener("load", () => {
    showStatus("翻譯完成，已覆蓋到原位置", 1800);
  }, { once: true });
  img.addEventListener("error", () => {
    showStatus("翻譯完成但圖片載入失敗", 5000);
  }, { once: true });
  img.src = dataUrl;

  tools.append(download, close);
  holder.append(tools, img);
  attachReplacementTarget(holder, targetElement);
  state.overlays.add(holder);
  state.root.append(holder);
  // 全域檢視為「顯示原圖」時，剛建立的覆蓋層也立即隱藏、露出原圖。
  if (state.viewMode === "original") _setOverlayView(holder, true);
}

function attachReplacementTarget(holder, targetElement) {
  if (!targetElement || !targetElement.style) return;
  holder.__dmmtTargetElement = targetElement;
  holder.__dmmtPreviousInlineVisibility = targetElement.style.visibility;
  holder.__dmmtPreviousInlineOpacity = targetElement.style.opacity;
  holder.__dmmtPreviousInlinePointerEvents = targetElement.style.pointerEvents;
  targetElement.style.visibility = "hidden";
  targetElement.style.opacity = "0";
  targetElement.style.pointerEvents = "none";
}

function restoreReplacementTarget(holder) {
  const targetElement = holder.__dmmtTargetElement;
  if (!targetElement?.style) return;
  targetElement.style.visibility = holder.__dmmtPreviousInlineVisibility || "";
  targetElement.style.opacity = holder.__dmmtPreviousInlineOpacity || "";
  targetElement.style.pointerEvents = holder.__dmmtPreviousInlinePointerEvents || "";
}

function removeOverlay(overlay) {
  restoreReplacementTarget(overlay);
  overlay.remove();
  state.overlays.delete(overlay);
}

function clearOverlays() {
  for (const overlay of Array.from(state.overlays)) {
    removeOverlay(overlay);
  }
}

// 滾輪翻頁：模擬方向鍵給閱讀器。日漫多為右到左 → 下一張＝ArrowLeft、上一張＝ArrowRight（方向相反跟我說就對調）。
function navigatePage(dir) {
  const next = dir === "next";
  let key, kc;
  if (_wheelDir === "ltr") { key = next ? "ArrowRight" : "ArrowLeft"; kc = next ? 39 : 37; }
  else if (_wheelDir === "vertical") { key = next ? "ArrowDown" : "ArrowUp"; kc = next ? 40 : 38; }
  else { key = next ? "ArrowLeft" : "ArrowRight"; kc = next ? 37 : 39; } // rtl 預設（日漫右到左）
  const init = { key, code: key, keyCode: kc, which: kc, bubbles: true, cancelable: true };
  for (const target of [document, document.body, document.documentElement]) {
    try {
      target?.dispatchEvent(new KeyboardEvent("keydown", init));
      target?.dispatchEvent(new KeyboardEvent("keyup", init));
    } catch {}
  }
}

function installNavigationCleanup() {
  document.addEventListener("pointerdown", clearBeforeViewerInteraction, true);
  document.addEventListener("touchstart", clearBeforeViewerInteraction, true);
  document.addEventListener("keydown", (event) => {
    if (state.picking && event.key === "Escape") {
      event.preventDefault();
      stopPickMode();
      if (state.autoArming) { stopAutoMode(); }
      return;
    }
    // 方向鍵/翻頁鍵只在連續翻譯（閱讀器）模式下清除覆蓋層；
    // 一般靜態頁面（如 pixiv）滾動時讓覆蓋層跟著圖片移動，不清掉。
    if (state.autoTargets.length &&
        ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "PageUp", "PageDown", " ", "Enter"].includes(event.key)) {
      clearOverlays();
    }
  }, true);
  // 滾動時重新定位覆蓋層，使翻譯圖跟著原圖移動而非被清除。
  window.addEventListener("scroll", repositionOverlays, true);
  // 視窗縮放會讓原圖尺寸改變、翻譯圖無法對齊，直接清除。
  window.addEventListener("resize", clearOverlays, true);

  // 滾輪翻頁（配合合併翻譯）：開啟後滾輪往下＝下一張、往上＝上一張，模擬方向鍵給被鎖住的閱讀器。
  let wheelNavTime = 0;
  window.addEventListener("wheel", (event) => {
    if (!_wheelNav) return;
    event.preventDefault();
    const now = Date.now();
    if (now - wheelNavTime < 220) return; // 一次滾動只翻一張
    wheelNavTime = now;
    clearOverlays();   // 翻頁前清掉目前頁卡在中心的翻譯覆蓋層
    const goNext = event.deltaY > 0;
    _pageIdx += goNext ? 1 : -1;
    navigatePage(goNext ? "next" : "prev");
    // 這頁先前翻過 → 換頁後把翻譯重新貼回（滾回上一頁不會不見）
    const cached = _boxCache.get(_pageIdx);
    if (cached) window.setTimeout(() => { if (_wheelNav) addResultOverlay(cached.image, cached.union, null, null); }, 250);
  }, { passive: false, capture: true });

  let navFastScanId = 0;
  function boostScannerAfterNav() {
    // 換頁後短暫開啟高頻掃描窗口，讓快取圖片能在圖片載入後立即復原。
    window.clearInterval(navFastScanId);
    let ticks = 0;
    navFastScanId = window.setInterval(() => {
      scanAndApplyImgCache();
      if (++ticks >= 20) window.clearInterval(navFastScanId); // 最多掃 20 次（約 2.4s）
    }, 120);
  }

  const cleanupForUrlChange = () => {
    window.setTimeout(() => {
      state.autoGen++;      // 讓進行中的舊頁翻譯結束後不套用到新頁。
      state.autoBusy = false; // 讓新頁的連續翻譯可以立即啟動。
      clearOverlays();
      releaseAllReplacements();
      // 立即掃快取並開高頻窗口，讓切回已翻頁面時盡快復原。
      scanAndApplyImgCache();
      boostScannerAfterNav();
      // 換頁後也重新確認當前頁、往後續抓（讓預先翻譯頁數隨閱讀進度滑動；全重載站點則靠 init 的 resumePrefetchOnLoad）。
      if (_autoPersistEnabled || _pagePersistEnabled) kickResumePrefetch(PREFETCH_TO_END_CAP, 0);
      if (state.autoTargets.length) {
        const anyFound = state.autoTargets.some((_, i) => {
          const rect = state.autoTargetLastRects[i];
          return rect && findImageCandidateAt(rect.left + rect.width / 2, rect.top + rect.height / 2);
        });
        if (!anyFound) stopAutoMode();
        else scheduleAutoTranslate();
      }
    }, 40);
  };
  const originalPushState = history.pushState;
  const originalReplaceState = history.replaceState;
  history.pushState = function (...args) {
    const result = originalPushState.apply(this, args);
    cleanupForUrlChange();
    return result;
  };
  history.replaceState = function (...args) {
    const result = originalReplaceState.apply(this, args);
    cleanupForUrlChange();
    return result;
  };
  window.addEventListener("popstate", cleanupForUrlChange, true);
  window.addEventListener("hashchange", cleanupForUrlChange, true);
}

function clearBeforeViewerInteraction(event) {
  // 只在連續翻譯（閱讀器）模式下，互動時清除覆蓋層；靜態頁面保留並跟隨。
  if (!state.overlays.size || state.picking || !state.autoTargets.length) return;
  if (state.root?.contains(event.target)) return;
  if (event.target.closest?.(".dmmt-ext-tools")) return;
  clearOverlays();
}

let _repositionScheduled = false;
function repositionOverlays() {
  if (!state.overlays.size || _repositionScheduled) return;
  _repositionScheduled = true;
  requestAnimationFrame(() => {
    _repositionScheduled = false;
    for (const holder of Array.from(state.overlays)) {
      const target = holder.__dmmtTargetElement;
      // 目標已移除（SPA 換頁等）→ 一併清掉覆蓋層。
      if (!target || !document.contains(target)) {
        removeOverlay(holder);
        continue;
      }
      const rect = target.getBoundingClientRect();
      if (rect.width < 1 || rect.height < 1) {
        // 目標暫時隱藏（display:none），先藏起覆蓋層但不刪除。
        holder.style.display = "none";
        continue;
      }
      holder.style.display = "";
      // 用建立時記錄的偏移定位，並保留截圖時的尺寸，使翻譯的那一段持續對齊原圖。
      const offX = holder.__dmmtOffsetX || 0;
      const offY = holder.__dmmtOffsetY || 0;
      holder.style.left = `${rect.left + offX}px`;
      holder.style.top = `${rect.top + offY}px`;
      if (holder.__dmmtCapW) holder.style.width = `${holder.__dmmtCapW}px`;
      if (holder.__dmmtCapH) holder.style.height = `${holder.__dmmtCapH}px`;
    }
  });
}

function showStatus(text, timeout = 0) {
  state.status.textContent = text;
  state.status.classList.remove("dmmt-ext-hidden");
  if (timeout > 0) {
    window.setTimeout(() => state.status.classList.add("dmmt-ext-hidden"), timeout);
  }
}

function showProgress(text) {
  state.progressText.textContent = text;
  state.progress.classList.remove("dmmt-ext-hidden");
}

function hideProgressSoon() {
  window.setTimeout(() => {
    state.progress.classList.add("dmmt-ext-hidden");
  }, 700);
}

function hideStatus() {
  state.status.classList.add("dmmt-ext-hidden");
}

function syncSettingsIfOnMangaTranslatorUi() {
  if (!/^(127\.0\.0\.1|localhost)$/i.test(location.hostname)) return;
  const sync = () => {
    try {
      const text = localStorage.getItem("manga-translator-settings") || "";
      if (!text || text === state.lastSettingsText) return;
      state.lastSettingsText = text;
      sendMessage({
        type: "sync-settings",
        settings: JSON.parse(text),
        apiBase: location.origin
      }).then((settings) => {
        showStatus(`已同步 MangaTranslator 設定：${settings.llmProvider} / ${settings.targetLang}`, 1800);
      }).catch(() => {});
    } catch {
      // Ignore malformed in-progress localStorage writes.
    }
  };
  sync();
  window.addEventListener("storage", sync);
  window.setInterval(sync, 2000);
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== "popup-command") return;
  try {
    if (message.action === "toggle-pick") togglePickMode();
    if (message.action === "box-select") toggleBoxMode();
    if (message.action === "toggle-auto") toggleAutoMode();
    if (message.action === "toggle-view") toggleViewMode();
    if (message.action === "toggle-ui") toggleBubbleVisibility();
    if (message.action === "restore-all") {
      clearOverlays();
      releaseAllReplacements();
      stopAutoMode();
      stopPageTranslate();
    }
    if (message.action === "clear-current") {
      // 清除目前頁面的翻譯：還原所有替換並刪掉它們的快取，避免又被掃回來。
      clearOverlays();
      for (const el of Array.from(state.replacements.keys())) {
        restoreInPlaceReplacement(el, true);
      }
      stopAutoMode();
      stopPageTranslate();
    }
    if (message.action === "translate-page") translatePage();
    if (message.action === "toggle-page") translatePage();
    if (message.action === "download-current") downloadCurrentTranslations();
    if (message.action === "download-all") downloadAllTranslations();
    if (message.action === "diagnose-cache") diagnoseCacheApply();
    sendResponse({
      ok: true,
      state: {
        picking: state.picking,
        auto: Boolean(state.autoTargets.length > 0 || state.autoArming || _autoPersistEnabled),
        pageActive: Boolean(_pageTranslate || _pagePersistEnabled),
        boxActive: Boolean(_boxMode || state.boxEditing),
        viewMode: state.viewMode,
        uiVisible: !state.bubbleHidden,
        replacements: state.replacements.size + state.overlays.size
      }
    });
  } catch (error) {
    sendResponse({ ok: false, error: String(error?.message || error) });
  }
});

function isExtContextError(e) {
  return /Extension context invalidated/i.test(e?.message || String(e));
}

window.addEventListener("unhandledrejection", (event) => {
  if (isExtContextError(event.reason)) event.preventDefault();
});
window.addEventListener("error", (event) => {
  if (isExtContextError(event.error)) event.preventDefault();
});

function isContextValid() {
  try { return Boolean(chrome.runtime?.id); } catch { return false; }
}

function chromeSafeGet(keys, cb) {
  try { chrome.storage.local.get(keys, cb); } catch {}
}

function chromeSafeSet(obj) {
  try { chrome.storage.local.set(obj); } catch {}
}

function chromeSafeRemove(keys) {
  try { chrome.storage.local.remove(keys); } catch {}
}

function sendMessage(message) {
  return new Promise((resolve, reject) => {
    if (!isContextValid()) {
      reject(new Error("擴充功能已更新，請重新整理頁面"));
      return;
    }
    try {
      chrome.runtime.sendMessage(message, (response) => {
        try {
          if (chrome.runtime.lastError) {
            reject(new Error(chrome.runtime.lastError.message));
            return;
          }
          if (!response?.ok) {
            reject(new Error(response?.error || "擴充功能背景程序沒有回應"));
            return;
          }
          resolve(response.result);
        } catch (e) {
          reject(e);
        }
      });
    } catch (e) {
      reject(e);
    }
  });
}

init();
"""進階編輯模式 server 端：載入翻譯後存的編輯狀態、套用使用者編輯、只重跑 render。

第一次翻譯時 manga_translator._save_edit_state 會在 result/<folder>/ 留下：
- background.png：抹字後背景（處理解析度，與 text_regions 座標對齊）
- edit_state.pkl：{img_inpainted, img_rgb, text_regions, config, input_size, orig_size}

重渲染完全在 server 進程跑（render 是 Qt + CPU，不需 GPU 模型），用 dispatch_rendering
搭 skip_font_scaling=True（直接吃 region.font_size，沒改就重現原狀、改了就生效）。
"""
import os
import pickle

import cv2
import numpy as np
from PIL import Image
from pydantic import BaseModel

from manga_translator.rendering import dispatch as dispatch_rendering


def _hex_to_rgb(value: str):
    v = (value or '').strip().lstrip('#')
    if len(v) != 6:
        return None
    try:
        return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


class RegionEdit(BaseModel):
    id: int
    translation: str | None = None
    font_size: int | None = None
    color: str | None = None      # "#rrggbb"
    bold: bool | None = None
    letter_spacing: float | None = None   # 字間距倍率（>1 拉開、<1 收緊）
    space_scale: float | None = None       # 空格寬度倍率（<1 收窄空格）
    direction: str | None = None  # 書寫方向：'auto'(自動) / 'h'(橫書) / 'v'(直書)
    font_path: str | None = None  # 該框字形（fonts/ 內檔名或 user/<name>）；空=用自動字形
    skip: bool = False            # 維持原文、不渲染譯文
    hidden: bool = False          # 暫時隱藏：不渲染譯文也不貼回原文（露出抹字後底圖）
    dx: int = 0                   # 位置微調（處理解析度像素）
    dy: int = 0


class PatchStroke(BaseModel):
    """手動修補筆刷一筆：座標為「最終輸出圖（final.png）」像素，後端換算到處理解析度。

    mode='erase'：把筆畫範圍用 OpenCV inpaint 補平（擦掉沒抹乾淨的殘字/痕跡）。
    mode='restore'：把筆畫範圍從原圖貼回（還原被誤擦的圖案）。
    """
    mode: str = 'erase'           # 'erase' / 'restore'
    size: float = 24              # 筆刷直徑（final.png 像素）
    points: list[list[float]] = []  # [[x, y], ...] 筆畫路徑


class CustomRegion(BaseModel):
    """使用者手動新增的文字框：在預覽上框選位置、自行填譯文。

    bbox 為「最終輸出圖（final.png）」像素座標，後端換算到處理解析度。
    """
    text: str = ''
    bbox: list[float] = []        # [x1, y1, x2, y2]
    font_size: int = 28           # 以 final.png 像素為準，後端換算
    color: str | None = None      # "#rrggbb"，None = 黑
    bold: bool = False
    direction: str = 'auto'       # 'auto' / 'h' / 'v'
    font_path: str | None = None
    letter_spacing: float | None = None
    space_scale: float | None = None


class RerenderRequest(BaseModel):
    folder: str
    edits: list[RegionEdit] = []
    patches: list[PatchStroke] = []
    custom_regions: list[CustomRegion] = []


# region 上會被覆寫的幾何 cached_property（移動位置後要清，否則 bbox 仍是舊值）
_GEOM_CACHE_KEYS = (
    'xyxy', 'xywh', 'center', 'unrotated_polygons',
    'unrotated_min_rect', 'min_rect', 'polygon_aspect_ratio',
)


def _state_path(result_root, folder: str) -> str:
    safe = os.path.basename(folder)
    return os.path.join(str(result_root), safe, 'edit_state.pkl')


def load_edit_state(result_root, folder: str):
    path = _state_path(result_root, folder)
    if not os.path.exists(path):
        return None
    with open(path, 'rb') as f:
        return pickle.load(f)


def _combined_regions(state):
    """渲染框（id 0..M0-1）+ 被跳過框（id M0..），id = 在合併清單的索引。"""
    return list(state.get('text_regions') or []) + list(state.get('skipped_regions') or [])


def _region_json(r, idx, was_skipped):
    try:
        x1, y1, x2, y2 = (int(v) for v in r.xyxy)
    except Exception:
        x1 = y1 = x2 = y2 = 0
    try:
        fg, _ = r.get_font_colors()
        color = '#%02x%02x%02x' % (int(fg[0]), int(fg[1]), int(fg[2]))
    except Exception:
        color = '#000000'
    return {
        'id': idx,
        'original': r.text or '',
        'translation': r.translation or '',
        'font_size': int(getattr(r, 'font_size', 0) or 0),
        'color': color,
        'bold': bool(getattr(r, 'bold', False)),
        'letter_spacing': round(float(getattr(r, 'letter_spacing', None) or 1.0), 2),
        'space_scale': round(float(getattr(r, 'space_scale', None) or 1.0), 2),
        'direction': (getattr(r, '_direction', '') if getattr(r, '_direction', '') in ('h', 'v') else 'auto'),
        'font': '',   # 預設用自動字形；使用者可在編輯器逐框覆蓋
        'bbox': [x1, y1, x2, y2],
        'angle': float(getattr(r, 'angle', 0) or 0),
        'skip': bool(was_skipped),   # 被跳過框預設勾「不渲染/維持原文」
        'was_skipped': bool(was_skipped),
    }


def state_to_json(result_root, folder: str):
    """回給編輯器的結構：渲染框在前、被跳過框（SFX/符號/小字）排最底並預設不渲染。"""
    state = load_edit_state(result_root, folder)
    if state is None:
        return None
    inp = state['img_inpainted']
    h, w = inp.shape[:2]
    rendered = list(state.get('text_regions') or [])
    skipped = list(state.get('skipped_regions') or [])
    out = []
    idx = 0
    for r in rendered:
        out.append(_region_json(r, idx, was_skipped=False)); idx += 1
    for r in skipped:
        out.append(_region_json(r, idx, was_skipped=True)); idx += 1
    return {'width': int(w), 'height': int(h), 'regions': out}


def _apply_edit(region, e: RegionEdit):
    if e.translation is not None:
        region.translation = e.translation
    if e.font_size and e.font_size > 0:
        region.font_size = int(e.font_size)
    if e.color:
        rgb = _hex_to_rgb(e.color)
        if rgb is not None:
            region.fg_colors = np.array(rgb, dtype=np.uint8)
            region.adjust_bg_color = False
    if e.bold is not None:
        region.bold = bool(e.bold)
    if e.letter_spacing and e.letter_spacing > 0:
        region.letter_spacing = float(e.letter_spacing)
    if e.space_scale and e.space_scale > 0:
        region.space_scale = float(e.space_scale)
    if e.direction:
        # 'h'/'v' 強制方向；其他值（auto）→ 設成非法值讓 direction property 自動推斷
        region._direction = e.direction if e.direction in ('h', 'v', 'hr', 'vr') else 'auto'
    if e.font_path:
        # 空值不動，沿用 pickle 載入的自動字形；選了才覆蓋（_resolve_font_path 認 fonts/ 與 user/）
        region.font_path = e.font_path
    if e.dx or e.dy:
        # Y 翻轉：UI 正值 = 往上（直覺），影像座標 Y 向下為正，故減 dy
        region.lines = (np.array(region.lines, dtype=np.int32)
                        + np.array([int(e.dx), -int(e.dy)], dtype=np.int32))
        for k in _GEOM_CACHE_KEYS:
            region.__dict__.pop(k, None)


def _bbox_clip(region, shape):
    x1, y1, x2, y2 = (int(v) for v in region.xyxy)
    x1, y1 = max(0, x1), max(0, y1)
    x2 = min(shape[1], x2); y2 = min(shape[0], y2)
    return x1, y1, x2, y2


def _fill_region_bg(base, region):
    """把框內填成取樣的背景色（被跳過框背景仍含原字，opt-in 翻譯前先粗略抹掉）。"""
    x1, y1, x2, y2 = _bbox_clip(region, base.shape)
    if x2 <= x1 or y2 <= y1:
        return
    # 取框邊一圈像素的中位數當底色
    pad = 3
    yy1, yy2 = max(0, y1 - pad), min(base.shape[0], y2 + pad)
    xx1, xx2 = max(0, x1 - pad), min(base.shape[1], x2 + pad)
    border = []
    if y1 - yy1 > 0:
        border.append(base[yy1:y1, xx1:xx2].reshape(-1, base.shape[2]))
    if yy2 - y2 > 0:
        border.append(base[y2:yy2, xx1:xx2].reshape(-1, base.shape[2]))
    if border:
        col = np.median(np.concatenate(border, axis=0), axis=0)
    else:
        col = np.array([255, 255, 255], np.float32)
    base[y1:y2, x1:x2] = col.astype(np.uint8)


def _paste_original(base, img_rgb, region, pad: int):
    """把原圖的字形範圍貼回背景：用 textline 多邊形 + 外擴遮罩。

    抹字時 complete_mask 會把遮罩膨脹（mask_dilation_offset + kernel），
    只貼 bbox 會在框外留一圈擦除痕跡 → 這裡同步外擴才能蓋乾淨。
    """
    mask = np.zeros(base.shape[:2], np.uint8)
    lines = getattr(region, 'lines', None)
    drawn = False
    if lines is not None and len(lines) > 0:
        for line in lines:
            try:
                cv2.fillPoly(mask, [np.round(np.asarray(line)).astype(np.int32)], 255)
                drawn = True
            except Exception:
                continue
    if not drawn:
        x1, y1, x2, y2 = _bbox_clip(region, base.shape)
        if x2 <= x1 or y2 <= y1:
            return
        mask[y1:y2, x1:x2] = 255
    mask = cv2.dilate(mask, np.ones((pad, pad), np.uint8))
    base[mask > 0] = img_rgb[mask > 0]


def _stroke_mask(shape, stroke: 'PatchStroke', sx: float, sy: float) -> 'np.ndarray | None':
    """筆畫 → 處理解析度的二值遮罩（座標從 final.png 像素換算）。"""
    pts = [(int(round(p[0] * sx)), int(round(p[1] * sy))) for p in (stroke.points or []) if len(p) >= 2]
    if not pts:
        return None
    radius = max(1, int(round(stroke.size * (sx + sy) / 4)))  # 直徑→半徑，取 xy 平均縮放
    mask = np.zeros(shape[:2], np.uint8)
    for i, p in enumerate(pts):
        cv2.circle(mask, p, radius, 255, -1)
        if i:
            cv2.line(mask, pts[i - 1], p, 255, thickness=radius * 2)
    return mask


def _build_custom_region(c: 'CustomRegion', sx: float, sy: float, target_lang: str):
    """手動文字框 → TextBlock（座標/字級從 final.png 像素換算到處理解析度）。"""
    from manga_translator.utils.textblock import TextBlock

    if len(c.bbox) < 4 or not (c.text or '').strip():
        return None
    x1, y1, x2, y2 = (float(v) for v in c.bbox[:4])
    x1, x2 = sorted((x1 * sx, x2 * sx))
    y1, y2 = sorted((y1 * sy, y2 * sy))
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None
    rgb = _hex_to_rgb(c.color or '') or (0, 0, 0)
    region = TextBlock(
        lines=[[[x1, y1], [x2, y1], [x2, y2], [x1, y2]]],
        texts=[c.text],
        translation=c.text,
        font_size=max(6, int(round(c.font_size * (sx + sy) / 2))),
        fg_color=rgb,
        bg_color=(255, 255, 255),
        bold=bool(c.bold),
        direction=c.direction if c.direction in ('h', 'v', 'hr', 'vr') else 'auto',
        target_lang=target_lang,
    )
    region.adjust_bg_color = False
    if c.font_path:
        region.font_path = c.font_path
    if c.letter_spacing and c.letter_spacing > 0:
        region.letter_spacing = float(c.letter_spacing)
    if c.space_scale and c.space_scale > 0:
        region.space_scale = float(c.space_scale)
    return region


def _apply_patches(base, img_rgb, patches: 'list[PatchStroke]', orig_size):
    """套用手動修補筆刷（在嵌字前的背景上動工）。"""
    h, w = base.shape[:2]
    if orig_size and orig_size[0] and orig_size[1]:
        sx, sy = w / float(orig_size[0]), h / float(orig_size[1])
    else:
        sx = sy = 1.0
    for stroke in patches:
        mask = _stroke_mask(base.shape, stroke, sx, sy)
        if mask is None:
            continue
        if stroke.mode == 'restore' and img_rgb is not None:
            base[mask > 0] = img_rgb[mask > 0]
        else:
            # erase：用周圍像素補平（殘字、漏擦的痕跡直接消失）
            patched = cv2.inpaint(base, mask, 3, cv2.INPAINT_TELEA)
            base[mask > 0] = patched[mask > 0]


async def rerender(result_root, folder: str, edits: list[RegionEdit],
                   patches: 'list[PatchStroke] | None' = None,
                   custom_regions: 'list[CustomRegion] | None' = None) -> Image.Image:
    """套用編輯、只重跑 render，回傳成品 PIL（已縮回原始尺寸）。"""
    state = load_edit_state(result_root, folder)
    if state is None:
        raise FileNotFoundError('edit state not found (translate first with advanced mode on)')

    img_inpainted = state['img_inpainted']
    img_rgb = state.get('img_rgb')
    rendered = list(state.get('text_regions') or [])
    n_rendered = len(rendered)
    regions = _combined_regions(state)
    config = state['config']
    orig_size = state.get('orig_size')

    edit_map = {e.id: e for e in edits}
    base = np.array(img_inpainted).copy()
    # 原圖尺寸跟處理解析度不合（upscale/resize 過）→ 縮放對齊，「維持原文」與還原筆刷才貼得回去
    if img_rgb is not None and img_rgb.shape[:2] != base.shape[:2]:
        img_rgb = cv2.resize(np.asarray(img_rgb), (base.shape[1], base.shape[0]),
                             interpolation=cv2.INTER_LANCZOS4)
    # 貼回外擴量：跟 complete_mask 的膨脹（mask_dilation_offset + kernel*2，kernel 預設 3）同步
    paste_pad = max(8, int(getattr(config, 'mask_dilation_offset', 20) or 20) + 6)

    render_regions = []
    for i, region in enumerate(regions):
        e = edit_map.get(i)
        was_skipped = i >= n_rendered
        # 暫時隱藏：什麼都不畫、也不貼回原文 → 露出抹字後的底圖（搭配筆刷清理用）
        if e is not None and e.hidden:
            continue
        skip = was_skipped if e is None else bool(e.skip)
        if skip:
            # 維持原文：把原圖該框（含擦除暈邊）貼回背景
            if img_rgb is not None:
                _paste_original(base, img_rgb, region, paste_pad)
            continue
        if e:
            _apply_edit(region, e)
        # opt-in 翻譯一個原本被跳過的框：背景仍有原字 → 先粗略抹掉再畫譯文
        if was_skipped and (region.translation or '').strip():
            _fill_region_bg(base, region)
        render_regions.append(region)

    # 手動修補筆刷最後套（蓋在自動貼回之上，使用者畫的最大）
    if patches:
        _apply_patches(base, img_rgb, patches, orig_size)

    # 手動新增的文字框（座標從 final.png 像素換算到處理解析度）
    if custom_regions:
        h, w = base.shape[:2]
        if orig_size and orig_size[0] and orig_size[1]:
            sx, sy = w / float(orig_size[0]), h / float(orig_size[1])
        else:
            sx = sy = 1.0
        target_lang = getattr(getattr(config, 'translator', None), 'target_lang', '') or ''
        for c in custom_regions:
            region = _build_custom_region(c, sx, sy, target_lang)
            if region is not None:
                render_regions.append(region)

    output = await dispatch_rendering(
        base, render_regions, config, img_rgb, skip_font_scaling=True,
    )
    result = Image.fromarray(output.astype(np.uint8))

    # 一律縮放回原圖解析度——使用者看到的輸出永遠跟原圖同尺寸
    if orig_size and tuple(result.size) != tuple(orig_size):
        result = result.resize(tuple(orig_size), Image.LANCZOS)
    return result

import itertools
import os
import numpy as np
from typing import List, Set
from collections import Counter
import networkx as nx
from shapely.geometry import Polygon

from ..utils import TextBlock, Quadrilateral, quadrilateral_can_merge_region, get_logger

logger = get_logger('textline_merge')


def _assign_region_to_bubble(region: TextBlock, bubbles) -> int:
    """Attach the merged region to the bubble it actually sits in."""
    if not bubbles:
        return -1
    try:
        x1, y1, x2, y2 = [int(v) for v in region.xyxy]
    except Exception:
        return -1

    area = max(1, (x2 - x1) * (y2 - y1))
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    best_idx = -1
    best_ratio = 0.0
    center_hit = -1
    for i, (bx1, by1, bx2, by2) in enumerate(bubbles):
        bw = max(1, bx2 - bx1)
        bh = max(1, by2 - by1)
        pad_x = max(4, int(bw * 0.06))
        pad_y = max(4, int(bh * 0.06))
        ebx1, eby1 = bx1 - pad_x, by1 - pad_y
        ebx2, eby2 = bx2 + pad_x, by2 + pad_y
        if ebx1 <= cx <= ebx2 and eby1 <= cy <= eby2:
            center_hit = i
        ix1, iy1 = max(x1, ebx1), max(y1, eby1)
        ix2, iy2 = min(x2, ebx2), min(y2, eby2)
        if ix2 <= ix1 or iy2 <= iy1:
            continue
        overlap = (ix2 - ix1) * (iy2 - iy1)
        ratio = overlap / area
        if ratio > best_ratio:
            best_ratio = ratio
            best_idx = i
    if best_ratio >= 0.35:
        return best_idx
    return center_hit


def _bubble_region_sort_key(region: TextBlock):
    """Japanese manga bubbles are usually vertical: right column first, then down."""
    try:
        x1, y1, x2, y2 = [int(v) for v in region.xyxy]
    except Exception:
        return (0, 0)
    w = max(1, x2 - x1)
    h = max(1, y2 - y1)
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    if h >= w * 1.2:
        return (-cx, cy)
    return (cy, cx)


def _choose_bubble_style_region(regions: List[TextBlock]) -> TextBlock:
    def score(region: TextBlock):
        text = region.text or ''
        has_han = any('\u4e00' <= ch <= '\u9fff' for ch in text)
        try:
            area = int(region.xywh[2] * region.xywh[3])
        except Exception:
            area = 0
        return (1 if has_han else 0, area)

    return max(regions, key=score)


def _coalesce_bubble_regions(regions: List[TextBlock], bubbles) -> List[TextBlock]:
    """Make one render/translation region per speech bubble, plus untouched outside regions."""
    if not bubbles:
        for region in regions:
            region._layout_role = 'outside'
        return regions

    by_bubble: dict[int, List[TextBlock]] = {}
    outside: List[TextBlock] = []
    for region in regions:
        bubble_idx = getattr(region, '_bubble_idx', -1)
        if bubble_idx >= 0:
            by_bubble.setdefault(bubble_idx, []).append(region)
        else:
            region._layout_role = 'outside'
            outside.append(region)

    out: List[TextBlock] = []
    merged_count = 0
    for bubble_idx, group in by_bubble.items():
        ordered = sorted(group, key=_bubble_region_sort_key)
        if len(ordered) == 1:
            region = ordered[0]
            region._layout_role = 'dialogue'
            out.append(region)
            continue

        style = _choose_bubble_style_region(ordered)
        lines = []
        texts = []
        for region in ordered:
            lines.extend([line for line in region.lines])
            texts.append(region.text)

        font_size = int(np.median([max(1, region.font_size) for region in ordered]))
        angle = float(np.mean([getattr(region, 'angle', 0) for region in ordered]))
        merged = TextBlock(
            lines,
            texts,
            font_size=font_size,
            angle=angle,
            prob=float(np.mean([getattr(region, 'prob', 1.0) for region in ordered])),
            fg_color=style.fg_colors,
            bg_color=style.bg_colors,
        )
        merged.text_raw = ''.join(texts)
        merged._bubble_idx = bubble_idx
        merged._bubble_rect = bubbles[bubble_idx]
        merged._bubble_rects = bubbles
        merged._layout_role = 'dialogue'
        merged._coalesced_regions = ordered
        out.append(merged)
        merged_count += len(ordered) - 1

    if merged_count:
        logger.info(f'[bubble-aware] coalesced {merged_count} extra text regions into speech bubbles')
    return sorted(out + outside, key=lambda region: (region.xyxy[1], region.xyxy[0]))


def split_text_region(
        bboxes: List[Quadrilateral],
        connected_region_indices: Set[int],
        width,
        height,
        gamma = 0.5,
        sigma = 2
    ) -> List[Set[int]]:

    connected_region_indices = list(connected_region_indices)

    # case 1
    if len(connected_region_indices) == 1:
        return [set(connected_region_indices)]

    # case 2
    if len(connected_region_indices) == 2:
        fs1 = bboxes[connected_region_indices[0]].font_size
        fs2 = bboxes[connected_region_indices[1]].font_size
        fs = max(fs1, fs2)

        # print(bboxes[connected_region_indices[0]].pts, bboxes[connected_region_indices[1]].pts)
        # print(fs, bboxes[connected_region_indices[0]].distance(bboxes[connected_region_indices[1]]), (1 + gamma) * fs)
        # print(bboxes[connected_region_indices[0]].angle, bboxes[connected_region_indices[1]].angle, 4 * np.pi / 180)

        if bboxes[connected_region_indices[0]].distance(bboxes[connected_region_indices[1]]) < (1 + gamma) * fs \
                and abs(bboxes[connected_region_indices[0]].angle - bboxes[connected_region_indices[1]].angle) < 0.2 * np.pi:
            return [set(connected_region_indices)]
        else:
            return [set([connected_region_indices[0]]), set([connected_region_indices[1]])]

    # case 3
    G = nx.Graph()
    for idx in connected_region_indices:
        G.add_node(idx)
    for (u, v) in itertools.combinations(connected_region_indices, 2):
        G.add_edge(u, v, weight=bboxes[u].distance(bboxes[v]))
    # Get distances from neighbouring bboxes
    edges = nx.algorithms.tree.minimum_spanning_edges(G, algorithm='kruskal', data=True)
    edges = sorted(edges, key=lambda a: a[2]['weight'], reverse=True)
    distances_sorted = [a[2]['weight'] for a in edges]
    fontsize = np.mean([bboxes[idx].font_size for idx in connected_region_indices])
    distances_std = np.std(distances_sorted)
    distances_mean = np.mean(distances_sorted)
    std_threshold = max(0.3 * fontsize + 5, 5)

    b1, b2 = bboxes[edges[0][0]], bboxes[edges[0][1]]
    max_poly_distance = Polygon(b1.pts).distance(Polygon(b2.pts))
    max_centroid_alignment = min(abs(b1.centroid[0] - b2.centroid[0]), abs(b1.centroid[1] - b2.centroid[1]))

    # print(edges)
    # print(f'std: {distances_std} < thrshold: {std_threshold}, mean: {distances_mean}')
    # print(f'{distances_sorted[0]} <= {distances_mean + distances_std * sigma}' \
    #         f' or {distances_sorted[0]} <= {fontsize * (1 + gamma)}' \
    #         f' or {distances_sorted[0] - distances_sorted[1]} < {distances_std * sigma}')

    if (distances_sorted[0] <= distances_mean + distances_std * sigma \
            or distances_sorted[0] <= fontsize * (1 + gamma)) \
            and (distances_std < std_threshold \
            or max_poly_distance == 0 and max_centroid_alignment < 5):
        return [set(connected_region_indices)]
    else:
        # (split_u, split_v, _) = edges[0]
        # print(f'split between "{bboxes[split_u].pts}", "{bboxes[split_v].pts}"')
        G = nx.Graph()
        for idx in connected_region_indices:
            G.add_node(idx)
        # Split out the most deviating bbox
        for edge in edges[1:]:
            G.add_edge(edge[0], edge[1])
        ans = []
        for node_set in nx.algorithms.components.connected_components(G):
            ans.extend(split_text_region(bboxes, node_set, width, height))
        return ans

# def get_mini_boxes(contour):
#     bounding_box = cv2.minAreaRect(contour)
#     points = sorted(list(cv2.boxPoints(bounding_box)), key=lambda x: x[0])

#     index_1, index_2, index_3, index_4 = 0, 1, 2, 3
#     if points[1][1] > points[0][1]:
#         index_1 = 0
#         index_4 = 1
#     else:
#         index_1 = 1
#         index_4 = 0
#     if points[3][1] > points[2][1]:
#         index_2 = 2
#         index_3 = 3
#     else:
#         index_2 = 3
#         index_3 = 2

#     box = [points[index_1], points[index_2], points[index_3], points[index_4]]
#     box = np.array(box)
#     startidx = box.sum(axis=1).argmin()
#     box = np.roll(box, 4 - startidx, 0)
#     box = np.array(box)
#     return box

def merge_bboxes_text_region(bboxes: List[Quadrilateral], width, height, owner_by_idx: List[int] = None):
    # step 1: divide into multiple text region candidates
    G = nx.Graph()
    for i, box in enumerate(bboxes):
        G.add_node(i, box=box)

    for ((u, ubox), (v, vbox)) in itertools.combinations(enumerate(bboxes), 2):
        # bubble-aware：兩 textline 屬於不同氣泡時直接拒絕合併（DBNet 把相鄰氣泡黏起來時靠這條切開）
        if owner_by_idx is not None:
            ou, ov = owner_by_idx[u], owner_by_idx[v]
            if ou >= 0 and ov >= 0 and ou != ov:
                continue
        # 修改：原本 char_gap_tolerance2=3、font_size_ratio_tol=2 太寬鬆，
        # 會把對話框跟附近旁白／字幕合併成同一 region 導致譯文塞進錯氣泡。
        # 收緊到 1.5 / 1.5：仍允許同氣泡多行合併（tolerance1=1），但拒絕遠距 fallback。
        if quadrilateral_can_merge_region(ubox, vbox, aspect_ratio_tol=1.3, font_size_ratio_tol=1.5,
                                          char_gap_tolerance=1, char_gap_tolerance2=1.5):
            G.add_edge(u, v)

    # step 2: postprocess - further split each region
    region_indices: List[Set[int]] = []
    for node_set in nx.algorithms.components.connected_components(G):
         region_indices.extend(split_text_region(bboxes, node_set, width, height))

    # step 3: return regions
    for node_set in region_indices:
    # for node_set in nx.algorithms.components.connected_components(G):
        nodes = list(node_set)
        txtlns: List[Quadrilateral] = np.array(bboxes)[nodes]

        # calculate average fg and bg color
        fg_r = round(np.mean([box.fg_r for box in txtlns]))
        fg_g = round(np.mean([box.fg_g for box in txtlns]))
        fg_b = round(np.mean([box.fg_b for box in txtlns]))
        bg_r = round(np.mean([box.bg_r for box in txtlns]))
        bg_g = round(np.mean([box.bg_g for box in txtlns]))
        bg_b = round(np.mean([box.bg_b for box in txtlns]))

        # majority vote for direction
        dirs = [box.direction for box in txtlns]
        majority_dir_top_2 = Counter(dirs).most_common(2)
        if len(majority_dir_top_2) == 1 :
            majority_dir = majority_dir_top_2[0][0]
        elif majority_dir_top_2[0][1] == majority_dir_top_2[1][1] : # if top 2 have the same counts
            max_aspect_ratio = -100
            for box in txtlns :
                if box.aspect_ratio > max_aspect_ratio :
                    max_aspect_ratio = box.aspect_ratio
                    majority_dir = box.direction
                if 1.0 / box.aspect_ratio > max_aspect_ratio :
                    max_aspect_ratio = 1.0 / box.aspect_ratio
                    majority_dir = box.direction
        else :
            majority_dir = majority_dir_top_2[0][0]

        # sort textlines
        if majority_dir == 'h':
            nodes = sorted(nodes, key=lambda x: bboxes[x].centroid[1])
        elif majority_dir == 'v':
            nodes = sorted(nodes, key=lambda x: -bboxes[x].centroid[0])
        txtlns = np.array(bboxes)[nodes]

        # 判斷該 region 是否完全屬於同一個 bubble；是的話回 bubble_idx，否則 -1
        bubble_idx = -1
        if owner_by_idx is not None:
            owners = {owner_by_idx[i] for i in nodes if owner_by_idx[i] >= 0}
            if len(owners) == 1:
                bubble_idx = next(iter(owners))

        # yield textlines, colors, bubble owner
        yield txtlns, (fg_r, fg_g, fg_b), (bg_r, bg_g, bg_b), bubble_idx

async def dispatch(textlines: List[Quadrilateral], width: int, height: int,
                   img_rgb: 'np.ndarray | None' = None, verbose: bool = False) -> List[TextBlock]:
    # bubble-aware：用 YOLO bubble detector 找氣泡邊界，把跨氣泡的 textline 切開
    # （DBNet 對相鄰氣泡的字常會被啟發式 merge 黏到同一 region）
    owner_by_idx = None
    bubbles = None
    if img_rgb is not None and os.environ.get('BUBBLE_AWARE_MERGE', '1') in ('1', 'true', 'True'):
        try:
            from ..bubble_detection import detect_bubbles, assign_textlines_to_bubbles
            bubbles = detect_bubbles(img_rgb)
            if bubbles:
                owner_by_idx = assign_textlines_to_bubbles(textlines, bubbles)
                grouped = sum(1 for o in owner_by_idx if o >= 0)
                logger.info(f'[bubble-aware] {len(bubbles)} bubbles | {grouped}/{len(textlines)} textlines 歸入氣泡')
        except Exception as e:
            logger.warning(f'[bubble-aware] failed (fallback to plain merge): {type(e).__name__}: {e}')

    text_regions: List[TextBlock] = []
    for (txtlns, fg_color, bg_color, bubble_idx) in merge_bboxes_text_region(
        textlines, width, height, owner_by_idx=owner_by_idx,
    ):
        total_logprobs = 0
        for txtln in txtlns:
            total_logprobs += np.log(txtln.prob) * txtln.area
        total_logprobs /= sum([txtln.area for txtln in textlines])

        font_size = int(min([txtln.font_size for txtln in txtlns]))
        angle = np.rad2deg(np.mean([txtln.angle for txtln in txtlns])) - 90
        if abs(angle) < 3:
            angle = 0
        lines = [txtln.pts for txtln in txtlns]
        texts = [txtln.text for txtln in txtlns]
        region = TextBlock(lines, texts, font_size=font_size, angle=angle, prob=np.exp(total_logprobs),
                           fg_color=fg_color, bg_color=bg_color)
        if bubbles:
            region._bubble_rects = bubbles
        region_bubble_idx = _assign_region_to_bubble(region, bubbles)
        if region_bubble_idx >= 0 and region_bubble_idx < len(bubbles):
            region._bubble_idx = region_bubble_idx
            region._bubble_rect = bubbles[region_bubble_idx]
            region._layout_role = 'dialogue'
        else:
            region._bubble_idx = -1
            region._layout_role = 'outside'
        text_regions.append(region)

    # 空泡泡補抓：YOLO 偵測到的泡泡內若一條 textline 都沒有（DBNet 漏抓
    # 點點+單假名的小血滴泡，實例「……み」），合成一個覆蓋泡內的 region 丟給
    # vision 讓 Gemini 看圖讀字（corrected_text）。文字佔位 '…'：能過
    # min_text_length，且 not-valuable 的泡內豁免會放行。誤報泡泡（裡面沒字）
    # 由 vision 回空 → 空譯文 → mask 挖洞保留原圖，無害。
    if bubbles:
        owned = {getattr(r, '_bubble_idx', -1) for r in text_regions}
        for i, (bx1, by1, bx2, by2) in enumerate(bubbles):
            if i in owned:
                continue
            bw, bh = bx2 - bx1, by2 - by1
            if bw < 24 or bh < 24:
                continue
            # 泡內其實有字、只是歸泡失敗（手寫字 box 超出泡框）：有任一 region
            # 與泡交疊 ≥30% 泡面積就不合成，否則 vision 會把同句讀兩次疊圖
            bubble_area = float(bw * bh)
            covered = False
            for r in text_regions:
                xs = [p[0] for ln in r.lines for p in ln]
                ys = [p[1] for ln in r.lines for p in ln]
                ix = max(0.0, min(bx2, max(xs)) - max(bx1, min(xs)))
                iy = max(0.0, min(by2, max(ys)) - max(by1, min(ys)))
                if ix * iy >= bubble_area * 0.3:
                    covered = True
                    break
            if covered:
                logger.info(f'[bubble-aware] 泡泡 {i} 已被既有 region 覆蓋，略過補抓')
                continue
            # 框取泡泡中央 ~56%：render 的字級是「把框撐滿」反推的，框給太大
            # 短譯文（……）會被放成超大字、太小又看不清。譯文長時排版會自己外擴。
            # font_size 是字級天花板的基準（cap = ×1.4），0.2 → 字約佔泡泡短邊 28%。
            sx, sy = int(bw * 0.22), int(bh * 0.22)
            pts = np.array([
                [bx1 + sx, by1 + sy], [bx2 - sx, by1 + sy],
                [bx2 - sx, by2 - sy], [bx1 + sx, by2 - sy],
            ], dtype=np.float32)
            region = TextBlock([pts], ['…'], font_size=max(12, int(min(bw, bh) * 0.2)),
                               angle=0, prob=0.5,
                               fg_color=(0, 0, 0), bg_color=(255, 255, 255))
            region._bubble_rects = bubbles
            region._bubble_idx = i
            region._bubble_rect = bubbles[i]
            region._layout_role = 'dialogue'
            region._synth_bubble = True
            text_regions.append(region)
            logger.info(f'[bubble-aware] 泡泡 {i} 無 textline，補抓整泡交 vision 讀字')
    # Keep OCR/translation regions granular. Coalescing happens after translation,
    # otherwise noisy OCR from tiny in-bubble marks can poison the LLM sentence.
    return text_regions

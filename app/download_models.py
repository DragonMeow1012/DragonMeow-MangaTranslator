# -*- coding: utf-8 -*-
"""
下載 / 校驗 / 補齊 DragonMeow-MangaTranslator 需要的模型權重。

setup.bat 在裝完套件後會自動呼叫本檔；也可單獨執行做完整性檢查：
    python download_models.py            # 檢查 + 補齊缺損
    python download_models.py --force    # 全部重新驗證 / 重抓

行為：
  * 有 sha256 的檔（偵測 / OCR / 抹字）：存在且雜湊正確 -> 跳過；
    缺檔或雜湊不符（檔案損壞 / 防毒誤刪 / 解壓不全）-> 重新下載並再次校驗。
  * HuggingFace 模型（manga-ocr-base 日文 OCR、對話框偵測）沒有官方單檔雜湊，
    改以「必要檔是否齊全且非空」判斷，缺了就重抓。

url / hash 來源是各模組的 _MODEL_MAPPING：
  manga_translator/detection/default.py
  manga_translator/ocr/model_48px.py
  manga_translator/inpainting/inpainting_lama_mpe.py
更新模型版本時，請同步這裡的表。
"""
import hashlib
import os
import sys
import urllib.request

# 不論主控台用哪個碼頁（cp950 / cp932 / utf-8），中文輸出都不該讓程式崩潰。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

BASE = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE, 'models')
CHUNK = 1024 * 256

# (相對於 models/ 的路徑, 下載網址, sha256)
HASHED = [
    ('detection/detect-20241225.ckpt',
     'https://github.com/zyddnys/manga-image-translator/releases/download/beta-0.3/detect-20241225.ckpt',
     '67ce1c4ed4793860f038c71189ba9630a7756f7683b1ee5afb69ca0687dc502e'),
    ('ocr/ocr_ar_48px.ckpt',
     'https://github.com/zyddnys/manga-image-translator/releases/download/beta-0.3/ocr_ar_48px.ckpt',
     '29daa46d080818bb4ab239a518a88338cbccff8f901bef8c9db191a7cb97671d'),
    ('ocr/alphabet-all-v7.txt',
     'https://github.com/zyddnys/manga-image-translator/releases/download/beta-0.3/alphabet-all-v7.txt',
     'f5722368146aa0fbcc9f4726866e4efc3203318ebb66c811d8cbbe915576538a'),
    ('inpainting/inpainting_lama_mpe.ckpt',
     'https://github.com/zyddnys/manga-image-translator/releases/download/beta-0.3/inpainting_lama_mpe.ckpt',
     'd625aa1b3e0d0408acfd6928aa84f005867aa8dbb9162480346a4e20660786cc'),
    ('inpainting/lama_large_512px.ckpt',
     'https://huggingface.co/dreMaz/AnimeMangaInpainting/resolve/main/lama_large_512px.ckpt',
     '11d30fbb3000fb2eceae318b75d9ced9229d99ae990a7f8b3ac35c8d31f2c935'),
]

# HuggingFace 多檔模型：repo_id, 子目錄, 必要檔
HF_SNAPSHOTS = [
    ('kha-white/manga-ocr-base', 'manga-ocr-base',
     ['config.json', 'preprocessor_config.json', 'pytorch_model.bin',
      'special_tokens_map.json', 'tokenizer_config.json', 'vocab.txt']),
]
# HuggingFace 單檔模型：repo_id, 檔名, 子目錄
HF_SINGLE = [
    ('ogkalu/comic-speech-bubble-detector-yolov8m',
     'comic-speech-bubble-detector.pt', 'bubble_detector'),
]


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(CHUNK), b''):
            h.update(chunk)
    return h.hexdigest()


def human(n):
    n = float(n)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return '%.1f%s' % (n, unit)
        n /= 1024


def download(url, dest):
    """串流下載到 dest（先寫 .part 再改名，避免半截檔被當成完整檔）。"""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    part = dest + '.part'
    req = urllib.request.Request(url, headers={'User-Agent': 'dmmt-setup'})
    with urllib.request.urlopen(req) as resp:
        total = int(resp.headers.get('Content-Length', 0) or 0)
        done = 0
        with open(part, 'wb') as f:
            while True:
                buf = resp.read(CHUNK)
                if not buf:
                    break
                f.write(buf)
                done += len(buf)
                if total:
                    pct = done * 100 // total
                    sys.stdout.write('\r     %3d%%  %s / %s   ' % (pct, human(done), human(total)))
                else:
                    sys.stdout.write('\r     %s   ' % human(done))
                sys.stdout.flush()
    sys.stdout.write('\n')
    os.replace(part, dest)


def do_hashed(force):
    ok = dl = fail = 0
    for rel, url, want in HASHED:
        dest = os.path.join(MODELS_DIR, *rel.split('/'))
        if os.path.isfile(dest) and not force:
            sys.stdout.write('[檢查] %s ... ' % rel)
            sys.stdout.flush()
            if sha256_of(dest).lower() == want.lower():
                print('OK')
                ok += 1
                continue
            print('雜湊不符，重新下載')
        else:
            print('[缺檔] %s，開始下載' % rel)
        try:
            download(url, dest)
            if sha256_of(dest).lower() != want.lower():
                print('  [錯誤] %s 下載後校驗失敗（檔案可能在傳輸中損壞）' % rel)
                try:
                    os.remove(dest)
                except OSError:
                    pass
                fail += 1
                continue
            print('  [完成] %s 校驗通過' % rel)
            dl += 1
        except Exception as e:
            print('  [錯誤] %s 下載失敗：%s: %s' % (rel, type(e).__name__, e))
            fail += 1
    return ok, dl, fail


def do_hf(force):
    try:
        from huggingface_hub import snapshot_download, hf_hub_download
    except Exception as e:
        print('[錯誤] 匯入 huggingface_hub 失敗（%s）；請先讓 setup 完成 pip 安裝再重跑。' % e)
        return 0, 0, len(HF_SNAPSHOTS) + len(HF_SINGLE)

    ok = dl = fail = 0
    for repo, sub, required in HF_SNAPSHOTS:
        target = os.path.join(MODELS_DIR, sub)
        have = all(
            os.path.isfile(os.path.join(target, r)) and os.path.getsize(os.path.join(target, r)) > 0
            for r in required
        )
        if have and not force:
            print('[檢查] %s ... OK' % sub)
            ok += 1
            continue
        print('[下載] %s（HuggingFace %s）...' % (sub, repo))
        try:
            snapshot_download(repo_id=repo, local_dir=target, allow_patterns=required)
            print('  [完成] %s' % sub)
            dl += 1
        except Exception as e:
            print('  [錯誤] %s 下載失敗：%s: %s' % (sub, type(e).__name__, e))
            fail += 1

    for repo, fname, sub in HF_SINGLE:
        target = os.path.join(MODELS_DIR, sub)
        dest = os.path.join(target, fname)
        if os.path.isfile(dest) and os.path.getsize(dest) > 0 and not force:
            print('[檢查] %s/%s ... OK' % (sub, fname))
            ok += 1
            continue
        print('[下載] %s/%s（HuggingFace %s）...' % (sub, fname, repo))
        try:
            hf_hub_download(repo_id=repo, filename=fname, local_dir=target)
            print('  [完成] %s' % fname)
            dl += 1
        except Exception as e:
            print('  [錯誤] %s 下載失敗：%s: %s' % (fname, type(e).__name__, e))
            fail += 1
    return ok, dl, fail


def main():
    force = '--force' in sys.argv[1:]
    os.makedirs(MODELS_DIR, exist_ok=True)
    print('============================================')
    print(' 檢查並補齊模型檔 / Verifying model files')
    if force:
        print(' (--force：全部重新校驗 / 重抓)')
    print('============================================')
    o1, d1, f1 = do_hashed(force)
    o2, d2, f2 = do_hf(force)
    ok, dl, fail = o1 + o2, d1 + d2, f1 + f2
    print('--------------------------------------------')
    print(' 完好 %d   新增/修復 %d   失敗 %d' % (ok, dl, fail))
    print('--------------------------------------------')
    if fail:
        print('[!] 有檔案未能補齊；請檢查網路後重跑：python download_models.py')
        return 1
    print('所有模型就緒。')
    return 0


if __name__ == '__main__':
    sys.exit(main())

"""線上更新：比對 GitHub 最新 commit、列出更新內容、下載套用後重啟。

設計：
- app/VERSION 記目前版本（commit SHA）。
- check：抓 GitHub 最新 commit + compare，回傳是否有更新與變更清單。
- apply：下載 main 原始碼 zip，覆蓋程式碼（不動 models/.venv/.env/result/使用者字型），
         更新 VERSION，再 spawn 外部 helper 殺掉本進程樹並重啟 start.bat。
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import httpx

REPO = "DragonMeow1012/DragonMeow-MangaTranslator"
APP_DIR = Path(__file__).resolve().parent.parent          # .../app
ROOT_DIR = APP_DIR.parent                                  # 含 setup.bat / start.bat 的根目錄
VERSION_FILE = APP_DIR / "VERSION"

# 套用更新時「絕不覆蓋 / 刪除」的使用者資料（zip 內本來就沒有，這裡再保險跳過）
_PROTECT = {"models", ".venv", ".env", "result", "logs", os.path.join("fonts", "user")}

_UA = {"User-Agent": "DragonMeow-MangaTranslator-Updater"}


def read_local_version() -> str:
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


async def check_update() -> dict:
    """回傳 {current, latest, latest_date, update_available, changelog:[...], count}。"""
    local = read_local_version()
    async with httpx.AsyncClient(timeout=20.0, headers=_UA, follow_redirects=True) as cli:
        r = await cli.get(f"https://api.github.com/repos/{REPO}/commits/main")
        if r.status_code != 200:
            raise RuntimeError(f"GitHub API {r.status_code}: {r.text[:200]}")
        head = r.json()
        latest = head.get("sha", "")
        latest_date = (head.get("commit", {}).get("author", {}) or {}).get("date", "")

        available = bool(local) and bool(latest) and local != latest
        changelog, count = [], 0
        if available:
            cmp = await cli.get(f"https://api.github.com/repos/{REPO}/compare/{local}...{latest}")
            if cmp.status_code == 200:
                data = cmp.json()
                count = data.get("ahead_by", 0)
                for c in (data.get("commits") or []):
                    msg = (c.get("commit", {}).get("message", "") or "").split("\n")[0]
                    if msg and not msg.lower().startswith("merge "):
                        changelog.append(msg)
                changelog = changelog[::-1][:20]   # 新到舊、最多 20 條
        # 沒寫 VERSION（如 git clone 自行跑）→ 無從比對，視為已是最新
        if not local:
            available = False
    return {
        "current": local[:7] if local else "unknown",
        "latest": latest[:7] if latest else "",
        "latest_full": latest,
        "latest_date": latest_date,
        "update_available": available,
        "changelog": changelog,
        "count": count or len(changelog),
    }


def _merge_copy(src: Path, dst: Path):
    """把 src 內容覆蓋合併進 dst：覆寫同名、補新檔，但不刪 dst 既有（保護使用者資料）。"""
    for item in src.iterdir():
        rel = item.name
        if rel in _PROTECT:
            continue
        target = dst / rel
        if item.is_dir():
            target.mkdir(exist_ok=True)
            # fonts/ 內 user/ 子資料夾要保護
            if rel == "fonts":
                for f in item.iterdir():
                    if f.is_dir():
                        (target / f.name).mkdir(exist_ok=True)
                        _merge_copy(f, target / f.name)
                    else:
                        shutil.copy2(f, target / f.name)
            else:
                _merge_copy(item, target)
        else:
            shutil.copy2(item, target)


async def apply_update() -> dict:
    """下載最新原始碼覆蓋、更新 VERSION，回傳 {applied, latest}。不在此重啟。"""
    info = await check_update()
    latest = info.get("latest_full")
    if not latest:
        raise RuntimeError("no latest version")

    url = f"https://codeload.github.com/{REPO}/zip/refs/heads/main"
    async with httpx.AsyncClient(timeout=180.0, headers=_UA, follow_redirects=True) as cli:
        resp = await cli.get(url)
        if resp.status_code != 200:
            raise RuntimeError(f"download {resp.status_code}")
        blob = resp.content

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            z.extractall(tmp)
        # 解出的頂層資料夾：DragonMeow-MangaTranslator-main/
        roots = [p for p in tmp.iterdir() if p.is_dir()]
        if not roots:
            raise RuntimeError("empty archive")
        _merge_copy(roots[0], ROOT_DIR)

    VERSION_FILE.write_text(latest, encoding="utf-8")
    return {"applied": True, "latest": latest[:7]}


def schedule_restart():
    """spawn 外部 helper：等幾秒 → 殺本進程樹（含 worker）→ 重啟 start.bat。"""
    pid = os.getpid()
    start_bat = ROOT_DIR / "start.bat"
    if sys.platform == "win32":
        # /T 連子進程（worker）一起殺；start 重新開一個視窗跑 start.bat
        cmd = (
            f'timeout /t 3 /nobreak >nul & '
            f'taskkill /PID {pid} /T /F >nul 2>&1 & '
            f'cd /d "{ROOT_DIR}" & start "" "{start_bat}"'
        )
        subprocess.Popen(["cmd", "/c", cmd], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    else:
        sh = f'sleep 3; kill -TERM -{pid} 2>/dev/null; cd "{ROOT_DIR}" && bash start.sh'
        subprocess.Popen(["bash", "-c", sh], start_new_session=True)

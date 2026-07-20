"""Launch the single interactive Windows updater used by manual and web flows."""

import subprocess
import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = APP_DIR.parent
UPDATE_BAT = ROOT_DIR / "update.bat"


def launch_updater() -> dict:
    """Open update.bat in a separate interactive console window."""
    if sys.platform != "win32":
        raise RuntimeError("The interactive updater is currently available on Windows only")
    if not UPDATE_BAT.is_file():
        raise RuntimeError(f"Updater not found: {UPDATE_BAT}")

    command = f'start "DragonMeow Updater" "{UPDATE_BAT}" --from-web'
    subprocess.Popen(
        ["cmd.exe", "/d", "/s", "/c", command],
        cwd=str(ROOT_DIR),
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        close_fds=True,
    )
    return {"launched": True, "updater": UPDATE_BAT.name}

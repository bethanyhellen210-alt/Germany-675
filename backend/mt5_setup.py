import os
import shutil
from dotenv import load_dotenv

load_dotenv()

MT5_BASE_DIR = os.getenv("MT5_BASE_DIR", r"C:\Program Files\MetaTrader 5")
MT5_INSTANCES_DIR = os.getenv("MT5_INSTANCES_DIR", r"C:\mt5-forex-webbot\mt5_instances")

def ensure_user_terminal(user_id: str) -> str:
    safe_id = "".join(c for c in user_id if c.isalnum() or c in ("_", "-"))
    if not safe_id:
        raise ValueError("Invalid user_id")

    target_dir = os.path.join(MT5_INSTANCES_DIR, safe_id)
    target_exe = os.path.join(target_dir, "terminal64.exe")

    if os.path.exists(target_exe):
        return target_exe

    if not os.path.isdir(MT5_BASE_DIR):
        raise RuntimeError(f"MT5_BASE_DIR not found: {MT5_BASE_DIR}")

    os.makedirs(MT5_INSTANCES_DIR, exist_ok=True)
    shutil.copytree(MT5_BASE_DIR, target_dir, dirs_exist_ok=True)

    if not os.path.exists(target_exe):
        raise RuntimeError(f"terminal64.exe not found in {target_dir}")

    return target_exe
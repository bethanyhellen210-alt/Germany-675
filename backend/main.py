import os
import subprocess
import sys
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from db import add_log, get_conn, get_logs, init_db
from mt5_setup import ensure_user_terminal
from security import encrypt_text

app = FastAPI(title="Hosted MT5 Forex WebBot")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

WORKERS: dict[str, subprocess.Popen] = {}

class ConnectAccountRequest(BaseModel):
    user_id: str = Field(..., min_length=2, max_length=64)
    mt5_login: int = Field(..., gt=0)
    mt5_password: str = Field(..., min_length=1)
    mt5_server: str = Field(..., min_length=2)
    symbol: str = Field(default="EURUSD", min_length=3, max_length=20)
    lot: float = Field(default=0.01, gt=0.0, le=10.0)
    max_daily_loss: float = Field(default=50.0, gt=0.0)

@app.on_event("startup")
def on_startup() -> None:
    init_db()

@app.get("/")
def serve_ui():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.post("/api/account/save")
def save_account(req: ConnectAccountRequest):
    enc_pw = encrypt_text(req.mt5_password)
    symbol = req.symbol.upper().strip()
    server = req.mt5_server.strip()

    with get_conn() as conn:
        conn.execute("""
            INSERT INTO accounts (user_id, mt5_login, mt5_password_enc, mt5_server, symbol, lot, max_daily_loss, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                mt5_login = excluded.mt5_login,
                mt5_password_enc = excluded.mt5_password_enc,
                mt5_server = excluded.mt5_server,
                symbol = excluded.symbol,
                lot = excluded.lot,
                max_daily_loss = excluded.max_daily_loss,
                updated_at = CURRENT_TIMESTAMP
        """, (req.user_id, req.mt5_login, enc_pw, server, symbol, req.lot, req.max_daily_loss))
        conn.commit()

    add_log(req.user_id, "INFO", f"Saved MT5 credentials for login={req.mt5_login} server={server}")
    return {
        "status": "saved",
        "user_id": req.user_id,
        "mt5_login": req.mt5_login,
        "mt5_server": server,
        "symbol": symbol,
        "lot": req.lot,
        "max_daily_loss": req.max_daily_loss,
    }

@app.get("/api/account/{user_id}")
def get_account(user_id: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT user_id, mt5_login, mt5_server, symbol, lot, max_daily_loss FROM accounts WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Account not found")

    proc = WORKERS.get(user_id)
    running = proc is not None and proc.poll() is None
    return {
        **dict(row),
        "running": running,
        "pid": proc.pid if running else None,
    }

@app.post("/api/bot/start/{user_id}")
def start_bot(user_id: str):
    proc = WORKERS.get(user_id)
    if proc is not None and proc.poll() is None:
        return {"status": "already_running", "pid": proc.pid}

    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM accounts WHERE user_id = ?",
            (user_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Save MT5 credentials first")

    try:
        terminal_path = ensure_user_terminal(user_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    worker_script = os.path.join(BASE_DIR, "bot_worker.py")
    cmd = [
        sys.executable,
        worker_script,
        "--user-id", row["user_id"],
        "--terminal-path", terminal_path,
        "--login", str(row["mt5_login"]),
        "--enc-password", row["mt5_password_enc"],
        "--server", row["mt5_server"],
        "--symbol", row["symbol"],
        "--lot", str(row["lot"]),
        "--max-daily-loss", str(row["max_daily_loss"]),
    ]

    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    new_proc = subprocess.Popen(cmd, cwd=BASE_DIR, creationflags=creation_flags)
    WORKERS[user_id] = new_proc

    return {"status": "started", "pid": new_proc.pid}

@app.post("/api/bot/stop/{user_id}")
def stop_bot(user_id: str):
    proc = WORKERS.get(user_id)
    if proc is None or proc.poll() is not None:
        return {"status": "not_running"}

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()

    add_log(user_id, "INFO", "Bot stopped by user.")
    return {"status": "stopped"}

@app.get("/api/logs/{user_id}")
def logs(user_id: str):
    return {"logs": get_logs(user_id, limit=40)}
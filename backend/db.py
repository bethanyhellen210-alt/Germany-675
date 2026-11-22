import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "webbot.db")

def get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                user_id TEXT PRIMARY KEY,
                mt5_login INTEGER NOT NULL,
                mt5_password_enc TEXT NOT NULL,
                mt5_server TEXT NOT NULL,
                symbol TEXT NOT NULL DEFAULT 'EURUSD',
                lot REAL NOT NULL DEFAULT 0.01,
                max_daily_loss REAL NOT NULL DEFAULT 50.0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

def add_log(user_id: str, level: str, message: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO logs (user_id, level, message) VALUES (?, ?, ?)",
            (user_id, level, message),
        )
        conn.commit()

def get_logs(user_id: str, limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT level, message, created_at FROM logs WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]
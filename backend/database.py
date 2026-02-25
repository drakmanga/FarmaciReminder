import sqlite3
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "data" / "farmaci.db"))


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _run_migrations(conn):
    """Applica migrazioni incrementali allo schema esistente."""
    cur = conn.cursor()

    # Controlla che la tabella farmaci esista
    if not cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='farmaci'"
    ).fetchone():
        return

    col_info = {col["name"]: dict(col) for col in cur.execute("PRAGMA table_info(farmaci)").fetchall()}

    # Aggiunge colonne mancanti
    if "notifica_preavviso_inviata" not in col_info:
        cur.execute("ALTER TABLE farmaci ADD COLUMN notifica_preavviso_inviata BOOLEAN NOT NULL DEFAULT 0")
    if "notifica_scaduto_inviata" not in col_info:
        cur.execute("ALTER TABLE farmaci ADD COLUMN notifica_scaduto_inviata BOOLEAN NOT NULL DEFAULT 0")
    if "ultima_notifica_scaduto" not in col_info:
        cur.execute("ALTER TABLE farmaci ADD COLUMN ultima_notifica_scaduto DATE")
    conn.commit()

    # Rende data_scadenza nullable se non lo è già
    col_info = {col["name"]: dict(col) for col in cur.execute("PRAGMA table_info(farmaci)").fetchall()}
    if col_info.get("data_scadenza", {}).get("notnull", 0) == 1:
        cur.executescript("""
            PRAGMA foreign_keys=OFF;
            CREATE TABLE farmaci_migration (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                nome TEXT NOT NULL CHECK(length(nome) <= 100),
                descrizione TEXT CHECK(length(descrizione) <= 500),
                data_scadenza DATE,
                stato TEXT NOT NULL DEFAULT 'attivo'
                    CHECK(stato IN ('attivo','in_scadenza','scaduto','eliminato')),
                notifica_preavviso_inviata BOOLEAN NOT NULL DEFAULT 0,
                notifica_scaduto_inviata BOOLEAN NOT NULL DEFAULT 0,
                ultima_notifica_scaduto DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                deleted_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
            INSERT INTO farmaci_migration
            SELECT id, user_id, nome, descrizione, data_scadenza, stato,
                   notifica_preavviso_inviata, notifica_scaduto_inviata,
                   ultima_notifica_scaduto, created_at, deleted_at
            FROM farmaci;
            DROP TABLE farmaci;
            ALTER TABLE farmaci_migration RENAME TO farmaci;
            PRAGMA foreign_keys=ON;
        """)
        conn.commit()


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            timezone TEXT NOT NULL DEFAULT 'Europe/Rome',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS farmaci (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            nome TEXT NOT NULL CHECK(length(nome) <= 100),
            descrizione TEXT CHECK(length(descrizione) <= 500),
            data_scadenza DATE,
            stato TEXT NOT NULL DEFAULT 'attivo'
                CHECK(stato IN ('attivo','in_scadenza','scaduto','eliminato')),
            notifica_preavviso_inviata BOOLEAN NOT NULL DEFAULT 0,
            notifica_scaduto_inviata BOOLEAN NOT NULL DEFAULT 0,
            ultima_notifica_scaduto DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL CHECK(type IN ('INFO','WARN','ERROR')),
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.commit()
    _run_migrations(conn)
    conn.close()


def get_setting(key: str, default=None):
    """Legge un valore dalla tabella settings."""
    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    """Scrive/aggiorna un valore nella tabella settings."""
    conn = get_connection()
    conn.execute(
        """INSERT INTO settings (key, value, updated_at)
           VALUES (?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value,
           updated_at = CURRENT_TIMESTAMP""",
        (key, value),
    )
    conn.commit()
    conn.close()


def get_telegram_config() -> dict:
    """
    Restituisce la config Telegram attiva.
    Priorità per ogni campo: DB (impostato dalla UI) → config.yaml → valore vuoto.
    """
    import json, yaml
    from pathlib import Path

    yaml_token = ""
    yaml_chat_ids = []
    config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    if config_path.exists():
        try:
            with open(config_path) as f:
                cfg = yaml.safe_load(f)
            yaml_token = cfg.get("telegram_token", "")
            yaml_chat_ids = cfg.get("chat_ids", [])
        except Exception:
            pass

    token = get_setting("telegram_token") or yaml_token

    chat_ids_raw = get_setting("telegram_chat_ids")
    if chat_ids_raw:
        try:
            chat_ids = json.loads(chat_ids_raw)
        except Exception:
            chat_ids = yaml_chat_ids
    else:
        chat_ids = yaml_chat_ids

    return {"telegram_token": token, "chat_ids": chat_ids}


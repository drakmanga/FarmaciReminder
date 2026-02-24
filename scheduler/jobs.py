import sys
import threading
from pathlib import Path
from datetime import date, timedelta
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from backend.database import get_connection
from scheduler.log_manager import get_logger, db_log
logger = get_logger("scheduler.jobs")
import yaml
CONFIG_PATH = BASE_DIR / "config.yaml"
with open(CONFIG_PATH, "r") as f:
    CONFIG = yaml.safe_load(f)
_send_lock = threading.Lock()
GIORNI_PREAVVISO = 30  # giorni prima della scadenza per l avviso
def _get_telegram_config():
    """Ricarica la config Telegram dal DB a ogni chiamata (hot-reload dalla UI)."""
    from backend.database import get_telegram_config
    return get_telegram_config()
def _send_telegram_sync(chat_id: int, text: str) -> bool:
    """Invia messaggio Telegram (sincrono)."""
    try:
        cfg = _get_telegram_config()
        token = cfg["telegram_token"]
        if not token:
            logger.warning("Token Telegram non configurato")
            return False
        import requests as req_lib
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }
        r = req_lib.post(url, json=payload, timeout=5)
        return r.status_code == 200
    except Exception as e:
        logger.error(f"Errore invio Telegram a {chat_id}: {e}")
        return False
def _format_data(data_str: str) -> str:
    """Formatta una data ISO in formato italiano DD/MM/YYYY."""
    try:
        d = date.fromisoformat(data_str) if isinstance(data_str, str) else data_str
        return d.strftime("%d/%m/%Y")
    except Exception:
        return str(data_str)
def check_scadenze_farmaci():
    """
    Job giornaliero: controlla scadenze farmaci e invia notifiche Telegram.
    - Se scade entro 30 giorni (notifica preavviso non ancora inviata) -> avviso
    - Se gia scaduto (notifica scaduto non ancora inviata) -> avviso urgente
    """
    if not _send_lock.acquire(blocking=False):
        logger.debug("check_scadenze_farmaci gia in esecuzione, skip")
        return
    try:
        conn = get_connection()
        today = date.today()
        today_str = today.isoformat()
        preavviso_str = (today + timedelta(days=GIORNI_PREAVVISO)).isoformat()
        # --- FARMACI IN SCADENZA (entro 30 giorni) ---
        in_scadenza = conn.execute(
            """SELECT f.*, u.username FROM farmaci f
               JOIN users u ON f.user_id = u.id
               WHERE f.stato IN ('attivo', 'in_scadenza')
               AND f.deleted_at IS NULL
               AND f.data_scadenza > ?
               AND f.data_scadenza <= ?
               AND f.notifica_preavviso_inviata = 0""",
            (today_str, preavviso_str),
        ).fetchall()
        for row in in_scadenza:
            farmaco = dict(row)
            ds = date.fromisoformat(farmaco["data_scadenza"])
            giorni = (ds - today).days
            desc = f"\n<i>{farmaco['descrizione']}</i>" if farmaco.get("descrizione") else ""
            text = (
                f"<b>FARMACO IN SCADENZA</b>\n\n"
                f"<b>{farmaco['nome']}</b>{desc}\n\n"
                f"Scade il <b>{_format_data(farmaco['data_scadenza'])}</b> "
                f"(tra <b>{giorni} giorni</b>)\n\n"
                f"Ricordati di rinnovare o sostituire il farmaco."
            )
            success = False
            for chat_id in _get_telegram_config()["chat_ids"]:
                ok = _send_telegram_sync(chat_id, text)
                success = success or ok
            if success:
                conn.execute(
                    """UPDATE farmaci SET stato = 'in_scadenza',
                       notifica_preavviso_inviata = 1 WHERE id = ?""",
                    (farmaco["id"],),
                )
                conn.commit()
                logger.info(f"Preavviso scadenza inviato per farmaco {farmaco['id']} ({farmaco['nome']})")
                db_log("INFO", f"Preavviso scadenza farmaco {farmaco['id']} ({farmaco['nome']})")
            else:
                logger.warning(f"Invio preavviso fallito per farmaco {farmaco['id']}")
        # --- FARMACI SCADUTI ---
        scaduti = conn.execute(
            """SELECT f.*, u.username FROM farmaci f
               JOIN users u ON f.user_id = u.id
               WHERE f.stato IN ('attivo', 'in_scadenza')
               AND f.deleted_at IS NULL
               AND f.data_scadenza <= ?
               AND f.notifica_scaduto_inviata = 0""",
            (today_str,),
        ).fetchall()
        for row in scaduti:
            farmaco = dict(row)
            desc = f"\n<i>{farmaco['descrizione']}</i>" if farmaco.get("descrizione") else ""
            text = (
                f"<b>FARMACO SCADUTO</b>\n\n"
                f"<b>{farmaco['nome']}</b>{desc}\n\n"
                f"Scaduto il <b>{_format_data(farmaco['data_scadenza'])}</b>\n\n"
                f"<b>Sostituire immediatamente!</b> Non utilizzare farmaci scaduti."
            )
            success = False
            for chat_id in _get_telegram_config()["chat_ids"]:
                ok = _send_telegram_sync(chat_id, text)
                success = success or ok
            if success:
                conn.execute(
                    """UPDATE farmaci SET stato = 'scaduto',
                       notifica_scaduto_inviata = 1 WHERE id = ?""",
                    (farmaco["id"],),
                )
                conn.commit()
                logger.info(f"Notifica scaduto inviata per farmaco {farmaco['id']} ({farmaco['nome']})")
                db_log("INFO", f"Notifica scaduto farmaco {farmaco['id']} ({farmaco['nome']})")
            else:
                logger.warning(f"Invio notifica scaduto fallito per farmaco {farmaco['id']}")
        conn.close()
    except Exception as e:
        logger.error(f"Errore check_scadenze_farmaci: {e}")
        db_log("ERROR", str(e))
    finally:
        _send_lock.release()
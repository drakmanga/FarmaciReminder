import sys
import asyncio
from pathlib import Path
from datetime import date

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import yaml
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)
from scheduler.log_manager import get_logger
from backend.database import get_connection, get_telegram_config

logger = get_logger("bot.telegram")

CONFIG_PATH = BASE_DIR / "config.yaml"
with open(CONFIG_PATH, "r") as f:
    CONFIG = yaml.safe_load(f)

POLLING_INTERVAL = CONFIG.get("polling_interval_sec", 2)


def _get_authorized_ids() -> set:
    """Ricarica i chat ID autorizzati dal DB (hot-reload dalla UI)."""
    cfg = get_telegram_config()
    return set(cfg.get("chat_ids", []))


def _is_authorized(update: Update) -> bool:
    cid = update.effective_chat.id if update.effective_chat else None
    return cid in _get_authorized_ids()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        await update.message.reply_text("⛔ Non autorizzato.")
        return
    await update.message.reply_text(
        "👋 Ciao! Sono il tuo <b>FarmaciReminder</b> 💊\n\n"
        "Riceverai notifiche automatiche quando un farmaco:\n"
        "  ⚠️ <b>è in scadenza</b> (entro 30 giorni)\n"
        "  🚨 <b>è scaduto</b>\n\n"
        "Comandi disponibili:\n"
        "/lista — Lista completa di tutti i farmaci\n"
        "/farmaci — Solo farmaci in scadenza o scaduti\n"
        "/start — Mostra questo messaggio",
        parse_mode="HTML"
    )


async def lista_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        await update.message.reply_text("⛔ Non autorizzato.")
        return

    conn = get_connection()
    rows = conn.execute(
        """SELECT nome, descrizione, data_scadenza, stato
           FROM farmaci
           WHERE stato != 'eliminato'
           ORDER BY nome ASC"""
    ).fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(
            "💊 <b>Nessun farmaco registrato.</b>",
            parse_mode="HTML"
        )
        return

    def fmt_farmaco(r):
        if r["stato"] == "scaduto":
            emoji = "🚨"
        elif r["stato"] == "in_scadenza":
            emoji = "⚠️"
        else:
            emoji = "✅"

        desc = f" — {r['descrizione']}" if r["descrizione"] else ""
        riga1 = f"{emoji} {r['nome']}{desc}"

        if r["data_scadenza"] is None:
            riga2 = "   📅 ∞ Nessuna scadenza"
        else:
            ds = date.fromisoformat(r["data_scadenza"])
            giorni = (ds - date.today()).days
            data_fmt = ds.strftime("%d/%m/%Y")
            if giorni < 0:
                riga2 = f"   📅 Scaduto da {abs(giorni)} gg ({data_fmt})"
            elif giorni == 0:
                riga2 = f"   📅 Scade oggi ({data_fmt})"
            else:
                riga2 = f"   📅 Scade il {data_fmt} (tra {giorni} gg)"

        return f"{riga1}\n{riga2}"

    testo = f"💊 <b>Lista completa farmaci:</b>\n\n" + "\n\n".join(fmt_farmaco(r) for r in rows)
    await update.message.reply_text(testo, parse_mode="HTML")


async def farmaci_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        await update.message.reply_text("⛔ Non autorizzato.")
        return

    conn = get_connection()
    today = date.today().isoformat()
    rows = conn.execute(
        """SELECT nome, descrizione, data_scadenza, stato
           FROM farmaci
           WHERE stato IN ('in_scadenza', 'scaduto')
           AND deleted_at IS NULL
           ORDER BY data_scadenza ASC"""
    ).fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(
            "✅ <b>Nessun farmaco in scadenza o scaduto.</b>\n\n"
            "Tutti i tuoi farmaci sono nella norma! 🎉",
            parse_mode="HTML"
        )
        return

    lines = ["💊 <b>Farmaci da controllare:</b>\n"]
    for r in rows:
        stato_emoji = "🚨" if r["stato"] == "scaduto" else "⚠️"
        ds = date.fromisoformat(r["data_scadenza"])
        giorni = (ds - date.today()).days
        data_fmt = ds.strftime("%d/%m/%Y")
        if giorni < 0:
            scad_str = f"<b>Scaduto da {abs(giorni)} giorni</b> ({data_fmt})"
        else:
            scad_str = f"Scade il {data_fmt} (tra {giorni} giorni)"
        desc = f" — <i>{r['descrizione']}</i>" if r["descrizione"] else ""
        lines.append(f"{stato_emoji} <b>{r['nome']}</b>{desc}\n   📅 {scad_str}")

    await update.message.reply_text("\n\n".join(lines), parse_mode="HTML")


def start_bot():
    """Avvia il bot in polling (blocca il thread). Ricarica il token dal DB."""
    cfg = get_telegram_config()
    token = cfg.get("telegram_token", "")

    if not token or token == "BOT_TOKEN_QUI":
        logger.warning("Token Telegram non configurato, bot non avviato.")
        return

    async def _run():
        app = ApplicationBuilder().token(token).build()
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("lista", lista_command))
        app.add_handler(CommandHandler("farmaci", farmaci_command))

        await app.initialize()
        await app.start()
        await app.updater.start_polling(poll_interval=POLLING_INTERVAL)
        logger.info("Bot Telegram FarmaciReminder avviato in polling")

        # Tieni vivo il thread finché l'applicazione gira
        while app.running:
            await asyncio.sleep(1)

        await app.updater.stop()
        await app.stop()
        await app.shutdown()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run())
    except Exception as e:
        logger.error(f"Bot arrestato: {e}")
    finally:
        loop.close()


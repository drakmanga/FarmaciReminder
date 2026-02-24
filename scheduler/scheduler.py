import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import yaml
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from scheduler.jobs import check_scadenze_farmaci
from scheduler.backup import run_backup
from scheduler.log_manager import get_logger

logger = get_logger("scheduler.main")

CONFIG_PATH = BASE_DIR / "config.yaml"
with open(CONFIG_PATH, "r") as f:
    CONFIG = yaml.safe_load(f)

_scheduler: BackgroundScheduler = None


def start_scheduler():
    global _scheduler

    _scheduler = BackgroundScheduler(timezone="UTC")

    # Esegui subito al boot per notificare eventuali scadenze già presenti
    logger.info("Controllo scadenze farmaci al boot...")
    check_scadenze_farmaci()
    logger.info("Controllo boot completato")

    # Job giornaliero: ogni giorno alle 09:00 (ora di Roma)
    _scheduler.add_job(
        check_scadenze_farmaci,
        trigger=CronTrigger(hour=9, minute=0, timezone="Europe/Rome"),
        id="check_scadenze",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Backup giornaliero
    _scheduler.add_job(
        run_backup,
        trigger=IntervalTrigger(hours=24),
        id="daily_backup",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    _scheduler.start()
    logger.info("Scheduler FarmaciReminder avviato (check scadenze ogni giorno alle 09:00)")

    import time
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        _scheduler.shutdown()
        logger.info("Scheduler fermato")


def get_scheduler() -> BackgroundScheduler:
    return _scheduler

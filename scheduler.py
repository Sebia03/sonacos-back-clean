from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import atexit

scheduler = None

def init_scheduler(app):
    global scheduler

    from email_report import send_weekly_reports
    from alert_sync import sync_all_alerts

    scheduler = BackgroundScheduler()

    # Rapport hebdomadaire — chaque lundi à 8h00
    # misfire_grace_time : si le serveur était éteint au moment prévu,
    # le job se déclenche quand même au prochain démarrage (dans la fenêtre de 6h)
    scheduler.add_job(
        func=send_weekly_reports,
        trigger=CronTrigger(day_of_week="mon", hour=8, minute=0),
        id="weekly_report",
        name="Rapport hebdomadaire VigilOS",
        replace_existing=True,
        misfire_grace_time=6 * 3600,
    )

    # Sync alertes — toutes les heures
    scheduler.add_job(
        func=sync_all_alerts,
        trigger=CronTrigger(minute=0),
        id="sync_alerts",
        name="Synchronisation alertes",
        replace_existing=True,
        misfire_grace_time=1800,
    )

    # Nettoyage alertes — chaque jour à minuit
    scheduler.add_job(
        func=cleanup_alerts,
        trigger=CronTrigger(hour=0, minute=0),
        id="cleanup_alerts",
        name="Nettoyage alertes anciennes",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.start()
    print("✅ Scheduler démarré :")
    print("   — Rapport hebdomadaire : lundi 8h00")
    print("   — Sync alertes         : toutes les heures")
    print("   — Nettoyage alertes    : chaque jour à minuit")

    atexit.register(lambda: scheduler.shutdown())


def cleanup_alerts():
    from database import cleanup_old_alerts
    cleanup_old_alerts(days=7)
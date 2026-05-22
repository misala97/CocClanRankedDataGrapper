import time
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from app import app, clan_members_update, ranked_week_update, battle_log_update

logging.basicConfig(level=logging.INFO)

if __name__ == '__main__':
    logging.info("Starting standalone scheduler...")
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=clan_members_update, trigger="interval", minutes=1)
    scheduler.add_job(func=ranked_week_update, trigger="interval", minutes=2)
    scheduler.add_job(func=battle_log_update, trigger="interval", minutes=2)
    scheduler.start()
    
    try:
        # Keep the script running
        while True:
            time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
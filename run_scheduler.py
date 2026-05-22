import time
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from app import app, task_update_clan_members, task_update_ranked_weeks, battle_log_update

logging.basicConfig(level=logging.INFO)

if __name__ == '__main__':
    logging.info("Starting standalone scheduler...")
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=task_update_clan_members, trigger="interval", minutes=10, max_instances=1)
    scheduler.add_job(func=task_update_ranked_weeks, trigger="interval", minutes=10,  max_instances=1)
    scheduler.add_job(func=battle_log_update, trigger="interval", minutes=5,  max_instances=1)
    scheduler.start()
    
    try:
        # Keep the script running
        while True:
            time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
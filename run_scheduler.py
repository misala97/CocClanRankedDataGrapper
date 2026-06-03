import time
import logging
from apscheduler.schedulers.background import BackgroundScheduler

from app import app
from tasks.battle_logs   import task_update_battle_logs
from tasks.raid_weekend  import task_update_raid_weekend
from tasks.ranked_weeks  import task_update_ranked_weeks
from tasks.clan_war      import task_update_clan_war
from tasks.clan_members  import task_update_clan_members
from tasks.cwl           import task_update_cwl

if __name__ == '__main__':
    logging.info("Starting standalone scheduler...")
    import extensions
    scheduler = BackgroundScheduler()
    extensions.scheduler = scheduler

    scheduler.add_job(func=task_update_clan_members, trigger="interval", minutes=5,  max_instances=1)
    scheduler.add_job(func=task_update_ranked_weeks, trigger="interval", minutes=10, max_instances=1)
    scheduler.add_job(func=task_update_battle_logs,  trigger="interval", minutes=5,  max_instances=1)
    scheduler.add_job(func=task_update_raid_weekend, trigger="interval", minutes=3,  max_instances=1, id='raid_weekend_update')
    scheduler.add_job(func=task_update_clan_war,     trigger="interval", hours=1,    max_instances=1, id='clan_war_update')
    scheduler.add_job(func=task_update_cwl,          trigger="interval", hours=1,    max_instances=1, id='cwl_update')
    scheduler.start()

    task_update_cwl()
    task_update_raid_weekend()
    task_update_clan_war()
    task_update_clan_members()
    task_update_ranked_weeks()
    task_update_battle_logs()
    

    try:
        while True:
            time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()

import glob
import os
import time
import logging
from apscheduler.schedulers.background import BackgroundScheduler

from logging_config import reset_task_logs
from services.helpers import LOCAL_TZ
from tasks import LOCK_DIR
from tasks.schedule import active_minutes

reset_task_logs(
    'logs/task_battle_logs.log',
    'logs/raid_weekend.log',
    'logs/task_ranked_weeks.log',
    'logs/clan_war.log',
    'logs/task_clan_members.log',
    'logs/cwl.log',
)

# A fresh process start means nothing can legitimately hold a task lock yet —
# clear any stale lock files left behind by a previous crash.
for _stale_lock in glob.glob(os.path.join(LOCK_DIR, '*.lock')):
    os.remove(_stale_lock)

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
    scheduler = BackgroundScheduler(timezone=LOCAL_TZ)
    extensions.scheduler = scheduler

    # Intervals come from tasks/schedule.py — the dynamic three retune themselves
    # from the same registry, so the number is written in exactly one place.
    scheduler.add_job(func=task_update_clan_members, trigger="interval",
                      minutes=active_minutes('task_update_clan_members'), max_instances=1)
    scheduler.add_job(func=task_update_ranked_weeks, trigger="interval",
                      minutes=active_minutes('task_update_ranked_weeks'), max_instances=1)
    scheduler.add_job(func=task_update_battle_logs, trigger="interval",
                      minutes=active_minutes('task_update_battle_logs'), max_instances=1)
    scheduler.add_job(func=task_update_raid_weekend, trigger="interval",
                      minutes=active_minutes('task_update_raid_weekend'),
                      max_instances=1, id='raid_weekend_update')
    scheduler.add_job(func=task_update_clan_war, trigger="interval",
                      minutes=active_minutes('task_update_clan_war'),
                      max_instances=1, id='clan_war_update')
    scheduler.add_job(func=task_update_cwl, trigger="interval",
                      minutes=active_minutes('task_update_cwl'),
                      max_instances=1, id='cwl_update')
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

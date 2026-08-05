import datetime as dt
import time

from logging_config import setup_task_logger
from services.helpers import json_get, JSON_BATTLE_LOG_DATA
from tasks import task_lock
from tasks.schedule import active_minutes

battle_logger = setup_task_logger('battle_logs', 'logs/task_battle_logs.log')


@task_lock(logger=battle_logger)
def task_update_battle_logs():
    from app import app
    from extensions import db
    from services.db import (
        db_player_get_all, create_db_battle_log,
        db_battle_log_get, db_battle_log_create_new,
        db_finalize_uptime,
    )
    from services.api import api_fetch_battlelog

    t0 = time.time()
    battle_logger.info(f"Starting at {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")

    logs_added = 0

    with app.app_context():
        db_players_in_clan = db_player_get_all()
        for db_player in db_players_in_clan:
            try:
                battle_log_api = api_fetch_battlelog(db_player.tag)
                battle_items = json_get(battle_log_api, JSON_BATTLE_LOG_DATA.ITEMS)
            except Exception as e:
                battle_logger.warning(f"Could not fetch battle log for {db_player.name}: {e}")
                continue

            for battle_api in battle_items:
                try:
                    tmp_battle_log = create_db_battle_log(db_player, battle_api)
                    if not tmp_battle_log.opponent_tag:
                        battle_logger.debug("Opponent player tag empty — skipping")
                        continue
                    if not db_battle_log_get(db_player, battle_api):
                        db_battle_log_create_new(tmp_battle_log)
                        logs_added += 1
                except Exception as e:
                    battle_logger.error(f"Failed to add battle log for {db_player.name}: {e}", exc_info=True)
                    db.session.rollback()
                    continue
            db.session.commit()

        db_finalize_uptime(task_update_battle_logs.__name__, t0, summary=f"logs_added={logs_added}",
                           logger=battle_logger,
                           interval_minutes=active_minutes(task_update_battle_logs.__name__))

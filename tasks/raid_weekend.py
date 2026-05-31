import datetime as dt
import time

from logging_config import setup_task_logger
from services.helpers import json_get, JSON_RAID_WEEKEND_DATA

raid_weekend_logger = setup_task_logger('raid_weekend', 'logs/raid_weekend.log')


def task_update_raid_weekend(run_always: bool = False):
    from app import app, CLAN_TAG
    from extensions import db
    from services.db import (
        create_db_raid_weekend_from_api, db_raid_weekend_get,
        db_raid_weekend_create_new, db_raid_weekend_update,
        create_db_raid_weekend_log, db_raid_weekend_log_get,
        db_raid_weekend_log_create_new,
        create_db_player_from_api, db_player_create_new, db_player_get,
        db_finalize_uptime,
    )
    from services.api import api_fetch_raid_weekend, api_fetch_player_data
    from models import Player

    t0 = time.time()
    raid_weekend_logger.info(f"Starting at {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")

    status = 'success'
    error_msg = None
    logs_added = 0

    with app.app_context():
        if dt.datetime.now(dt.timezone.utc).weekday() not in (4, 5, 6, 0) and not run_always:
            raid_weekend_logger.info("Skipping — not raid weekend.")
            db_finalize_uptime(task_update_raid_weekend.__name__, t0, 'skipped', summary='not_weekend', logger=raid_weekend_logger)
            return

        try:
            raid_weekend_all_api = api_fetch_raid_weekend(CLAN_TAG)
            current_raid_weekend = json_get(raid_weekend_all_api, JSON_RAID_WEEKEND_DATA.ITEMS)[0]
        except Exception as e:
            raid_weekend_logger.warning(f"Could not fetch raid weekend: {e}", exc_info=True)
            db_finalize_uptime(task_update_raid_weekend.__name__, t0, 'error', str(e), logger=raid_weekend_logger)
            return

        try:
            tmp_raid_weekend = create_db_raid_weekend_from_api(current_raid_weekend)
            raid_weekend = db_raid_weekend_get(tmp_raid_weekend.startTime, tmp_raid_weekend.endTime)
            if not raid_weekend:
                raid_weekend = db_raid_weekend_create_new(tmp_raid_weekend)
            else:
                db_raid_weekend_update(raid_weekend, tmp_raid_weekend)
        except Exception as e:
            raid_weekend_logger.error(f"Failed to update raid weekend: {e}", exc_info=True)
            db.session.rollback()
            db_finalize_uptime(task_update_raid_weekend.__name__, t0, 'error', str(e), logger=raid_weekend_logger)
            return
        db.session.commit()

        try:
            attack_logs_api = json_get(current_raid_weekend, JSON_RAID_WEEKEND_DATA.ITEMS_ATTACKLOG)
        except Exception as e:
            raid_weekend_logger.warning(f"Could not get attack log for raid weekend: {e}", exc_info=True)
            db_finalize_uptime(task_update_raid_weekend.__name__, t0, 'error', str(e), logger=raid_weekend_logger)
            return

        try:
            for attack_log_api in attack_logs_api:
                districts_api = json_get(attack_log_api, JSON_RAID_WEEKEND_DATA.ITEMS_ATTACKLOG_DISTRICTS)
                for district_api in districts_api:
                    attacks_api = json_get(district_api, JSON_RAID_WEEKEND_DATA.ITEMS_ATTACKLOG_DISTRICTS_ATTACKS, raise_on_missing=False)
                    if attacks_api is None:
                        continue

                    sorted_attacks_api = sorted(attacks_api, key=lambda x: x['destructionPercent'])
                    previous_percent = 0
                    for attack_api in sorted_attacks_api:
                        current_percent = json_get(attack_api, JSON_RAID_WEEKEND_DATA.ITEMS_ATTACKLOG_DISTRICTS_ATTACKS_DESTRUCTION_PERCENT)
                        percentage_done = current_percent - previous_percent
                        player_tag      = json_get(attack_api, JSON_RAID_WEEKEND_DATA.ITEMS_ATTACKLOG_DISTRICTS_ATTACKS_ATTACKER.TAG)
                        district_name   = json_get(district_api, JSON_RAID_WEEKEND_DATA.ITEMS_ATTACKLOG_DISTRICTS_NAME)
                        stars           = json_get(attack_api, JSON_RAID_WEEKEND_DATA.ITEMS_ATTACKLOG_DISTRICTS_ATTACKS_DESTRUCTION_STARS)
                        defender_name   = json_get(attack_log_api, JSON_RAID_WEEKEND_DATA.ITEMS_ATTACKLOG_DEFENDER.NAME)
                        defender_tag    = json_get(attack_log_api, JSON_RAID_WEEKEND_DATA.ITEMS_ATTACKLOG_DEFENDER.TAG)
                        district_level  = json_get(district_api, JSON_RAID_WEEKEND_DATA.ITEMS_ATTACKLOG_DISTRICTS_HALLLEVEL)

                        member = next((m for m in json_get(current_raid_weekend, JSON_RAID_WEEKEND_DATA.ITEMS_MEMBERS) if json_get(m, JSON_RAID_WEEKEND_DATA.ITEMS_MEMBERS_TAG) == player_tag), None)
                        total_loot_all_attacks = member["capitalResourcesLooted"] if member else None

                        if not Player.query.filter_by(tag=player_tag).first():
                            try:
                                player_api = api_fetch_player_data(player_tag)
                                tmp_player = create_db_player_from_api(player_api)
                                db_player_create_new(tmp_player)
                                db.session.flush()
                            except Exception as e:
                                raid_weekend_logger.warning(f"Could not auto-create player {player_tag}: {e}")
                                previous_percent = current_percent
                                continue

                        previous_percent = current_percent
                        tmp_log = create_db_raid_weekend_log(raid_weekend, player_tag, district_name, 0, percentage_done, current_percent, stars, defender_tag, defender_name, district_level, total_loot_all_attacks)
                        if not db_raid_weekend_log_get(raid_weekend, defender_tag, district_name, percentage_done, current_percent):
                            db_raid_weekend_log_create_new(tmp_log)
                            logs_added += 1
        except Exception as e:
            raid_weekend_logger.error(f"Failed to create raid weekend logs: {e}", exc_info=True)
            db.session.rollback()
            status = 'error'
            error_msg = str(e)
        db.session.commit()

        db_finalize_uptime(
            task_update_raid_weekend.__name__, t0, status, error_msg,
            summary=f"logs_added={logs_added}",
            logger=raid_weekend_logger,
        )

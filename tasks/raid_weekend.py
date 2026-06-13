import datetime as dt
import time

from logging_config import setup_task_logger
from services.helpers import json_get, JSON_RAID_WEEKEND_DATA
from tasks import task_lock

raid_weekend_logger = setup_task_logger('raid_weekend', 'logs/raid_weekend.log')


@task_lock(logger=raid_weekend_logger)
def task_update_raid_weekend():
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
        try:
            raid_weekend_all_api = api_fetch_raid_weekend(CLAN_TAG)
            current_raid_weekend = json_get(raid_weekend_all_api, JSON_RAID_WEEKEND_DATA.ITEMS)[0]
        except Exception as e:
            raid_weekend_logger.warning(f"Could not fetch raid weekend: {e}", exc_info=True)
            db_finalize_uptime(task_update_raid_weekend.__name__, t0, 'error', str(e), logger=raid_weekend_logger)
            return

        try:
            tmp_raid_weekend = create_db_raid_weekend_from_api(current_raid_weekend)
            raid_weekend = db_raid_weekend_get(tmp_raid_weekend.start_time, tmp_raid_weekend.end_time)
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
                        defender_badge  = json_get(attack_log_api, JSON_RAID_WEEKEND_DATA.ITEMS_ATTACKLOG_DEFENDER.BADGE, raise_on_missing=False)
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
                        tmp_log = create_db_raid_weekend_log(raid_weekend, player_tag, district_name, 0, percentage_done, current_percent, stars, defender_tag, defender_name, district_level, total_loot_all_attacks, defender_badge)
                        if not db_raid_weekend_log_get(raid_weekend, defender_tag, district_name, percentage_done, current_percent):
                            db_raid_weekend_log_create_new(tmp_log)
                            logs_added += 1
        except Exception as e:
            raid_weekend_logger.error(f"Failed to create raid weekend logs: {e}", exc_info=True)
            db.session.rollback()
            status = 'error'
            error_msg = str(e)
        db.session.commit()

        # ── Enrich logs with capital league info (one clan call per unique defender) ──
        try:
            from services.api import api_fetch_clan_data
            from models import RaidWeekendLog
            defender_tags = db.session.query(RaidWeekendLog.defender_tag).filter(
                RaidWeekendLog.raid_weekend_id == raid_weekend.id,
                RaidWeekendLog.defender_tag.isnot(None),
                RaidWeekendLog.defender_league.is_(None),
            ).distinct().all()
            for (dtag,) in defender_tags:
                try:
                    clan_data = api_fetch_clan_data(dtag)
                    league_name = ((clan_data.get('capitalLeague') or {}).get('name'))
                    db.session.query(RaidWeekendLog).filter(
                        RaidWeekendLog.raid_weekend_id == raid_weekend.id,
                        RaidWeekendLog.defender_tag == dtag,
                    ).update({'defender_league': league_name})
                except Exception as e:
                    raid_weekend_logger.warning(f"Could not fetch league for defender {dtag}: {e}")
            db.session.commit()
        except Exception as e:
            raid_weekend_logger.warning(f"League enrichment failed: {e}")
            db.session.rollback()

        db_finalize_uptime(
            task_update_raid_weekend.__name__, t0, status, error_msg,
            summary=f"logs_added={logs_added}",
            logger=raid_weekend_logger,
        )

        
        import extensions
        raid_weekend_logger.info(f"state: {raid_weekend.state}, ext: {extensions.scheduler == None}")
        if extensions.scheduler:
            if raid_weekend.state == 'ended' and raid_weekend.end_time:
                next_run = raid_weekend.end_time + dt.timedelta(days=4)
                next_run = next_run.replace(tzinfo=dt.timezone.utc)
                now = dt.datetime.now(dt.timezone.utc)
                if next_run > now:
                    extensions.scheduler.reschedule_job('raid_weekend_update', trigger='date', run_date=next_run)
                    raid_weekend_logger.info(f"Raid ended — rescheduled to {next_run} UTC")
                else:
                    # Past the expected start window — raid hasn't been manually started yet, poll until it does
                    extensions.scheduler.reschedule_job('raid_weekend_update', trigger='interval', minutes=30)
                    raid_weekend_logger.info("Waiting for new raid to be started — polling every 30 minutes")
            elif raid_weekend.state == 'ongoing':
                extensions.scheduler.reschedule_job('raid_weekend_update', trigger='interval', minutes=3)
                raid_weekend_logger.info("Raid ongoing — keeping 3-minute interval")

            
            
            

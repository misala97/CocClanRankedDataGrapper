import datetime as dt
import time

from logging_config import setup_task_logger
from services.helpers import json_get, JSON_PLAYER_DATA, JSON_RANKED_GROUP_DATA

ranked_logger = setup_task_logger('ranked_weeks', 'logs/task_ranked_weeks.log')


def task_update_ranked_weeks():
    from app import app
    from extensions import db
    from services.db import (
        db_player_get_all,
        db_ranked_week_get, create_db_ranked_week,
        db_ranked_week_create_new, db_ranked_week_update,
        db_ranked_battle_log_get, create_db_ranked_battle_log,
        db_ranked_battle_log_create_new,
        db_ranked_week_get_all_done,
        create_db_player_from_api,
        db_finalize_uptime,
    )
    from services.api import api_fetch_player_data, api_fetch_league_group

    t0 = time.time()
    ranked_logger.info(f"Starting at {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")

    weeks_created = 0
    weeks_updated = 0
    attack_logs_added = 0
    defense_logs_added = 0
    players_failed = 0

    with app.app_context():
        db_players_in_clan = db_player_get_all()
        for db_player in db_players_in_clan:
            try:
                player_api = api_fetch_player_data(db_player.tag)
            except Exception as e:
                ranked_logger.warning(f"Could not fetch player {db_player.name}: {e}")
                players_failed += 1
                continue

            try:
                season_id = json_get(player_api, JSON_PLAYER_DATA.CURRENT_LEAGUE_SEASON_ID)
                group_tag = None
                if season_id != 0:
                    group_tag = json_get(player_api, JSON_PLAYER_DATA.CURRENT_LEAGUE_GROUP_TAG)
                else:
                    ranked_logger.debug(f"No ranked season for {db_player.name}")
                    continue
            except Exception as e:
                ranked_logger.warning(f"Could not get season/group for {db_player.name}: {e}")
                players_failed += 1
                continue

            try:
                group_data_api = api_fetch_league_group(group_tag, season_id, db_player.tag)
            except Exception as e:
                ranked_logger.warning(f"Could not fetch league group for {db_player.name}: {e}")
                players_failed += 1
                continue

            try:
                ranked_week     = db_ranked_week_get(group_tag, season_id, db_player.tag)
                tmp_ranked_week = create_db_ranked_week(group_tag, season_id, player_api, group_data_api)
                if not ranked_week:
                    ranked_week = db_ranked_week_create_new(tmp_ranked_week)
                    weeks_created += 1
                else:
                    db_ranked_week_update(ranked_week, tmp_ranked_week)
                    weeks_updated += 1
            except Exception as e:
                ranked_logger.error(f"Failed to update ranked week for {db_player.name}: {e}", exc_info=True)
                db.session.rollback()
                players_failed += 1
                continue
            db.session.commit()

            try:
                attack_logs_api  = json_get(group_data_api, JSON_RANKED_GROUP_DATA.ATTACK_LOGS)
                defense_logs_api = json_get(group_data_api, JSON_RANKED_GROUP_DATA.DEFENSE_LOGS)
            except Exception as e:
                ranked_logger.warning(f"Could not get ranked logs for {db_player.name}: {e}")
                continue

            for attack_api in attack_logs_api:
                try:
                    opponent_tag  = json_get(attack_api, JSON_RANKED_GROUP_DATA.ATTACK_LOGS_OPPONENT_TAG)
                    ranked_log_db = db_ranked_battle_log_get(ranked_week, opponent_tag, True)
                    if not ranked_log_db:
                        opponent_api = api_fetch_player_data(opponent_tag)
                        db_opponent  = create_db_player_from_api(opponent_api)
                        tmp_log      = create_db_ranked_battle_log(db_opponent, attack_api, player_api, True)
                        db_ranked_battle_log_create_new(tmp_log)
                        attack_logs_added += 1
                        ranked_logger.info(f"New ranked attack log for {db_player.name}")
                except Exception as e:
                    db.session.rollback()
                    ranked_logger.warning(f"Could not add ranked attack log for {db_player.name}: {e}", exc_info=True)
                    continue
            db.session.commit()

            for defense_api in defense_logs_api:
                try:
                    opponent_tag  = json_get(defense_api, JSON_RANKED_GROUP_DATA.DEFENSE_LOGS_OPPONENT_TAG)
                    ranked_log_db = db_ranked_battle_log_get(ranked_week, opponent_tag, False)
                    if not ranked_log_db:
                        opponent_api = api_fetch_player_data(opponent_tag)
                        db_opponent  = create_db_player_from_api(opponent_api)
                        tmp_log      = create_db_ranked_battle_log(db_opponent, defense_api, player_api, False)
                        db_ranked_battle_log_create_new(tmp_log)
                        defense_logs_added += 1
                        ranked_logger.info(f"New ranked defense log for {db_player.name}")
                except Exception as e:
                    db.session.rollback()
                    ranked_logger.warning(f"Could not add ranked defense log for {db_player.name}: {e}", exc_info=True)
                    continue
            db.session.commit()

            for done_week in db_ranked_week_get_all_done(db_player):
                try:
                    tmp_ranked_week = create_db_ranked_week(done_week.league_group_tag, done_week.league_season_id, player_api, group_data_api)
                    db_ranked_week_update(done_week, tmp_ranked_week, True)
                except Exception as e:
                    ranked_logger.error(f"Failed to update done ranked week for {done_week.player.name}: {e}", exc_info=True)
                    db.session.rollback()
                    continue
                db.session.commit()

        summary = f"weeks_created={weeks_created} weeks_updated={weeks_updated} attack_logs={attack_logs_added} defense_logs={defense_logs_added} players_failed={players_failed}"
        db_finalize_uptime(task_update_ranked_weeks.__name__, t0, summary=summary, logger=ranked_logger)

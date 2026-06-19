import datetime as dt
import time

from logging_config import setup_task_logger
from services.helpers import json_get, JSON_CLAN_DATA, JSON_PLAYER_DATA
from tasks import task_lock

clan_logger = setup_task_logger('clan_members', 'logs/task_clan_members.log')


@task_lock(logger=clan_logger)
def task_update_clan_members():
    from app import app, CLAN_TAG
    from extensions import db
    from services.db import (
        db_player_update_all_inactive, db_player_get, db_player_create_new,
        db_player_update, create_db_player_from_api,
        db_finalize_uptime,
    )
    from services.api import api_fetch_clan_data

    t0 = time.time()
    clan_logger.info(f"Starting at {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")

    status = 'success'
    error_msg = None
    players_added = 0
    players_updated = 0

    with app.app_context():
        try:
            clan_api = api_fetch_clan_data(CLAN_TAG)
            member_list_api = json_get(clan_api, JSON_CLAN_DATA.MEMBER_LIST)
        except Exception as e:
            clan_logger.warning(f"Could not fetch clan data: {e}")
            db_finalize_uptime(task_update_clan_members.__name__, t0, 'error', str(e), logger=clan_logger)
            return

        try:
            from models import ClanConfig
            cwl_league = json_get(clan_api, JSON_CLAN_DATA.WAR_LEAGUE, raise_on_missing=False)
            if cwl_league:
                cfg = db.session.get(ClanConfig, CLAN_TAG) or ClanConfig(clan_tag=CLAN_TAG)
                cfg.cwl_league_name = cwl_league
                db.session.merge(cfg)
                db.session.commit()

            db_player_update_all_inactive()
            for player_api in member_list_api:
                player_tag = json_get(player_api, JSON_PLAYER_DATA.TAG)
                db_player  = db_player_get(player_tag)
                tmp_player = create_db_player_from_api(player_api)
                if not db_player:
                    clan_logger.info(f"New player: {tmp_player.name}")
                    db_player_create_new(tmp_player)
                    players_added += 1
                else:
                    db_player_update(db_player, tmp_player)
                    players_updated += 1
        except Exception as e:
            clan_logger.error(f"Task failed: {e}", exc_info=True)
            db.session.rollback()
            status = 'error'
            error_msg = str(e)

        db_finalize_uptime(
            task_update_clan_members.__name__, t0, status, error_msg,
            summary=f"added={players_added} updated={players_updated}",
            logger=clan_logger,
        )

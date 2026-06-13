import datetime as dt
import time

from logging_config import setup_task_logger
from services.helpers import json_get, JSON_CLAN_WAR_DATA
from tasks import task_lock

clan_war_logger = setup_task_logger('clan_war', 'logs/clan_war.log')


@task_lock(logger=clan_war_logger)
def task_update_clan_war():
    from app import app, CLAN_TAG
    from extensions import db
    import extensions
    from services.db import (
        create_db_clan_war, db_clan_war_get, db_clan_war_update,
        create_db_clan_war_member, create_db_clan_war_attack,
        db_finalize_uptime,
    )
    from services.api import api_fetch_clan_war, api_fetch_clan_data, api_fetch_player_data
    from services.helpers import get_name_to_id, JSON_PLAYER_DATA

    t0 = time.time()
    clan_war_logger.info(f"Starting at {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")

    status = 'success'
    error_msg = None
    members_added = 0
    attacks_added = 0
    war_action = None

    with app.app_context():
        try:
            war_data = api_fetch_clan_war(CLAN_TAG)
            state    = json_get(war_data, JSON_CLAN_WAR_DATA.STATE)
        except Exception as e:
            clan_war_logger.warning(f"Could not fetch clan war: {e}", exc_info=True)
            db_finalize_uptime(task_update_clan_war.__name__, t0, 'error', str(e), logger=clan_war_logger)
            return
        
        
        if state == 'notInWar':
            if extensions.scheduler:
                extensions.scheduler.reschedule_job('clan_war_update', trigger='interval', hours=1)
            clan_war_logger.info("No active war — skipping.")
            db_finalize_uptime(task_update_clan_war.__name__, t0, 'skipped', summary='notInWar', logger=clan_war_logger)
            return
        else:
            if extensions.scheduler:
                extensions.scheduler.reschedule_job('clan_war_update', trigger='interval', minutes=3)


        opp_tag = json_get(
            json_get(war_data, JSON_CLAN_WAR_DATA.OPPONENT, default={}, raise_on_missing=False) or {},
            JSON_CLAN_WAR_DATA.SIDE_TAG, raise_on_missing=False
        )
        clan_full_api = None
        opp_full_api  = None
        try:
            clan_full_api = api_fetch_clan_data(CLAN_TAG)
        except Exception as e:
            clan_war_logger.warning(f"Could not fetch own clan data (extended fields will be null): {e}")
        try:
            if opp_tag:
                opp_full_api = api_fetch_clan_data(opp_tag)
        except Exception as e:
            clan_war_logger.warning(f"Could not fetch opponent clan data (extended fields will be null): {e}")

        try:
            tmp_clan_war = create_db_clan_war(war_data, clan_full_api, opp_full_api)
            clan_war     = db_clan_war_get(tmp_clan_war.start_time)
            if not clan_war:
                db.session.add(tmp_clan_war)
                db.session.flush()
                clan_war = tmp_clan_war
                war_action = 'created'
                clan_war_logger.info(f"Created war vs {clan_war.opponent_name} (state={state})")
            else:
                db_clan_war_update(clan_war, tmp_clan_war)
                war_action = 'updated'
                clan_war_logger.info(f"Updated war vs {clan_war.opponent_name} (state={state})")
        except Exception as e:
            clan_war_logger.error(f"Failed to create/update clan war: {e}", exc_info=True)
            db.session.rollback()
            db_finalize_uptime(task_update_clan_war.__name__, t0, 'error', str(e), logger=clan_war_logger)
            return
        db.session.commit()

        if not clan_war.members:
            try:
                for side_data, is_opponent in (
                    (json_get(war_data, JSON_CLAN_WAR_DATA.CLAN),     False),
                    (json_get(war_data, JSON_CLAN_WAR_DATA.OPPONENT), True),
                ):
                    for member in (json_get(side_data, JSON_CLAN_WAR_DATA.SIDE_MEMBERS, raise_on_missing=False) or []):
                        player_tag = json_get(member, JSON_CLAN_WAR_DATA.MEMBER_TAG)
                        ranked_league = None
                        try:
                            player_api    = api_fetch_player_data(player_tag)
                            ranked_league = get_name_to_id(json_get(player_api, JSON_PLAYER_DATA.LEAGUE_TIER.ID, raise_on_missing=False))
                        except Exception:
                            clan_war_logger.debug(f"Could not fetch ranked league for {player_tag}")
                        db.session.add(create_db_clan_war_member(clan_war, member, is_opponent, ranked_league))
                        members_added += 1
            except Exception as e:
                clan_war_logger.error(f"Failed to save war members: {e}", exc_info=True)
                db.session.rollback()
                db_finalize_uptime(task_update_clan_war.__name__, t0, 'error', str(e), logger=clan_war_logger)
                return
            db.session.commit()

        try:
            existing_orders = {a.attack_order for a in clan_war.attacks}
            for side_data, is_opponent in (
                (json_get(war_data, JSON_CLAN_WAR_DATA.CLAN),     False),
                (json_get(war_data, JSON_CLAN_WAR_DATA.OPPONENT), True),
            ):
                for member in (json_get(side_data, JSON_CLAN_WAR_DATA.SIDE_MEMBERS, raise_on_missing=False) or []):
                    attacks = json_get(member, JSON_CLAN_WAR_DATA.MEMBER_ATTACKS, raise_on_missing=False)
                    if not attacks:
                        continue
                    for attack in attacks:
                        order = json_get(attack, JSON_CLAN_WAR_DATA.ATTACK_ORDER)
                        if order not in existing_orders:
                            db.session.add(create_db_clan_war_attack(clan_war, attack))
                            existing_orders.add(order)
                            attacks_added += 1
        except Exception as e:
            clan_war_logger.error(f"Failed to save war attacks: {e}", exc_info=True)
            db.session.rollback()
            status = 'error'
            error_msg = str(e)
        db.session.commit()

        # Auto-set war_preference_custom='out' for our members who missed both attacks
        pref_updated = 0
        if state == 'warEnded':
            try:
                from models import Player
                from collections import Counter

                attack_counts = Counter(a.attacker_tag for a in clan_war.attacks)
                for m in clan_war.members:
                    if m.is_opponent:
                        continue
                    if attack_counts[m.player_tag] == 0:
                        player = db.session.get(Player, m.player_tag)
                        if player and player.war_preference_custom != 'out':
                            player.war_preference_custom = 'out'
                            pref_updated += 1
                            clan_war_logger.info(f"Auto pref=out: {player.name} (0 attacks)")
                    # Check if the player tag appears exactly 2 times in the list
                    elif attack_counts[m.player_tag] == 2:
                        player = db.session.get(Player, m.player_tag)
                        if player and player.war_preference_custom != 'in':
                            player.war_preference_custom = 'in'
                            pref_updated += 1
                            clan_war_logger.info(f"Auto pref=in: {player.name} (2 attacks)")
                if pref_updated:
                    db.session.commit()
            except Exception as e:
                clan_war_logger.warning(f"Failed to auto-set pref=out: {e}", exc_info=True)
                db.session.rollback()

        summary = f"state={state} war={war_action} members_added={members_added} attacks_added={attacks_added} pref_out={pref_updated}"
        db_finalize_uptime(task_update_clan_war.__name__, t0, status, error_msg, summary, logger=clan_war_logger)

        
        
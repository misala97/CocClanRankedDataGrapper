import datetime as dt
import time

from logging_config import setup_task_logger
from services.helpers import json_get, get_name_to_id, JSON_CWL_GROUP_DATA, JSON_CWL_WAR_DATA, JSON_PLAYER_DATA
from tasks import task_lock

cwl_logger = setup_task_logger('cwl', 'logs/cwl.log')


@task_lock(logger=cwl_logger)
def task_update_cwl():
    from app import app, CLAN_TAG
    from extensions import db
    import extensions
    from services.db import (
        db_cwl_season_get, db_cwl_season_create, db_cwl_season_update,
        db_cwl_war_get, create_db_cwl_war, db_cwl_war_update,
        create_db_cwl_member, create_db_cwl_attack,
        create_db_cwl_clan_member,
        db_finalize_uptime,
    )
    from services.api import api_fetch_cwl_league_group, api_fetch_cwl_war, api_fetch_player_data, api_fetch_clan_data
    from models import CWLClan, CWLClanMember, CWLMember, CWLAttack

    t0 = time.time()
    cwl_logger.info(f"Starting at {dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")

    status        = 'success'
    error_msg     = None
    wars_updated  = 0
    attacks_added = 0

    with app.app_context():
        try:
            group = api_fetch_cwl_league_group(CLAN_TAG)
        except Exception as e:
            cwl_logger.warning(f"Could not fetch CWL league group: {e}")
            db_finalize_uptime(task_update_cwl.__name__, t0, 'skipped', str(e), logger=cwl_logger)
            return

        state       = json_get(group, JSON_CWL_GROUP_DATA.STATE  ) or 'unknown'
        season_str  = json_get(group, JSON_CWL_GROUP_DATA.SEASON ) or ''
        from models import ClanConfig
        cfg         = db.session.get(ClanConfig, CLAN_TAG)
        league_name = cfg.cwl_league_name if cfg else None
        
        if state == 'notInWar' or not season_str:
            if extensions.scheduler:
                extensions.scheduler.reschedule_job('cwl_update', trigger='interval', hours=1)
            cwl_logger.info("Not in CWL — skipping.")
            db_finalize_uptime(task_update_cwl.__name__, t0, 'skipped', summary='notInWar', logger=cwl_logger)
            return
        else:
            if extensions.scheduler:
                extensions.scheduler.reschedule_job('cwl_update', trigger='interval', minutes=3)

        # ── Upsert season ─────────────────────────────────────────────────────
        try:
            season = db_cwl_season_get(season_str)
            if not season:
                season = db_cwl_season_create(season_str, state, league_name)
                cwl_logger.info(f"Created CWL season {season_str} (state={state})")
            else:
                db_cwl_season_update(season, state, league_name)
                cwl_logger.info(f"Updated CWL season {season_str} (state={state})")
        except Exception as e:
            cwl_logger.error(f"Failed to upsert CWL season: {e}", exc_info=True)
            db.session.rollback()
            db_finalize_uptime(task_update_cwl.__name__, t0, 'error', str(e), logger=cwl_logger)
            return
        db.session.commit()

        # ── Upsert clans + fetch day-1 member rosters ─────────────────────────
        try:
            existing_clan_tags = {c.tag for c in CWLClan.query.filter_by(season_id=season.id).all()}
            for clan_data in json_get(group, JSON_CWL_GROUP_DATA.CLANS) or []:
                tag = json_get(clan_data, JSON_CWL_GROUP_DATA.CLAN_TAG)
                if not tag or tag in existing_clan_tags:
                    continue
                clan_obj = CWLClan(
                    season_id = season.id,
                    tag       = tag,
                    name      = json_get(clan_data, JSON_CWL_GROUP_DATA.CLAN_NAME,  ),
                    badge_url = json_get(clan_data, JSON_CWL_GROUP_DATA.CLAN_BADGE),
                )
                db.session.add(clan_obj)
                db.session.flush()

                members_in_clan = json_get(clan_data, JSON_CWL_GROUP_DATA.CLAN_MEMBERS) or []
                cwl_logger.info(f"Fetching {len(members_in_clan)} player APIs for clan {tag}")
                for member_data in members_in_clan:
                    player_tag = json_get(member_data, JSON_CWL_GROUP_DATA.CLAN_MEMBER_TAG)
                    ranked_league = None
                    if player_tag:
                        try:
                            player_api = api_fetch_player_data(player_tag)
                            league_id  = json_get(player_api, JSON_PLAYER_DATA.LEAGUE_TIER.ID)
                            ranked_league = get_name_to_id(league_id) if league_id else None
                        except Exception as e:
                            cwl_logger.warning(f"Could not fetch player {player_tag}: {e}")
                    db.session.add(create_db_cwl_clan_member(clan_obj.id, member_data, ranked_league))
        except Exception as e:
            cwl_logger.error(f"Failed to upsert CWL clans: {e}", exc_info=True)
            db.session.rollback()
            db_finalize_uptime(task_update_cwl.__name__, t0, 'error', str(e), logger=cwl_logger)
            return
        db.session.commit()

        # ── Build league lookup from day-1 roster for war member enrichment ───
        clan_member_leagues = {
            cm.player_tag: cm.ranked_league
            for cm in CWLClanMember.query.join(CWLClan).filter(CWLClan.season_id == season.id).all()
        }

        # ── Fetch and upsert each round's wars ────────────────────────────────
        rounds = json_get(group, JSON_CWL_GROUP_DATA.ROUNDS) or []
        for round_num, round_data in enumerate(rounds, start=1):
            war_tags = json_get(round_data, JSON_CWL_GROUP_DATA.ROUND_WAR_TAGS) or []
            for war_tag in war_tags:
                if war_tag == '#0':
                    continue

                try:
                    war_data = api_fetch_cwl_war(war_tag)
                except Exception as e:
                    cwl_logger.warning(f"Could not fetch CWL war {war_tag}: {e}")
                    continue

                war_state = json_get(war_data, JSON_CWL_WAR_DATA.STATE) or 'unknown'

                try:
                    war = db_cwl_war_get(war_tag)
                    if not war:
                        clan_side    = json_get(war_data, JSON_CWL_WAR_DATA.CLAN,     default={}, raise_on_missing=False) or {}
                        opp_side     = json_get(war_data, JSON_CWL_WAR_DATA.OPPONENT, default={}, raise_on_missing=False) or {}
                        clan_tag_war = json_get(clan_side, JSON_CWL_WAR_DATA.SIDE_TAG, raise_on_missing=False)
                        opp_tag_war  = json_get(opp_side,  JSON_CWL_WAR_DATA.SIDE_TAG, raise_on_missing=False)
                        clan_api = opp_api = None
                        try:
                            clan_api = api_fetch_clan_data(clan_tag_war)
                        except Exception as e:
                            cwl_logger.warning(f"Could not fetch clan data for {clan_tag_war}: {e}")
                        try:
                            opp_api = api_fetch_clan_data(opp_tag_war)
                        except Exception as e:
                            cwl_logger.warning(f"Could not fetch clan data for {opp_tag_war}: {e}")
                        war = create_db_cwl_war(season.id, round_num, war_tag, war_data, clan_api, opp_api)
                        db.session.add(war)
                        db.session.flush()
                        cwl_logger.info(f"Created CWL war R{round_num} {war_tag}: "
                                        f"{json_get(clan_side, JSON_CWL_WAR_DATA.SIDE_NAME, raise_on_missing=False)} "
                                        f"vs {json_get(opp_side, JSON_CWL_WAR_DATA.SIDE_NAME, raise_on_missing=False)}")
                    else:
                        db_cwl_war_update(war, war_data)
                except Exception as e:
                    cwl_logger.error(f"Failed to upsert CWL war {war_tag}: {e}", exc_info=True)
                    db.session.rollback()
                    continue
                db.session.commit()

                if war_state not in ('inWar', 'warEnded'):
                    wars_updated += 1
                    continue

                # ── Members (add once per war) ────────────────────────────────
                try:
                    if not CWLMember.query.filter_by(war_id=war.id).first():
                        for side_data, is_opp in (
                            (json_get(war_data, JSON_CWL_WAR_DATA.CLAN) or {}, False),
                            (json_get(war_data, JSON_CWL_WAR_DATA.OPPONENT) or {}, True),
                        ):
                            clan_tag = json_get(side_data, JSON_CWL_WAR_DATA.SIDE_TAG)
                            for member_data in json_get(side_data, JSON_CWL_WAR_DATA.SIDE_MEMBERS) or []:
                                ptag   = json_get(member_data, JSON_CWL_WAR_DATA.MEMBER_TAG)
                                league = clan_member_leagues.get(ptag)
                                db.session.add(create_db_cwl_member(war.id, clan_tag, member_data, is_opp, league))
                except Exception as e:
                    cwl_logger.error(f"Failed to save CWL members for {war_tag}: {e}", exc_info=True)
                    db.session.rollback()
                db.session.commit()

                # ── Attacks (add new ones only) ───────────────────────────────
                try:
                    existing_orders = {a.attack_order for a in CWLAttack.query.filter_by(war_id=war.id).all()}
                    for side_data in (
                        json_get(war_data, JSON_CWL_WAR_DATA.CLAN) or {},
                        json_get(war_data, JSON_CWL_WAR_DATA.OPPONENT) or {},
                    ):
                        for member_data in json_get(side_data, JSON_CWL_WAR_DATA.SIDE_MEMBERS) or []:
                            for attack_data in json_get(member_data, JSON_CWL_WAR_DATA.MEMBER_ATTACKS, raise_on_missing=False) or []:
                                order = json_get(attack_data, JSON_CWL_WAR_DATA.ATTACK_ORDER)
                                if order not in existing_orders:
                                    db.session.add(create_db_cwl_attack(war.id, attack_data))
                                    existing_orders.add(order)
                                    attacks_added += 1
                except Exception as e:
                    cwl_logger.error(f"Failed to save CWL attacks for {war_tag}: {e}", exc_info=True)
                    db.session.rollback()
                db.session.commit()

                wars_updated += 1

        summary = f"season={season_str} state={state} wars_updated={wars_updated} attacks_added={attacks_added}"
        cwl_logger.info(summary)
        db_finalize_uptime(task_update_cwl.__name__, t0, status, error_msg, summary, logger=cwl_logger)


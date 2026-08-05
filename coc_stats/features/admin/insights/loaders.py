# -*- coding: utf-8 -*-
"""The only DB-aware file under features/admin/insights.

Turns ORM rows into plain fact dicts the study modules consume, and normalizes
clan identity so no study ever sees is_opponent.

That normalization is the reason this file exists. cwl_member carries clan_tag
directly, and our clan appears there as 'the opponent' in rivals' wars because
the CWL tables hold the whole group — so is_opponent answers a different
question than clan_tag (44.8% against 67.9% for the same statistic). Meanwhile
clan_war_member has no clan_tag column at all and must take one from the war.
Two sources, two different mistakes available; both closed here, once. A
third: clan_war.clan_tag was added after the table already had rows, so the
earliest war still reads NULL, and war_fact takes a resolved fallback for it.
"""


def war_fact(attack, attacker, defender, war, clan_tag_fallback=None):
    """One clan_war_attack row plus its two member rows -> a fact dict.

    `war` supplies clan identity: clan_war_member has no clan_tag, so the
    attacker's side decides which of the war's two tags applies. clan_tag_fallback
    covers the one war row where war.clan_tag itself is NULL; it is never
    looked up here, only applied.
    """
    return {
        'src':          'war',
        'war_id':       war.id,
        'ended_at':     war.end_time,
        'attacker_tag': attack.attacker_tag,
        'attacker_th':  attacker.town_hall_level,
        'defender_th':  defender.town_hall_level,
        'stars':        attack.stars or 0,
        'destruction':  attack.destruction_pct or 0.0,
        'clan_tag':     war.opponent_tag if attacker.is_opponent else (war.clan_tag or clan_tag_fallback),
        'attack_order': attack.attack_order,
    }


def cwl_fact(attack, attacker, defender, war):
    """One cwl_attack row plus its two member rows -> a fact dict.

    clan_tag comes off the member, never from is_opponent.
    """
    return {
        'src':          'cwl',
        'war_id':       war.id,
        'ended_at':     war.end_time,
        'attacker_tag': attack.attacker_tag,
        'attacker_th':  attacker.town_hall_level,
        'defender_th':  defender.town_hall_level,
        'stars':        attack.stars or 0,
        'destruction':  attack.destruction_pct or 0.0,
        'clan_tag':     attacker.clan_tag,
        'attack_order': attack.attack_order,
    }


def resolve_clan_tag():
    """The clan_tag off the most recently ended war that has one.

    clan_war holds exactly one clan's wars (see module docstring), so any row
    with a non-NULL clan_tag names it — used to backfill the one row where the
    column itself is NULL. Requires an app context.
    """
    from models import ClanWar

    war = (ClanWar.query
           .filter(ClanWar.clan_tag.isnot(None))
           .order_by(ClanWar.end_time.desc())
           .first())
    return war.clan_tag if war else None


def load_attack_facts():
    """Every war and CWL attack as a fact dict. Requires an app context.

    Members are indexed by (war, tag) up front so the attack loop stays linear
    instead of issuing a query per attack.
    """
    from models import (ClanWar, ClanWarAttack, ClanWarMember,
                        CWLAttack, CWLMember, CWLWar)

    facts = []
    clan_tag_fallback = resolve_clan_tag()

    wars = {w.id: w for w in ClanWar.query.all()}
    wmem = {(m.clan_war_id, m.player_tag): m for m in ClanWarMember.query.all()}
    for a in ClanWarAttack.query.all():
        war = wars.get(a.clan_war_id)
        att = wmem.get((a.clan_war_id, a.attacker_tag))
        dfn = wmem.get((a.clan_war_id, a.defender_tag))
        if war and att and dfn:
            facts.append(war_fact(a, att, dfn, war, clan_tag_fallback))

    cwars = {w.id: w for w in CWLWar.query.all()}
    cmem = {(m.war_id, m.player_tag): m for m in CWLMember.query.all()}
    for a in CWLAttack.query.all():
        war = cwars.get(a.war_id)
        att = cmem.get((a.war_id, a.attacker_tag))
        dfn = cmem.get((a.war_id, a.defender_tag))
        if war and att and dfn:
            facts.append(cwl_fact(a, att, dfn, war))

    return facts

import json

from flask import Blueprint, render_template, request
from sqlalchemy.orm import selectinload

from models import RaidWeekend, RaidWeekendLog, Player
from services.helpers import (
    cleanup_threshold, RAID_DISTRICT_MEDALS, RAID_CAPITAL_PEAK_MEDALS,
    raid_district_medal_value, raid_score_verdict, _raid_level_mult, is_capital_peak,
)

raid_bp = Blueprint('raid', __name__)


@raid_bp.route('/raid')
def raid_weekend_page():
    all_raids = RaidWeekend.query.order_by(RaidWeekend.start_time.desc()).all()

    selected_id = request.args.get('raid_id', type=int)
    if not selected_id and all_raids:
        selected_id = all_raids[0].id

    selected_raid = next((r for r in all_raids if r.id == selected_id), None) if selected_id else None

    player_data = []
    total_log_attacks = 0
    cleanup_count = 0
    est_medals_6atk = None
    est_off_6atk = None
    est_avg_defensive = None
    regular_baseline = None
    peak_baseline = None
    combined_baseline = None
    roster_status = []
    clan_attacks_remaining = 0
    participated = 0
    roster_total = 0
    participation_pct = 0
    highlights = None

    if selected_raid:
        logs = (
            RaidWeekendLog.query
            .filter(RaidWeekendLog.raid_weekend_id == selected_raid.id)
            .options(selectinload(RaidWeekendLog.player))
            .order_by(RaidWeekendLog.id.asc())
            .all()
        )

        # ── Per-player medal impact ─────────────────────────────────────────────
        # Each fully-destroyed district's medal value is split across whoever
        # attacked it, in proportion to each attacker's own destruction % — two
        # players splitting a district 40/60 share its value 40/60, not both
        # claiming the full value. Impact is your own medals/attack rate minus
        # the bucket's average medals/attack rate — directly comparable to
        # "my total credit ÷ my attacks" without any further scaling. Computed
        # against final totals, so attack order and timing don't matter.
        #
        # Capital Peak attacks are NOT comparable to regular district attacks —
        # a peak is worth far more per attack than any regular district, so even
        # a badly-played peak attempt can outscore a great run on regular
        # districts if both are judged against the same average. Each bucket is
        # compared only against other attacks of the same kind.
        def _bucket_impact(bucket_logs, exclude_log_ids=frozenset()):
            # A district counts as cleared if it ever reached 100% — a fact about what actually
            # happened, independent of which specific attack (possibly excluded below) crossed
            # the line. Built from bucket_logs, not credited_logs: if only the completing attack
            # were excluded from this check, the WHOLE district's value would vanish, taking
            # every other (legitimate, non-excluded) attacker's share of it down too — punishing
            # teammates who did real work just because someone else's cleanup tap finished it.
            district_value = {}
            for log in bucket_logs:
                if (log.percentage_total or 0) >= 100:
                    key = (log.defender_tag, log.district_name)
                    district_value[key] = raid_district_medal_value(log.district_name, log.district_level)

            # Every attacker keeps their own share of whatever they destroyed, cleanup or not —
            # a cleanup tap still earned its medals. What it doesn't do is count as an "attack"
            # for averaging: it's excluded from the attacker's own denominator (so it's a pure
            # bonus, never a penalty for taking the unglamorous finishing tap), and it's excluded
            # from the raid-wide baseline's denominator too. The baseline's medal total also only
            # draws from non-cleanup attacks — so a cleanup tap can credit its own attacker without
            # ever inflating the average everyone else gets compared against.
            credit                  = {}
            attack_count            = {}
            player_baseline_medals  = {}
            player_baseline_attacks = {}
            baseline_medals  = 0.0
            baseline_attacks = 0
            for log in bucket_logs:
                key   = (log.defender_tag, log.district_name)
                value = district_value.get(key, 0)
                share = (log.percentage or 0) / 100.0 * value
                credit[log.player_tag] = credit.get(log.player_tag, 0) + share
                if log.id not in exclude_log_ids:
                    attack_count[log.player_tag] = attack_count.get(log.player_tag, 0) + 1
                    baseline_medals  += share
                    baseline_attacks += 1
                    player_baseline_medals[log.player_tag]  = player_baseline_medals.get(log.player_tag, 0) + share
                    player_baseline_attacks[log.player_tag] = player_baseline_attacks.get(log.player_tag, 0) + 1

            baseline = (baseline_medals / baseline_attacks) if baseline_attacks else 0.0

            rate           = {}
            impact         = {}
            baseline_shift = {}
            for player_tag, ac in attack_count.items():
                personal_rate = credit[player_tag] / ac
                rate[player_tag]   = round(personal_rate, 2)
                impact[player_tag] = round(personal_rate - baseline, 2)
                # Baseline Shift answers a different question than Impact: not "how does my
                # rate compare to average" but "how many medals/attack did MY OWN attacks pull
                # the shared average up or down by" — baseline-with-me minus baseline-without-me
                # (the latter computed leave-one-out: this player's own non-cleanup medals/
                # attacks removed from the bucket totals). A player can have a huge Impact
                # (their rate is far from average) while barely moving the baseline (their
                # attacks are a tiny fraction of a large pool), or the reverse — a middling
                # Impact but a large Baseline Shift if the bucket is thin and they're a big
                # chunk of it (this is common on the Capital Peak, which gets far fewer attacks
                # overall than regular districts). Falls back to 0 if this player IS the entire
                # bucket (no one else to compare to, so there's no "average without them").
                other_medals   = baseline_medals  - player_baseline_medals.get(player_tag, 0)
                other_attacks  = baseline_attacks - player_baseline_attacks.get(player_tag, 0)
                other_baseline = (other_medals / other_attacks) if other_attacks else baseline
                baseline_shift[player_tag] = round(baseline - other_baseline, 2)
            return {
                'baseline': round(baseline, 2), 'rate': rate, 'impact': impact,
                'baseline_shift': baseline_shift,
            }

        peak_logs    = [l for l in logs if is_capital_peak(l.district_name)]
        regular_logs = [l for l in logs if not is_capital_peak(l.district_name)]
        regular_bucket = _bucket_impact(regular_logs)
        peak_bucket    = _bucket_impact(peak_logs)

        net_medal_impact_by_player  = regular_bucket['impact']
        peak_medal_impact_by_player = peak_bucket['impact']
        # Only used internally to build the combined overall_baseline_shift below — not
        # surfaced per-bucket, just like overall_impact doesn't surface separate columns.
        net_medal_baseline_shift_by_player    = regular_bucket['baseline_shift']
        peak_medal_baseline_shift_by_player   = peak_bucket['baseline_shift']
        regular_rate_by_player      = regular_bucket['rate']
        peak_rate_by_player         = peak_bucket['rate']
        regular_baseline            = regular_bucket['baseline'] if regular_logs else None
        peak_baseline               = peak_bucket['baseline'] if peak_logs else None
        players_with_peak_attack    = {l.player_tag for l in peak_logs}
        players_with_regular_attack = {l.player_tag for l in regular_logs}

        # ── Overall impact (regular + peak, weighted by real value share) ───────
        # A Capital Peak is worth far more than its "1 of 9 structures" share would
        # suggest, so weighting regular vs peak by raw structure count understates
        # the peak's real importance. Instead, weight each bucket by its share of
        # the max medals actually achievable this raid (using each district's
        # observed level, since not every enemy is maxed) — only districts hit by
        # at least one attack are known, since untouched districts' levels aren't
        # captured by ingestion.
        observed_level = {}
        for log in logs:
            key = (log.defender_tag, log.district_name)
            if key not in observed_level:
                observed_level[key] = log.district_level

        medals_non_peak_max = sum(
            raid_district_medal_value(name, lvl)
            for (_, name), lvl in observed_level.items() if not is_capital_peak(name)
        )
        medals_peak_max = sum(
            raid_district_medal_value(name, lvl)
            for (_, name), lvl in observed_level.items() if is_capital_peak(name)
        )
        medals_weight_total = medals_non_peak_max + medals_peak_max
        weight_regular = (medals_non_peak_max / medals_weight_total) if medals_weight_total else 0.0
        weight_peak    = (medals_peak_max / medals_weight_total) if medals_weight_total else 0.0

        # Combined district value across both buckets, for the existing medal estimate below.
        district_value_all = {}
        for log in logs:
            if (log.percentage_total or 0) >= 100:
                key = (log.defender_tag, log.district_name)
                district_value_all[key] = raid_district_medal_value(log.district_name, log.district_level)
        total_medals_now = sum(district_value_all.values())

        player_map = {}
        for log in logs:
            tag = log.player_tag
            if tag not in player_map:
                player_map[tag] = {
                    'player_name': log.player.name if log.player else tag,
                    'player_tag': tag,
                    'in_clan': log.player.in_clan if log.player else None,
                    'att_count': 0,
                    'cleanup_count': 0,
                    'capital_loot': 0,
                    'solo_wipes': 0,
                    'attack_logs': [],
                }
            p = player_map[tag]
            p['att_count'] += 1
            if log.total_loot_all_attacks:
                p['capital_loot'] = log.total_loot_all_attacks
            level = log.district_level or 5
            try:
                level = int(level)
            except (TypeError, ValueError):
                level = 5
            level_mult = round(_raid_level_mult(level, is_capital_peak(log.district_name)), 2)
            pct = log.percentage or 0
            p['attack_logs'].append({
                'log_id':           log.id,
                'district_name':    log.district_name or '—',
                'district_level':   level,
                'level_mult':       level_mult,
                'stars':            log.stars or 0,
                'percentage':       pct,
                'adj_score':        0.0,
                'percentage_total': log.percentage_total or 0,
                'is_clean_up':      False,
                'defender_name':         log.defender_name or '—',
                'defender_tag':          log.defender_tag or '—',
                'defender_badge':        log.defender_badge or None,
                'defender_league':       log.defender_league or None,
                'defender_league_badge': log.defender_league_badge or None,
            })

        MAX_ATTACKS = 6
        for p in player_map.values():
            district_hits = {}
            for l in p['attack_logs']:
                key = (l['district_name'], l['defender_tag'])
                district_hits.setdefault(key, []).append(l)
            player_cleanup_log_ids = set()
            solo_wipe_count = 0
            for hits in district_hits.values():
                district_done = any(l['percentage_total'] == 100 for l in hits)
                player_total  = sum(l['percentage'] for l in hits)
                if len(hits) == 1 and district_done and hits[0]['percentage'] < cleanup_threshold(hits[0]['district_name']):
                    player_cleanup_log_ids.add(hits[0]['log_id'])
                if district_done and player_total == 100:
                    solo_wipe_count += 1
            for l in p['attack_logs']:
                l['is_clean_up'] = l['log_id'] in player_cleanup_log_ids
                l['adj_score']   = round(0.0 if l['is_clean_up'] else l['percentage'] * l['level_mult'], 2)

            p['cleanup_count']      = len(player_cleanup_log_ids)
            p['solo_wipes']         = solo_wipe_count
            p['medals_per_attack'] = (
                regular_rate_by_player.get(p['player_tag'])
                if p['player_tag'] in players_with_regular_attack else None
            )
            p['net_medal_impact'] = (
                net_medal_impact_by_player.get(p['player_tag'])
                if p['player_tag'] in players_with_regular_attack else None
            )
            p['peak_medals_per_attack'] = (
                peak_rate_by_player.get(p['player_tag'])
                if p['player_tag'] in players_with_peak_attack else None
            )
            p['peak_medal_impact'] = (
                peak_medal_impact_by_player.get(p['player_tag'])
                if p['player_tag'] in players_with_peak_attack else None
            )
            # Overall Impact is this player's weighted share of impact on the raid's whole
            # medal pool: a player who never attacked the Capital Peak had no chance to move
            # the ~28% of total value that lives there, so that share counts as 0 for them —
            # it isn't excluded/renormalized away, it caps their Overall Impact below someone
            # who covered both buckets, even if their regular-district performance was identical.
            overall_regular_impact = (
                net_medal_impact_by_player.get(p['player_tag'], 0)
                if p['player_tag'] in players_with_regular_attack else 0
            )
            overall_peak_impact = (
                peak_medal_impact_by_player.get(p['player_tag'], 0)
                if p['player_tag'] in players_with_peak_attack else 0
            )
            p['overall_impact'] = round(
                weight_regular * overall_regular_impact + weight_peak * overall_peak_impact, 2
            )
            overall_regular_baseline_shift = (
                net_medal_baseline_shift_by_player.get(p['player_tag'], 0)
                if p['player_tag'] in players_with_regular_attack else 0
            )
            overall_peak_baseline_shift = (
                peak_medal_baseline_shift_by_player.get(p['player_tag'], 0)
                if p['player_tag'] in players_with_peak_attack else 0
            )
            p['overall_baseline_shift'] = round(
                weight_regular * overall_regular_baseline_shift + weight_peak * overall_peak_baseline_shift, 2
            )
            overall_regular_rate = (
                regular_rate_by_player.get(p['player_tag'], 0)
                if p['player_tag'] in players_with_regular_attack else 0
            )
            overall_peak_rate = (
                peak_rate_by_player.get(p['player_tag'], 0)
                if p['player_tag'] in players_with_peak_attack else 0
            )
            p['overall_rate'] = round(
                weight_regular * overall_regular_rate + weight_peak * overall_peak_rate, 2
            )

            non_cleanup = [l['percentage'] for l in p['attack_logs'] if not l['is_clean_up']]
            p['avg_pct'] = round(sum(non_cleanup) / len(non_cleanup), 1) if non_cleanup else 0

            effective_max  = max(1, p['att_count'] - p['cleanup_count'])
            total_adj      = sum(l['adj_score'] for l in p['attack_logs'])
            adj_per_attack = total_adj / effective_max
            missing = max(0, MAX_ATTACKS - p['att_count'])
            missing_text = f" ({missing} missing)" if missing else ""
            score_100, adj_boosted, p['badge_class'], p['judge_label'] = raid_score_verdict(
                adj_per_attack, p['solo_wipes'], p['att_count'], missing_text
            )
            p['score_100']      = score_100
            p['adj_per_attack'] = adj_boosted
            p['effective_max']  = effective_max

        player_data = sorted(player_map.values(), key=lambda x: x['att_count'], reverse=True)
        total_log_attacks = sum(p['att_count'] for p in player_data)
        cleanup_count = sum(p['cleanup_count'] for p in player_data)

        # ── Roster reconciliation (war-room: who still has attacks) ──────────────
        # player_data is built purely from attack logs, so in-clan members who
        # haven't swung yet are absent from it. Reconcile against the current
        # in-clan roster so the mid-raid war-room can surface attacks-remaining and
        # no-shows. NOTE: in_clan reflects the roster NOW, not at raid time — so the
        # template only surfaces no-show *names* while the raid is ongoing (naming a
        # since-left member on an old ended raid would be wrong); ended raids use
        # only the aggregate participation count.
        att_by_tag = {p['player_tag']: p['att_count'] for p in player_data}
        clan_members = Player.query.filter_by(in_clan=True).order_by(Player.name).all()
        for m in clan_members:
            used = min(att_by_tag.get(m.tag, 0), MAX_ATTACKS)
            roster_status.append({
                'player_name':  m.name or m.tag,
                'player_tag':   m.tag,
                'attacks_used': used,
                'attacks_left': MAX_ATTACKS - used,
                'has_attacked': used > 0,
            })
        roster_total           = len(roster_status)
        participated           = sum(1 for r in roster_status if r['has_attacked'])
        clan_attacks_remaining = sum(r['attacks_left'] for r in roster_status)
        participation_pct      = round(participated / roster_total * 100) if roster_total else 0

        # ── Post-raid highlights (all client-visible data; template shows only when
        # the raid has ended). Each award renders only when it has a real winner. ──
        def _top(key, predicate):
            cands = [p for p in player_data if predicate(p) and p.get(key) is not None]
            return max(cands, key=lambda p: p[key]) if cands else None
        highlights = {
            'mvp':           max(player_data, key=lambda p: (p['score_100'], p['overall_impact'])) if player_data else None,
            'biggest_carry': _top('overall_baseline_shift', lambda p: (p.get('overall_baseline_shift') or 0) > 0),
            'cleanup_hero':  _top('cleanup_count',          lambda p: p['cleanup_count'] > 0),
            'peak_slayer':   _top('peak_medals_per_attack', lambda p: p.get('peak_medals_per_attack') is not None),
            'triple_wipers': [p['player_name'] for p in player_data if p['solo_wipes'] >= 3],
        }

        # ── Estimated raid medals ─────────────────────────────────────────────
        total_medals  = total_medals_now
        total_attacks = max(total_log_attacks, 1)

        # Average defensive reward from last 10 finished raids
        past_def = (
            RaidWeekend.query
            .filter(RaidWeekend.defensive_reward > 0)
            .order_by(RaidWeekend.start_time.desc())
            .limit(10)
            .with_entities(RaidWeekend.defensive_reward)
            .all()
        )
        avg_defensive = round(sum(r.defensive_reward for r in past_def) / len(past_def)) if past_def else 0

        if total_medals > 0:
            baseline = total_medals / total_attacks
            combined_baseline = round(baseline, 2)
            off_6atk = max(0, min(round(baseline * 6), 1620))
            est_medals_6atk = off_6atk + avg_defensive
            est_off_6atk = off_6atk
            est_avg_defensive = avg_defensive
            for p in player_data:
                p['est_medals'] = max(0, min(round(min(p['att_count'], 6) * baseline), 1620)) + avg_defensive
        elif selected_raid.offensive_reward and selected_raid.offensive_reward > 0:
            baseline = selected_raid.offensive_reward
            combined_baseline = round(baseline, 2)
            off_6atk = min(round(baseline * 6), 1620)
            est_medals_6atk = off_6atk + avg_defensive
            est_off_6atk = off_6atk
            est_avg_defensive = avg_defensive
            for p in player_data:
                p['est_medals'] = min(round(min(p['att_count'], 6) * baseline), 1620) + avg_defensive
        else:
            est_medals_6atk = None
            for p in player_data:
                p['est_medals'] = None

    has_ongoing = any(r.state == 'ongoing' for r in all_raids)
    last_weekend_assigned = False
    raid_options = []
    for r in all_raids:
        if r.state == 'ongoing':
            label = 'Current Weekend'
        elif has_ongoing and not last_weekend_assigned:
            label = 'Last Weekend'
            last_weekend_assigned = True
        else:
            start = r.start_time.strftime('%d.%m.%Y') if r.start_time else '?'
            end   = r.end_time.strftime('%d.%m.%Y') if r.end_time else '?'
            label = f"{start} – {end}"
        raid_options.append({'id': r.id, 'label': label})

    return render_template(
        'raid/raid_weekend.html',
        raid_options=raid_options,
        selected_raid=selected_raid,
        selected_id=selected_id,
        player_data=player_data,
        total_log_attacks=total_log_attacks,
        cleanup_count=cleanup_count,
        est_medals_6atk=est_medals_6atk,
        est_off_6atk=est_off_6atk,
        est_avg_defensive=est_avg_defensive,
        regular_baseline=regular_baseline,
        peak_baseline=peak_baseline,
        combined_baseline=combined_baseline,
        roster_status=roster_status,
        clan_attacks_remaining=clan_attacks_remaining,
        participated=participated,
        roster_total=roster_total,
        participation_pct=participation_pct,
        highlights=highlights,
        raid_medal_tables_json=json.dumps({
            'district': RAID_DISTRICT_MEDALS,
            'peak': RAID_CAPITAL_PEAK_MEDALS,
        }),
    )

"""HA1-US-DAILY-EXPLORE-REVIEW-1: DB-free reproductions against the pure contract.

    cd personal_apps && py -3.12 ../radar-design/artifacts/ha1/review/contract_repro.py

Imports only features.radar.analysis_contract (standard library plus the
rule-based market calendar). No app import, no database, no network, no
fixtures. Reviewer evidence only; it changes nothing in the candidate.
"""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4] / 'personal_apps'
sys.path.insert(0, str(ROOT))

from features.radar import analysis_contract as ac  # noqa: E402

D9 = dt.date(2026, 9, 9)


def bucket(day, slot, source='bluesky', count=1, status='ok', config='cfgA', when=None):
    return {'bucket_start': when or dt.datetime(2026, 9, day) + dt.timedelta(minutes=15 * slot),
            'source': source, 'mention_count': count, 'status': status,
            'source_config_version': config}


def close(day):
    return {'close_date': dt.date(2026, 9, day), 'close': 10, 'currency': 'USD',
            'source': 'massive_grouped', 'price_basis': 'close', 'adjustment_basis': 'split',
            'fetched_at': dt.datetime(2026, 9, day, 23), 'market': 'us', 'mic': 'XNYS',
            'is_shadow': 0}


out = {}

# 1. identity_excluded_slots counts source-bucket ROWS, not time slots.
rows = [bucket(9, s, source=src) for src in ('bluesky', 'fourchan', 'reddit:wsb')
        for s in range(96)]
day = ac.chatter_days(rows, D9, D9, dt.datetime(2026, 9, 9, 12))['days'][0]
out['1_identity_excluded_unit'] = {
    'quarter_hours_before_first_seen': 48, 'represented_sources': 3,
    'identity_excluded_slots': day['identity_excluded_slots'],
}

# 2. Unaligned rows are invalid but not part of the 96-slot partition, so the
#    per-source slot fields can sum past expected_slots.
rows = [bucket(9, s) for s in range(96)] + [
    bucket(9, 0, when=dt.datetime(2026, 9, 9, 0, 7)),
    bucket(9, 0, when=dt.datetime(2026, 9, 9, 0, 22))]
src = ac.chatter_days(rows, D9, D9, dt.datetime(2026, 1, 1))['days'][0]['sources'][0]
fields = ('ok_slots', 'truncated_slots', 'missing_slots', 'absent_slots', 'invalid_slots')
out['2_slot_partition'] = {**{k: src[k] for k in fields},
                           'expected_slots': src['expected_slots'],
                           'sum_of_slot_fields': sum(src[k] for k in fields),
                           'coverage': src['coverage']}

# 3. A weekend between Friday and Monday closes is state 'missing' in the
#    payload -- the dates the frontend priceRuns joins across.
price = ac.price_days([close(11), close(14)], {'market': 'us', 'mic': 'XNYS'},
                      dt.datetime(2026, 1, 1), dt.date(2026, 9, 11), dt.date(2026, 9, 14),
                      ac.calendar_for('XNYS'))
out['3_weekend_between_closes'] = {
    'days': [[d['date'], d['state'], d['calendar_hint']] for d in price['days']],
    'backend_regime_runs': ac.regime_runs(price['days']),
}

# 4. A source whose only rows precede first_seen is still represented, as an
#    unavailable source on the day.
rows = [bucket(9, s, source='stocktwits') for s in range(10)] + [bucket(9, s) for s in range(60, 96)]
day = ac.chatter_days(rows, D9, D9, dt.datetime(2026, 9, 9, 6))['days'][0]
out['4_pre_identity_only_source'] = [[s['source'], s['coverage'], s['absent_slots']]
                                     for s in day['sources']]
out['4_identity_excluded_slots'] = day['identity_excluded_slots']

print(json.dumps(out, indent=2))

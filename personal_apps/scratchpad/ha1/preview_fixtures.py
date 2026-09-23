"""Owned preview fixtures for verify_preview.py (PLAN C15/C16), on a gated HA1 target.

    py -3.12 scratchpad/ha1/preview_fixtures.py seed
    py -3.12 scratchpad/ha1/preview_fixtures.py cleanup

CORRECTION-1 (2026-09-15): new for REVIEW-1 R4; NOT executed.

seed: gate (before the app is imported), refuse if a manifest already exists
or RADAR_HA1_PLAIN_PASSWORD is missing/short, bind, generate run-unique
symbols and a non-admin username, refuse before any write if any of them
exists, seed one company per C16 data state over the last seven completed UTC
days, commit, then write the manifest of exact owned keys to
radar-design/artifacts/ha1/runtime/preview-fixtures.json. A failure while
seeding removes every recorded row and writes no manifest. No password is
written anywhere; the admin is the operator's existing local-only account.

cleanup: gate and bind; the manifest's target must equal the gated target;
delete exactly the recorded keys, verify none remain, remove the manifest.
Synthetic local acceptance data only.

CORRECTION-2 (2026-09-15, NOT executed): a `lines` case whose own 7-day
window has modeled trading days at both ends and a modeled closed date inside,
with a close on every trading day, so the preview can assert positive
adjacent-price connections AND a weekend break (U9); the expected runs are
computed by ha1_harness.adjacent_runs and written to the manifest. A failed
seed or cleanup writes runtime/preview-fixtures-report.json keeping both the
original failure and the cleanup outcome with the owned identities still
present (U7), and the process exits nonzero; a failed cleanup keeps the
manifest.
"""
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import ha1_harness as harness  # noqa: E402
import local_runtime  # noqa: E402

MANIFEST = local_runtime.RUNTIME_DIR / 'preview-fixtures.json'
REPORT = local_runtime.RUNTIME_DIR / 'preview-fixtures-report.json'

#: role letter -> case. Every case is one company the preview opens by link.
CASES = {
    'T': 'typical', 'O': 'one_close', 'N': 'no_data', 'P': 'partial', 'C': 'config',
    'R': 'overlap', 'I': 'identity', 'G': 'regime', 'V': 'invalid', 'X': 'excluded',
    'S': 'stale', 'E': 'ineligible', 'A': 'ambiguous', 'L': 'limit', 'K': 'lines',
}


def seed_cases(owned, session, fx, symbols, days):
    from features.radar.market_calendars import us

    cases = {}
    d = days

    def identity(case, **company):
        symbol = symbols[case]
        return symbol, fx.add_company(owned, session, symbol, **company)

    symbol, company = identity('typical')
    instrument = fx.add_instrument(owned, session, symbol)
    for day in (d[1], d[3], d[4]):
        fx.add_close(owned, session, symbol, day)
    for day in (d[1], d[2], d[4]):
        fx.add_buckets(owned, session, fx.bucket_rows(symbol, day, 'bluesky', count=2))
    fx.add_buckets(owned, session, fx.bucket_rows(symbol, d[3], 'bluesky', slots=range(40)))
    cases['typical'] = {'symbol': symbol, 'company_id': company, 'instrument_id': instrument}

    symbol, company = identity('one_close')
    instrument = fx.add_instrument(owned, session, symbol)
    fx.add_close(owned, session, symbol, next(day for day in d if us.is_trading_day(day)))
    cases['one_close'] = {'symbol': symbol, 'company_id': company, 'instrument_id': instrument}

    symbol, company = identity('no_data')
    cases['no_data'] = {'symbol': symbol, 'company_id': company,
                        'instrument_id': fx.add_instrument(owned, session, symbol)}

    symbol, company = identity('partial')
    instrument = fx.add_instrument(owned, session, symbol)
    fx.add_buckets(owned, session, fx.bucket_rows(symbol, d[2], 'bluesky', slots=range(3)))
    fx.add_buckets(owned, session, fx.bucket_rows(symbol, d[2], 'bluesky', slots=range(3, 5),
                                                  status='truncated'))
    fx.add_buckets(owned, session, fx.bucket_rows(symbol, d[2], 'bluesky', slots=range(5, 96),
                                                  status='missing', count=0))
    fx.add_buckets(owned, session, fx.bucket_rows(symbol, d[4], 'bluesky', count=0))
    fx.add_buckets(owned, session, fx.bucket_rows(symbol, d[5], 'bluesky', count=0, slots=range(95)))
    cases['partial'] = {'symbol': symbol, 'company_id': company, 'instrument_id': instrument}

    symbol, company = identity('config')
    instrument = fx.add_instrument(owned, session, symbol)
    fx.add_buckets(owned, session, fx.bucket_rows(symbol, d[1], 'bluesky', slots=range(48)))
    fx.add_buckets(owned, session, fx.bucket_rows(symbol, d[1], 'bluesky', slots=range(48, 96),
                                                  config='cfgB'))
    fx.add_buckets(owned, session, fx.bucket_rows(symbol, d[2], 'bluesky', config='cfgB'))
    fx.add_buckets(owned, session, fx.bucket_rows(symbol, d[3], 'bluesky', config=None))
    cases['config'] = {'symbol': symbol, 'company_id': company, 'instrument_id': instrument,
                       'transition_day': d[1].isoformat()}

    symbol, company = identity('overlap')
    instrument = fx.add_instrument(owned, session, symbol)
    fx.add_buckets(owned, session, fx.bucket_rows(symbol, d[3], 'reddit'))
    fx.add_buckets(owned, session, fx.bucket_rows(symbol, d[3], 'reddit:wallstreetbets', count=2))
    cases['overlap'] = {'symbol': symbol, 'company_id': company, 'instrument_id': instrument,
                        'day': d[3].isoformat()}

    boundary = dt.datetime.combine(d[3], dt.time(12))
    symbol, company = identity('identity', first_seen=boundary)
    instrument = fx.add_instrument(owned, session, symbol, mapped_at=boundary)
    for day in (d[1], d[2], d[4]):
        fx.add_close(owned, session, symbol, day)
    for day in (d[2], d[3], d[4]):
        fx.add_buckets(owned, session, fx.bucket_rows(symbol, day, 'bluesky'))
    fx.add_buckets(owned, session, fx.bucket_rows(symbol, d[1], 'stocktwits'))
    cases['identity'] = {'symbol': symbol, 'company_id': company, 'instrument_id': instrument}

    symbol, company = identity('regime')
    instrument = fx.add_instrument(owned, session, symbol)
    open_days = [day for day in d if us.is_trading_day(day)][:3]
    for day, source in zip(open_days, ('massive_grouped', 'finnhub', 'massive_grouped')):
        fx.add_close(owned, session, symbol, day, source=source)
    cases['regime'] = {'symbol': symbol, 'company_id': company, 'instrument_id': instrument}

    symbol, company = identity('invalid')
    instrument = fx.add_instrument(owned, session, symbol)
    fx.add_close(owned, session, symbol, d[1], source=None)
    closed = next(day for day in d if not us.is_trading_day(day))
    fx.add_close(owned, session, symbol, closed)
    cases['invalid'] = {'symbol': symbol, 'company_id': company, 'instrument_id': instrument,
                        'closed_day': closed.isoformat()}

    symbol, company = identity('excluded')
    instrument = fx.add_instrument(owned, session, symbol)
    fx.add_buckets(owned, session, fx.bucket_rows(symbol, d[2], 'bluesky'))
    fx.add_buckets(owned, session, [
        {'ticker': symbol, 'source': 'bluesky', 'mention_count': 1, 'status': 'ok',
         'source_config_version': 'cfgA',
         'bucket_start': dt.datetime.combine(d[2], dt.time(0, minute))} for minute in (7, 22)])
    cases['excluded'] = {'symbol': symbol, 'company_id': company, 'instrument_id': instrument}

    symbol, company = identity('stale')
    current = fx.add_instrument(owned, session, symbol)
    demoted = fx.add_instrument(owned, session, symbol, mic='XNGS', venue='Nasdaq', primary=False)
    cases['stale'] = {'symbol': symbol, 'company_id': company, 'instrument_id': current,
                      'stale_instrument_id': demoted}

    symbol, company = identity('ineligible')
    fx.add_instrument(owned, session, symbol, currency='EUR')
    cases['ineligible'] = {'symbol': symbol, 'company_id': company}

    symbol, company = identity('ambiguous')
    fx.add_instrument(owned, session, symbol)
    fx.add_instrument(owned, session, symbol, mic='XNGS', venue='Nasdaq')
    cases['ambiguous'] = {'symbol': symbol, 'company_id': company}

    symbol, company = identity('limit')
    instrument = fx.add_instrument(owned, session, symbol)
    for n in range(harness.MAX_SOURCES + 1):
        fx.add_buckets(owned, session, fx.bucket_rows(symbol, d[3], f'zqsrc{n:02d}', slots=range(1)))
    cases['limit'] = {'symbol': symbol, 'company_id': company, 'instrument_id': instrument}

    # U9: its own window, trading days at both ends and a closed date inside.
    window = harness.interior_break_window(d[-1], us.is_trading_day)
    if window is None:
        raise RuntimeError('no 7-day window with an interior modeled closed date; lines case not seeded')
    start, end = window
    line_days = [start + dt.timedelta(days=n) for n in range(7)]
    flags = [bool(us.is_trading_day(day)) for day in line_days]
    symbol, company = identity('lines')
    instrument = fx.add_instrument(owned, session, symbol)
    for index, (day, trading) in enumerate(zip(line_days, flags)):
        if trading:
            fx.add_close(owned, session, symbol, day, close=f'{10 + index}.25')
        fx.add_buckets(owned, session, fx.bucket_rows(symbol, day, 'bluesky', count=1 + index % 3))
    cases['lines'] = {'symbol': symbol, 'company_id': company, 'instrument_id': instrument,
                      'window': {'from': start.isoformat(), 'to': end.isoformat()},
                      'expected_runs': [run for run in harness.adjacent_runs(flags) if len(run) > 1],
                      'closed_indexes': [index for index, flag in enumerate(flags) if not flag]}
    return cases


def write_report(original, owned, command):
    report = harness.run_failure_report(original, owned)
    report.update({'command': command, 'written_at': dt.datetime.now(dt.timezone.utc).isoformat()})
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, default=str), encoding='utf-8')
    return report


def main():
    command = sys.argv[1:2]
    if command not in (['seed'], ['cleanup']):
        raise SystemExit(__doc__)
    host, port, database, target, registry = local_runtime.gate()
    password = os.environ.get('RADAR_HA1_PLAIN_PASSWORD') or ''
    if command == ['seed']:
        if MANIFEST.exists():
            raise SystemExit(f'{MANIFEST} exists: preview fixtures are already seeded; run cleanup first')
        if len(password) < 12:
            raise SystemExit('set RADAR_HA1_PLAIN_PASSWORD (12+ characters) for the owned non-admin account')
    elif not MANIFEST.exists():
        raise SystemExit(f'no {MANIFEST}; nothing to clean up')
    app = local_runtime.bind(host, port, database, target, registry)

    import ha1_fixtures as fx
    from extensions import db
    from features.radar import analysis_contract as contract

    owned = None
    try:
        with app.app_context():
            store = fx.SqlFixtureStore(db.session)
            if command == ['cleanup']:
                document = json.loads(MANIFEST.read_text(encoding='utf-8'))
                owned = harness.OwnedFixtures.from_manifest(store, document, target)
                owned.cleanup()  # raises CleanupIncomplete; the manifest is then kept
                MANIFEST.unlink()
                print(f'removed the owned preview fixtures recorded for {target}')
                return
            token = harness.run_token()
            symbols = {case: harness.owned_symbol(letter, token) for letter, case in CASES.items()}
            plain = harness.owned_username('plain', token)
            start, end = contract.default_range(dt.datetime.now(dt.timezone.utc))
            days = [start + dt.timedelta(days=n) for n in range((end - start).days + 1)]
            owned = harness.OwnedFixtures(store, symbols.values(), [plain])
            with owned:
                cases = seed_cases(owned, db.session, fx, symbols, days)
                fx.add_user(owned, db.session, plain, password)
                db.session.commit()
                manifest = owned.persist(target)
                manifest.update({
                    'window': {'from': start.isoformat(), 'to': end.isoformat()},
                    'cases': cases, 'plain_user': plain,
                    'seeded_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'synthetic': True,
                })
                MANIFEST.parent.mkdir(parents=True, exist_ok=True)
                MANIFEST.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
            print(f'seeded {len(cases)} owned preview cases on {target}; manifest {MANIFEST}')
    except Exception as exc:  # noqa: BLE001 -- reported with the cleanup outcome, then re-raised
        report = write_report(exc, owned, command[0])
        print(json.dumps(report, indent=2, default=str), file=sys.stderr)
        raise


if __name__ == '__main__':
    main()

# personal_apps/scripts/report_radar_market_data_shadow.py
"""The READ-ONLY activation-gate report (plan Task 11).

    cd personal_apps && python -m scripts.report_radar_market_data_shadow \
        --from 2026-09-02T05:30:00 --to 2026-09-02T21:00:00 \
        [--gate german|us-closes] [--identity-audit FILE] \
        [--us-close-audit FILE] [--json]

Read-only is ENFORCED, not promised: the entry point starts a READ ONLY
transaction and a before_cursor_execute guard rejects every mutating
statement. Exit 0 only when every gate GOVERNING THE SELECTED SWITCH
passes; exit 2 for incomplete evidence; exit 1 for a failed truth or
identity gate. Activation itself stays an operator action -- this script
never changes flags, mappings, or rows.
"""
import argparse
import dataclasses
import datetime as dt
import decimal
import hashlib
import json
import re
import sys

MIN_IDENTITY_AUDIT = 50
MIN_MAPPING_COVERAGE = 0.90
MIN_DISPLAY_COVERAGE = 0.95
MAX_P95_EVENT_AGE_SECONDS = 1800
MIN_TRANSPORT_SUCCESS = 0.99
MIN_HISTORY_COVERAGE = 0.95
MIN_GROUPED_AGREEMENT_DAYS = 3                  # [A1]
MIN_GROUPED_PROVIDER_ROWS = 5000                # [A1]
MIN_GROUPED_ACTIVE_COVERAGE = decimal.Decimal('0.95')   # [A1]
MIN_GROUPED_OVERLAP_ROWS = 100                  # [A1]
MAX_GROUPED_CLOSE_DELTA = decimal.Decimal('0.005')      # [A1] vs incumbent

_FORBIDDEN = re.compile(
    r'^\s*(?:/\*.*?\*/\s*|--[^\n]*\n\s*)*'
    r'(INSERT|UPDATE|DELETE|REPLACE|CREATE|ALTER|DROP|TRUNCATE|GRANT|CALL)\b',
    re.IGNORECASE | re.DOTALL)


class ReadOnlyViolation(RuntimeError):
    """A mutating statement reached a read-only report session."""


def install_statement_guard(engine):
    import sqlalchemy as sa

    @sa.event.listens_for(engine, 'before_cursor_execute')
    def _guard(conn, cursor, statement, parameters, context, executemany):
        if _FORBIDDEN.match(statement or ''):
            raise ReadOnlyViolation(
                f'read-only report refused: {statement[:80]!r}')


@dataclasses.dataclass(frozen=True)
class Gate:
    name: str
    passed: bool
    numerator: object
    denominator: object
    threshold: object
    detail: dict


@dataclasses.dataclass(frozen=True)
class ShadowReport:
    start: dt.datetime
    end: dt.datetime
    gates: tuple
    truth_violations: tuple
    incomplete: tuple
    grouped_informational: dict
    generation_sha256: str | None
    instrument_map_sha256: str | None
    german_truth_violations: tuple = ()
    grouped_truth_violations: tuple = ()
    german_incomplete: tuple = ()
    grouped_incomplete: tuple = ()
    us_close_report_sha256: str | None = None

    def gate(self, name):
        return next(gate for gate in self.gates if gate.name == name)


def _percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))
    return ordered[index]


def _active_generation():
    from models import RadarMappingGeneration
    return (RadarMappingGeneration.query
            .filter_by(market='de')
            .filter(RadarMappingGeneration.status.in_(('active', 'shadow')))
            .order_by(
                (RadarMappingGeneration.status == 'active').desc(),
                RadarMappingGeneration.id.desc())
            .first())


def _instrument_map_sha():
    from features.radar import market_data
    found, _ = market_data.grouped_instrument_map()
    rows = sorted(f'{symbol}|{identity.ticker}|{identity.mic}|'
                  f'{identity.currency}'
                  for symbol, identity in found.items())
    return hashlib.sha256('\n'.join(rows).encode('utf-8')).hexdigest()


def _german_gates(session, start, end, identity_audit):
    """Every gate of spec §12's German activation list, plus truth checks."""
    import sqlalchemy as sa
    from features.radar.instruments import MappingDecision
    from models import (RadarBucketSource, RadarMarketDataCycle, RadarQuote)

    gates = []
    truth = []
    incomplete = []

    generation = _active_generation()
    generation_sha = generation.payload_sha256 if generation else None
    decisions = []
    if generation is not None:
        decisions = [MappingDecision(**item) for item in
                     json.loads(generation.payload_json)['decisions']]
    mapped = {decision.ticker: decision for decision in decisions
              if decision.status == 'mapped'}

    # identity: the operator audit, exact generation hash, >=50 rows, all
    # correct. The script can never fill `correct` itself.
    identity_detail = {'supplied': identity_audit is not None}
    identity_pass = False
    if identity_audit is None:
        incomplete.append('identity audit not supplied')
    elif generation is None:
        incomplete.append('no mapping generation to audit')
    else:
        problems = []
        if identity_audit.get('generation_sha256') != generation_sha:
            problems.append('generation hash mismatch')
        rows = identity_audit.get('rows') or []
        if len({row.get('ticker') for row in rows}) < MIN_IDENTITY_AUDIT:
            problems.append('fewer than 50 unique audited tickers')
        wrong = [row.get('ticker') for row in rows
                 if row.get('correct') is not True]
        if wrong:
            problems.append(f'rows not confirmed correct: {wrong[:5]}')
            truth.append('identity audit reports wrong identities')
        identity_detail.update(problems=problems, rows=len(rows))
        identity_pass = not problems
    gates.append(Gate('identity', identity_pass,
                      len(identity_audit.get('rows', []))
                      if identity_audit else 0,
                      MIN_IDENTITY_AUDIT, MIN_IDENTITY_AUDIT,
                      identity_detail))

    # mapping: >=90% of the top-100 30-day tickers WITH a German listing per
    # the complete official references. The generation payload is the
    # reference-derived record: a ticker refused with 'no_german_candidate'
    # provably has no listing and leaves the denominator.
    top = [ticker for (ticker,) in session.query(RadarBucketSource.ticker)
           .filter(RadarBucketSource.bucket_start >= end - dt.timedelta(days=30))
           .group_by(RadarBucketSource.ticker)
           .order_by(sa.func.sum(RadarBucketSource.mention_count).desc())
           .limit(100).all()]
    by_ticker = {decision.ticker: decision for decision in decisions}
    with_listing = [ticker for ticker in top
                    if ticker in by_ticker and
                    (by_ticker[ticker].status == 'mapped' or
                     by_ticker[ticker].reason != 'no_german_candidate')]
    mapped_top = [ticker for ticker in with_listing
                  if by_ticker[ticker].status == 'mapped']
    unmapped_reasons = {
        ticker: by_ticker[ticker].reason for ticker in with_listing
        if by_ticker[ticker].status != 'mapped'}
    if generation is None or not top:
        incomplete.append('mapping denominator unavailable '
                          '(no generation or no 30-day tickers)')
        mapping_pass = False
        ratio = None
    else:
        ratio = len(mapped_top) / len(with_listing) if with_listing else None
        if ratio is None:
            incomplete.append('zero top-100 tickers with a German listing')
            mapping_pass = False
        else:
            mapping_pass = ratio >= MIN_MAPPING_COVERAGE
    gates.append(Gate('mapping', mapping_pass, len(mapped_top),
                      len(with_listing), MIN_MAPPING_COVERAGE,
                      {'ratio': ratio, 'refusals': unmapped_reasons}))

    # display coverage + freshness: shadow quotes inside open-session cycles.
    shadow_quotes = (session.query(RadarQuote)
                     .filter(RadarQuote.is_shadow.is_(True),
                             RadarQuote.source == 'deutsche_boerse_delayed',
                             RadarQuote.fetched_at >= start,
                             RadarQuote.fetched_at <= end).all())
    covered = {quote.ticker for quote in shadow_quotes
               if quote.price_basis in ('trade', 'midpoint')}
    display_denominator = len(mapped)
    display_ratio = (len(covered & set(mapped)) / display_denominator
                     if display_denominator else None)
    if display_ratio is None:
        incomplete.append('no mapped instruments for display coverage')
    gates.append(Gate(
        'display_coverage',
        display_ratio is not None and display_ratio >= MIN_DISPLAY_COVERAGE,
        len(covered & set(mapped)), display_denominator,
        MIN_DISPLAY_COVERAGE, {'ratio': display_ratio}))

    ages = [(quote.fetched_at - quote.quote_ts).total_seconds()
            for quote in shadow_quotes if quote.quote_ts is not None]
    p95 = _percentile(ages, 0.95)
    if p95 is None:
        incomplete.append('no shadow quotes with provider event time')
    gates.append(Gate(
        'freshness', p95 is not None and p95 <= MAX_P95_EVENT_AGE_SECONDS,
        p95, MAX_P95_EVENT_AGE_SECONDS, MAX_P95_EVENT_AGE_SECONDS,
        {'p50': _percentile(ages, 0.5), 'samples': len(ages)}))

    # transport: no_newer and duplicate are deterministic success; rejected
    # and transport_error are not.
    cycles = (session.query(RadarMarketDataCycle)
              .filter(RadarMarketDataCycle.scheduled_at >= start,
                      RadarMarketDataCycle.scheduled_at <= end).all())
    ok = [cycle for cycle in cycles
          if cycle.status in ('accepted', 'no_newer', 'duplicate')]
    transport_ratio = len(ok) / len(cycles) if cycles else None
    if transport_ratio is None:
        incomplete.append('no collection cycles in the window')
    gates.append(Gate(
        'transport',
        transport_ratio is not None and
        transport_ratio >= MIN_TRANSPORT_SUCCESS,
        len(ok), len(cycles), MIN_TRANSPORT_SUCCESS,
        {'ratio': transport_ratio,
         'failures': [cycle.error_code for cycle in cycles
                      if cycle.status in ('rejected', 'transport_error')]}))

    # history: a deterministic 20-instrument stratified sample of mapped
    # tickers; expected trading dates over one year from the German
    # calendar; verified closes of any stored provenance count.
    from features.radar import history as history_mod
    from features.radar.market_calendars import session_state
    sample = sorted(mapped)[:20]
    history_pass = False
    history_ratio = None
    if not sample:
        incomplete.append('no mapped instruments for the history audit')
    else:
        expected_days = []
        day = end.date() - dt.timedelta(days=365)
        while day <= end.date() - dt.timedelta(days=1):
            probe = dt.datetime.combine(day, dt.time(12),
                                        tzinfo=dt.timezone.utc)
            if session_state('de', probe, mic='XETR') != 'closed':
                expected_days.append(day)
            day += dt.timedelta(days=1)
        stored = history_mod.closes_for(sample, days=366, today=end.date(),
                                        market='de', mic='XETR')
        have = sum(
            1 for ticker in sample
            for day in expected_days
            if day in dict(stored.get(ticker, [])))
        want = len(sample) * len(expected_days)
        history_ratio = have / want if want else None
        history_pass = history_ratio is not None and \
            history_ratio >= MIN_HISTORY_COVERAGE
    gates.append(Gate('history', history_pass,
                      history_ratio, MIN_HISTORY_COVERAGE,
                      MIN_HISTORY_COVERAGE, {'sample': len(sample)}))

    # truth: venue hops, midpoint-as-trade, US-as-German. Any hit blocks
    # activation regardless of every percentage.
    by_ticker_mics = {}
    for quote in shadow_quotes:
        by_ticker_mics.setdefault(quote.ticker, set()).add(quote.mic)
    hoppers = [ticker for ticker, mics in by_ticker_mics.items()
               if len(mics) > 1]
    if hoppers:
        truth.append(f'venue hop inside the window: {hoppers[:5]}')
    dressed = [quote.ticker for quote in shadow_quotes
               if quote.price_basis == 'midpoint' and
               (quote.bid is None or quote.ask is None)]
    if dressed:
        truth.append(f'midpoint without its book: {dressed[:5]}')
    mislabelled = [quote.ticker for quote in shadow_quotes
                   if quote.market == 'de' and quote.currency != 'EUR']
    if mislabelled:
        truth.append(f'non-EUR rows labelled German: {mislabelled[:5]}')

    return gates, truth, incomplete, generation_sha


def _close_basis(row):
    """Normalize the one permitted migration-era NULL provenance."""
    if row.adjustment_basis == 'split':
        return 'split'
    if row.adjustment_basis is None and row.source in (None, 'legacy',
                                                       'twelvedata'):
        return 'split'
    return row.adjustment_basis or 'unknown'


def _grouped_gate(session, end, us_close_audit, instrument_map_sha):
    """[A1] The US grouped-close agreement gate; independent of Germany."""
    import sqlalchemy as sa
    from features.radar import market_data
    from features.radar.market_calendars import session_state
    from models import RadarDailyClose, RadarGroupedCloseDay

    incomplete = []
    truth = []

    expected = []
    day = end.date() - dt.timedelta(days=730)
    while day <= end.date() - dt.timedelta(days=1):
        probe = dt.datetime.combine(day, dt.time(16), tzinfo=dt.timezone.utc)
        if session_state('us', probe) != 'closed':
            expected.append(day)
        day += dt.timedelta(days=1)

    states = {state.close_date: state for state in
              session.query(RadarGroupedCloseDay)
              .filter_by(source='massive_grouped', is_shadow=True).all()}
    missing = [day for day in expected if day not in states or
               states[day].status != 'accepted']
    thin = [day for day in expected
            if day in states and states[day].status == 'accepted' and
            states[day].provider_rows < MIN_GROUPED_PROVIDER_ROWS]
    duplicate_days = [day for day in expected if day in states and
                      states[day].duplicate_conflicts]
    if missing:
        incomplete.append(
            f'{len(missing)} expected trading days lack accepted shadow '
            f'grouped state (backfill incomplete)')
    if thin:
        truth.append(f'accepted days below the provider-row floor: '
                     f'{[d.isoformat() for d in thin[:3]]}')
    if duplicate_days:
        truth.append('conflicting grouped duplicate symbols: %s' %
                     [d.isoformat() for d in duplicate_days[:5]])

    # Recompute date-aware active coverage from current identities and
    # persisted closes. The ingestion-time counters are diagnostic only.
    instrument_map, _ = market_data.grouped_instrument_map()
    base_symbols_by_day = market_data.grouped_active_symbols_by_day(
        expected, end, instrument_map, is_shadow=True)
    base_symbols = {
        day: {(identity.ticker, identity.mic): symbol
              for symbol, identity in symbols.items()}
        for day, symbols in base_symbols_by_day.items()
    }
    all_base_keys = set().union(*base_symbols.values()) if base_symbols else set()
    present_by_day = {day: set() for day in expected}
    if all_base_keys and expected:
        active_rows = (session.query(
            RadarDailyClose.close_date, RadarDailyClose.ticker,
            RadarDailyClose.mic)
            .filter(RadarDailyClose.source == 'massive_grouped',
                    RadarDailyClose.is_shadow.is_(True),
                    RadarDailyClose.market == 'us',
                    RadarDailyClose.close_date.in_(expected),
                    sa.tuple_(RadarDailyClose.ticker,
                              RadarDailyClose.mic).in_(
                                  list(all_base_keys))).all())
        for close_date, ticker, mic in active_rows:
            present_by_day[close_date].add((ticker, mic))

    observed_symbols_by_day = {
        day: {base_symbols[day][key] for key in present_by_day[day]
              if key in base_symbols[day]}
        for day in expected
    }
    active_symbols_by_day = market_data.grouped_active_symbols_by_day(
        expected, end, instrument_map, is_shadow=True,
        observed_symbols_by_day=observed_symbols_by_day)
    active_symbols = {
        day: {(identity.ticker, identity.mic): symbol
              for symbol, identity in symbols.items()}
        for day, symbols in active_symbols_by_day.items()
    }
    all_active_keys = set().union(*active_symbols.values()) if \
        active_symbols else set()

    coverage_gaps = []
    unmatched_universe = set()
    coverage_values = []
    if not all_active_keys:
        incomplete.append('zero active denominator for grouped coverage')
    else:
        for expected_day in expected:
            expected_symbols = active_symbols[expected_day]
            if not expected_symbols:
                coverage_gaps.append({
                    'date': expected_day.isoformat(), 'matched': 0,
                    'expected': 0, 'ratio': None,
                })
                continue
            present = present_by_day[expected_day] & set(expected_symbols)
            coverage = (decimal.Decimal(len(present)) /
                        decimal.Decimal(len(expected_symbols)))
            coverage_values.append(coverage)
            missing_keys = set(expected_symbols) - present
            unmatched_universe.update(expected_symbols[key]
                                      for key in missing_keys)
            if coverage < MIN_GROUPED_ACTIVE_COVERAGE:
                coverage_gaps.append({
                    'date': expected_day.isoformat(),
                    'matched': len(present),
                    'expected': len(expected_symbols),
                    'ratio': str(coverage),
                })
        if coverage_gaps:
            incomplete.append(
                f'{len(coverage_gaps)} expected trading days are below '
                'historically eligible grouped coverage')

    # Agreement over the most recent expected dates: recomputed from
    # persisted shadow rows against incumbent live closes.
    recent = [day for day in reversed(expected)][:MIN_GROUPED_AGREEMENT_DAYS]
    if len(recent) < MIN_GROUPED_AGREEMENT_DAYS:
        incomplete.append('too few expected dates for grouped agreement')
    agreement_days = []
    worst = decimal.Decimal(0)
    split_candidates = []
    basis_conflicts = []
    delta_failures = []
    for recent_day in recent:
        shadow_rows = {
            (row.ticker, row.mic): row for row in
            session.query(RadarDailyClose)
            .filter_by(close_date=recent_day, is_shadow=True,
                       source='massive_grouped', market='us').all()}
        live_rows = {
            (row.ticker, row.mic): row for row in
            session.query(RadarDailyClose)
            .filter(RadarDailyClose.close_date == recent_day,
                    RadarDailyClose.is_shadow.is_(False),
                    RadarDailyClose.market == 'us').all()}
        overlap = set(shadow_rows) & set(live_rows)
        if len(overlap) < MIN_GROUPED_OVERLAP_ROWS:
            incomplete.append(
                f'{recent_day.isoformat()}: only {len(overlap)} overlapping '
                f'rows (need {MIN_GROUPED_OVERLAP_ROWS})')
            continue
        deltas = []
        day_basis_conflict = False
        for key in overlap:
            shadow = shadow_rows[key]
            live = live_rows[key]
            if _close_basis(shadow) != 'split' or \
                    _close_basis(live) != 'split':
                day_basis_conflict = True
                basis_conflicts.append((key[0], recent_day.isoformat(),
                                        _close_basis(shadow),
                                        _close_basis(live)))
            if not live.close:
                continue
            delta = abs(shadow.close - live.close) / live.close
            deltas.append(delta)
            if delta > decimal.Decimal('0.25'):
                ratio = shadow.close / live.close
                if abs(ratio - round(ratio)) < decimal.Decimal('0.02'):
                    split_candidates.append((key[0],
                                             recent_day.isoformat()))
        day_worst = max(deltas) if deltas else decimal.Decimal(0)
        worst = max(worst, day_worst)
        if day_worst > MAX_GROUPED_CLOSE_DELTA:
            delta_failures.append((recent_day.isoformat(), str(day_worst)))
        if not day_basis_conflict and day_worst <= MAX_GROUPED_CLOSE_DELTA:
            agreement_days.append(recent_day)
    if split_candidates:
        truth.append(f'split-basis candidates: {split_candidates[:5]}')
    if basis_conflicts:
        truth.append(f'adjustment-basis conflicts: {basis_conflicts[:5]}')
    if delta_failures:
        incomplete.append(f'grouped close delta failures: {delta_failures[:5]}')

    accepted_count = sum(1 for day in expected if day in states and
                         states[day].status == 'accepted')
    measured_rows = (session.query(sa.func.count(RadarDailyClose.id))
                     .filter(RadarDailyClose.source == 'massive_grouped',
                             RadarDailyClose.is_shadow.is_(True),
                             RadarDailyClose.close_date.in_(expected))
                     .scalar() or 0) if expected else 0
    daily_growth = (decimal.Decimal(measured_rows) /
                    decimal.Decimal(accepted_count)
                    if accepted_count else None)
    projected_rows = (int(daily_growth * len(expected))
                      if daily_growth is not None else None)
    unmatched_provider_count = sum(
        states[day].unmatched_provider for day in expected if day in states)

    evidence = {
        'agreement_days': [d.isoformat() for d in agreement_days],
        'worst_delta': str(worst),
        'missing_days': len(missing),
        'thin_days': [d.isoformat() for d in thin],
        'duplicate_conflict_days': [d.isoformat() for d in duplicate_days],
        'split_candidates': split_candidates[:10],
        'basis_conflicts': basis_conflicts[:10],
        'active_coverage_min': (str(min(coverage_values))
                                if coverage_values else None),
        'active_coverage_gaps': coverage_gaps[:50],
        'unmatched_universe_symbols': sorted(unmatched_universe),
        'unmatched_provider_count': unmatched_provider_count,
        'storage': {
            'measured_shadow_rows': measured_rows,
            'measured_rows_per_accepted_day': (str(daily_growth)
                                               if daily_growth is not None
                                               else None),
            'projected_steady_state_rows': projected_rows,
        },
    }
    report_hash_payload = {
        'instrument_map_sha256': instrument_map_sha,
        'evidence': evidence,
        'truth_violations': truth,
        'incomplete': incomplete,
    }
    report_sha = hashlib.sha256(json.dumps(
        report_hash_payload, sort_keys=True, separators=(',', ':'),
        default=str).encode('utf-8')).hexdigest()

    audit_ok = False
    audit_problems = []
    if us_close_audit is None:
        incomplete.append('US-close operator audit not supplied')
    else:
        if us_close_audit.get('report_sha256') != report_sha:
            audit_problems.append('report hash mismatch')
        if us_close_audit.get('instrument_map_sha256') != instrument_map_sha:
            audit_problems.append('instrument map hash mismatch')
        if not us_close_audit.get('reviewer') or \
                not us_close_audit.get('reviewed_at'):
            audit_problems.append('review provenance missing')
        if us_close_audit.get('accept_unmatched_symbols') is not True or \
                us_close_audit.get('accept_storage_projection') is not True:
            audit_problems.append('operator acceptances missing')
        audit_ok = not audit_problems
        if audit_problems:
            truth.append(f'US-close operator audit failed: {audit_problems}')

    evidence['audit_problems'] = audit_problems
    evidence['report_sha256'] = report_sha
    passed = (not missing and not thin and not duplicate_days and
              not coverage_gaps and all_active_keys and
              not split_candidates and not basis_conflicts and
              not delta_failures and
              len(agreement_days) >= MIN_GROUPED_AGREEMENT_DAYS and
              audit_ok and not incomplete and not truth)
    gate = Gate('grouped_agreement', bool(passed), len(agreement_days),
                MIN_GROUPED_AGREEMENT_DAYS, MIN_GROUPED_AGREEMENT_DAYS,
                evidence)
    return gate, truth, incomplete, report_sha


def build_report(session, start, end, identity_audit=None,
                 us_close_audit=None):
    german_gates, truth, incomplete, generation_sha = _german_gates(
        session, start, end, identity_audit)
    instrument_map_sha = _instrument_map_sha()
    grouped_gate, grouped_truth, grouped_incomplete, report_sha = _grouped_gate(
        session, end, us_close_audit, instrument_map_sha)
    return ShadowReport(
        start=start, end=end,
        gates=tuple(german_gates) + (grouped_gate,),
        truth_violations=tuple(truth + grouped_truth),
        incomplete=tuple(incomplete + grouped_incomplete),
        grouped_informational=grouped_gate.detail,
        generation_sha256=generation_sha,
        instrument_map_sha256=instrument_map_sha,
        german_truth_violations=tuple(truth),
        grouped_truth_violations=tuple(grouped_truth),
        german_incomplete=tuple(incomplete),
        grouped_incomplete=tuple(grouped_incomplete),
        us_close_report_sha256=report_sha)


GERMAN_GATES = ('identity', 'mapping', 'display_coverage', 'freshness',
                'transport', 'history')


def exit_code(report, gate_selector):
    """0 green for the selected switch; 1 truth/identity failure; 2 incomplete."""
    if gate_selector == 'german':
        if report.german_truth_violations:
            return 1
        governing = [report.gate(name) for name in GERMAN_GATES]
        if report.german_incomplete:
            return 2
        if not report.gate('identity').passed:
            return 1
        return 0 if all(gate.passed for gate in governing) else 2
    if report.grouped_truth_violations:
        return 1
    if report.grouped_incomplete:
        return 2
    governing = [report.gate('grouped_agreement')]
    if not governing[0].passed:
        return 2
    return 0


def _serialize(report):
    return {
        'from': report.start.isoformat(),
        'to': report.end.isoformat(),
        'generation_sha256': report.generation_sha256,
        'instrument_map_sha256': report.instrument_map_sha256,
        'us_close_report_sha256': report.us_close_report_sha256,
        'gates': [dataclasses.asdict(gate) for gate in report.gates],
        'truth_violations': list(report.truth_violations),
        'incomplete': list(report.incomplete),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='READ ONLY market-data v2 activation-gate report.')
    parser.add_argument('--from', dest='start', required=True)
    parser.add_argument('--to', dest='end', required=True)
    parser.add_argument('--gate', choices=('german', 'us-closes'),
                        default='german')
    parser.add_argument('--identity-audit')
    parser.add_argument('--us-close-audit')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)

    from app import app
    from extensions import db
    import sqlalchemy as sa

    identity_audit = None
    if args.identity_audit:
        with open(args.identity_audit, encoding='utf-8') as handle:
            identity_audit = json.load(handle)
    us_close_audit = None
    if args.us_close_audit:
        with open(args.us_close_audit, encoding='utf-8') as handle:
            us_close_audit = json.load(handle)

    with app.app_context():
        install_statement_guard(db.engine)
        db.session.execute(sa.text('SET TRANSACTION READ ONLY'))
        report = build_report(
            db.session,
            dt.datetime.fromisoformat(args.start.replace('Z', '')),
            dt.datetime.fromisoformat(args.end.replace('Z', '')),
            identity_audit=identity_audit, us_close_audit=us_close_audit)
        payload = _serialize(report)
        encoded = json.dumps(payload, indent=None if args.json else 2,
                             sort_keys=True, default=str)
        print(encoded)
        print('report_sha256:',
              (report.us_close_report_sha256 if args.gate == 'us-closes'
               else hashlib.sha256(encoded.encode('utf-8')).hexdigest()),
              file=sys.stderr)
        return exit_code(report, args.gate)


if __name__ == '__main__':
    sys.exit(main())

# personal_apps/scripts/backfill_radar_market_history.py
"""Resumable market-data v2 history backfill (plan Task 8).

Three bounded modes, all defaulting to --dry-run:

    cd personal_apps && python -m scripts.backfill_radar_market_history \
        --market us --apply --limit 40
    ... --market de --apply
    ... --market us-universe --apply --resume-after 2026-06-30

``us``          Yahoo deep tail for the ACTIVE board union's US instruments
                that do not yet reach the 3Y floor -- the deep history
                beyond Massive's two-year window [A1][A2].
``de``          Yahoo ``.DE`` backfill for verified Xetra-identity German
                instruments (the §8.2 proxy input).
``us-universe`` The complete Massive grouped backfill, one request per US
                trading day, newest first, to the free tier's two-year
                depth. REFUSES to run under RADAR_US_CLOSE_SOURCE=legacy:
                the shadow/live lane comes from that flag alone.

Resume keys: instrument modes use ``TICKER:MIC`` and continue strictly
after it; the grouped mode's cursor is the DATE and it continues strictly
before it. ``--limit`` bounds ATTEMPTED items, not successful ones, so a
wall of failures cannot spin forever.
"""
import argparse
import datetime as dt
import sys


def _instrument_targets(mode, now):
    from features.radar import history, market_data
    from models import RadarInstrument

    if mode == 'us':
        active = set(market_data.active_price_tickers(now))
        rows = (RadarInstrument.query
                .filter(RadarInstrument.market == 'us',
                        RadarInstrument.is_primary.is_(True),
                        RadarInstrument.mapping_status == 'mapped',
                        RadarInstrument.ticker.in_(active))
                .order_by(RadarInstrument.ticker, RadarInstrument.mic).all()
                ) if active else []
        floor = int(history.HISTORY_DAYS * history.MIN_STORED_RATIO)
        stored = history.closes_for([row.ticker for row in rows],
                                    today=now.date())
        return [row for row in rows
                if len(stored.get(row.ticker, [])) < floor]

    rows = (RadarInstrument.query
            .filter(RadarInstrument.market == 'de',
                    RadarInstrument.mic == 'XETR',
                    RadarInstrument.mapping_status == 'mapped',
                    RadarInstrument.isin.isnot(None))
            .order_by(RadarInstrument.ticker, RadarInstrument.mic).all())
    return rows


def _run_instruments(args, now):
    from features.radar import history
    from features.radar.prices import yahoo

    targets = _instrument_targets(args.market, now)
    if args.resume_after:
        resume_ticker, _, resume_mic = args.resume_after.partition(':')
        targets = [row for row in targets
                   if (row.ticker, row.mic) > (resume_ticker, resume_mic)]
    if args.limit:
        targets = targets[:args.limit]

    if not args.apply:
        print(f'dry-run: {args.market} would attempt {len(targets)} '
              f'instruments')
        if targets:
            print(f'next resume key: {targets[0].ticker}:{targets[0].mic}')
        return 0

    provider = yahoo.YahooProvider(yahoo.YahooHttp())
    stored = 0
    attempted = 0
    last_key = None
    for row in targets:
        attempted += 1
        last_key = f'{row.ticker}:{row.mic}'
        symbol = row.provider_symbol
        if args.market == 'de':
            symbol = symbol if symbol.endswith('.DE') else f'{symbol}.DE'
        closes = provider.daily_closes(symbol, history.HISTORY_DAYS)
        if not closes:
            continue
        currency = 'EUR' if args.market == 'de' else row.currency
        history.record_closes(
            row.ticker, closes, now, market=row.market, mic=row.mic,
            currency=currency, source='yahoo_chart',
            adjustment_basis='split')
        stored += 1
    print(f'{args.market}: attempted={attempted} stored={stored} '
          f'last_key={last_key}')
    return 0


def _us_trading_days(newest, depth_days):
    from features.radar.market_calendars import session_state
    days = []
    day = newest
    floor = newest - dt.timedelta(days=depth_days)
    while day >= floor:
        probe = dt.datetime.combine(day, dt.time(16),
                                    tzinfo=dt.timezone.utc)
        if session_state('us', probe) != 'closed':
            days.append(day)
        day -= dt.timedelta(days=1)
    return days


def _run_universe(args, now):
    from features.radar import market_data
    from features.radar.prices import massive
    from models import RadarGroupedCloseDay
    import os

    mode = os.getenv('RADAR_US_CLOSE_SOURCE', 'legacy')
    if mode == 'legacy':
        print('refusing: us-universe needs RADAR_US_CLOSE_SOURCE=shadow or '
              'massive -- an ungated run under legacy would overwrite the '
              'incumbent live closes at higher priority and make the '
              'agreement gate compare massive against itself',
              file=sys.stderr)
        return 2

    days = _us_trading_days(now.date() - dt.timedelta(days=1), 730)
    if args.resume_after:
        resume_date = dt.date.fromisoformat(args.resume_after)
        days = [day for day in days if day < resume_date]
    is_shadow = mode == 'shadow'
    accepted = {
        state.close_date
        for state in RadarGroupedCloseDay.query.filter_by(
            source='massive_grouped', is_shadow=is_shadow,
            status='accepted')}
    days = [day for day in days if day not in accepted]
    if args.limit:
        days = days[:args.limit]

    if not args.apply:
        minutes = len(days) / 5
        print(f'dry-run: us-universe would attempt {len(days)} trading days '
              f'(~{minutes:.0f} minutes at 5 calls/minute)')
        if days:
            print(f'next resume key: {days[0].isoformat()}')
        return 0

    provider = massive.MassiveProvider(massive.MassiveHttp())
    counts = {'accepted': 0, 'failed': 0}
    for day in days:
        result = market_data.ingest_grouped_day(provider, day, now)
        if result.status == 'accepted':
            counts['accepted'] += 1
        else:
            counts['failed'] += 1
            print(f'{day}: {result.status}')
    print(f'us-universe: attempted={len(days)} accepted={counts["accepted"]} '
          f'failed={counts["failed"]}')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Resumable market-data v2 history backfill.')
    parser.add_argument('--market', required=True,
                        choices=('us', 'de', 'us-universe', 'all'))
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--resume-after', default=None)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--dry-run', action='store_true', default=True)
    action.add_argument('--apply', action='store_true', default=False)
    args = parser.parse_args(argv)

    from app import app
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    with app.app_context():
        if args.market == 'all':
            for market in ('us', 'de'):
                sub = argparse.Namespace(**{**vars(args), 'market': market})
                code = _run_instruments(sub, now)
                if code:
                    return code
            sub = argparse.Namespace(**{**vars(args),
                                        'market': 'us-universe'})
            return _run_universe(sub, now)
        if args.market == 'us-universe':
            return _run_universe(args, now)
        return _run_instruments(args, now)


if __name__ == '__main__':
    sys.exit(main())

"""The real Flask app, served with `build_payload` routed through the store.

NOTHING UNDER `personal_apps/` IS MODIFIED. The two module globals named
`build_payload` -- `routes.api.build_payload`, which `/radar/api/board` calls,
and `routes.views.build_payload`, which the page imported by value -- are
rebound in this process only. `git status` is unaffected.

A `pending` answer renders as an EMPTY board carrying `pending: true`. The
client change that would poll on it is explicitly outside this design's
authorization (Part I.7), so the browser measurement reports what the SERVER
delivers and calls a pending render `pending`, never a board.

    python serve_store_app.py --port 5001
"""
import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from env_check import bootstrap  # noqa: E402
bootstrap()

import reader                                          # noqa: E402
import store                                           # noqa: E402


def install(app):
    from extensions import db
    from features.radar import board as board_mod
    from features.radar import llm_sentiment, market_data, spend
    from features.radar.config import SOURCES, source_root
    from features.radar.market_calendars import session_state
    from features.radar.routes import api as api_mod
    from features.radar.routes import views as views_mod

    def pending_shell(query, now, envelope):
        """Enough payload for the island to render an empty board.

        The three ops blocks are real: the island reads `spend.today_usd`
        directly and a null there is a client crash, not an empty state.
        """
        mic = 'XGAT' if query.market == 'de' else None
        session = session_state(query.market,
                                now.replace(tzinfo=dt.timezone.utc), mic=mic)
        payload = {
            'generated_at': now.isoformat() + 'Z',
            'market': query.market,
            'display_timezone': 'Europe/Berlin',
            'market_venue': ('Tradegate-first Germany' if query.market == 'de'
                             else 'US markets'),
            'next_boundary_label': None, 'next_boundary_at': None,
            'sources': sorted({source_root(s) for s in query.sources}),
            'all_sources': list(SOURCES),
            'segments': list(query.segments),
            'session': session,
            'min_venues': query.min_venues,
            'sort': query.sort, 'dir': query.direction,
            'venue_counts': {'any': 0, 'multi': 0},
            'window_hours': query.window,
            'segment_counts': {}, 'excluded': {},
            'spend': spend.summary(),
            'sentiment_ops': llm_sentiment.ops_summary(),
            'market_data_ops': market_data.ops_summary(now),
            'triplet_hours': list(board_mod.TRIPLET_HOURS),
            'series_hours': board_mod.SERIES_HOURS,
            'lead_count': board_mod.LEAD_COUNT,
            'rows': [],
            'watching': [], 'watch_rows': [],
        }
        payload.update(envelope)
        payload['rows'] = []
        return payload

    def store_build_payload(args, now=None, user_id=None):
        now = now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
        payload = reader.read_payload(db.engine, args, now, user_id)
        if payload.get('pending') or payload.get('busy'):
            query = api_mod.parse_query(args, now=now)
            payload = pending_shell(query, now, payload)
        return payload

    api_mod.build_payload = store_build_payload
    views_mod.build_payload = store_build_payload
    return store_build_payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=5001)
    args = ap.parse_args()
    from app import app
    with app.app_context():
        from extensions import db
        store.create_table(db.engine)
    install(app)
    print('SERVING on %d with build_payload routed through the store'
          % args.port, flush=True)
    app.run(host='127.0.0.1', port=args.port, threaded=True,
            use_reloader=False)


if __name__ == '__main__':
    main()

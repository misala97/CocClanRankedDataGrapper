"""The board build is memoised for a minute per selection.

Viewer-invariant, like coverage.py's memo: every account sees identical rows,
so the same selection asked twice within the TTL is one build. Measured
2026-09-01: the build is ~0.6s of 24 queries and is the whole of the page's
server time now that the N+1s are gone.
"""
import datetime as dt

from app import app as flask_app
from features.radar.routes import api


NOW = dt.datetime(2026, 9, 1, 12, 0)


def counting_build(monkeypatch):
    calls = []

    def build(sources, now, **kwargs):
        calls.append((tuple(sources), now, tuple(sorted(kwargs.items()))))
        return api.board_mod.Board(
            generated_at=now, market=kwargs.get('market', 'us'),
            display_timezone='Europe/Berlin', market_venue='US markets',
            next_boundary_label='closes', next_boundary_at=now,
            sources=list(sources), segments=list(kwargs.get('segments', ())),
            session='regular', min_venues=kwargs.get('min_venues', 1),
            venue_counts={}, window_hours=kwargs.get('window_hours', 4),
            segment_counts={}, excluded={}, rows=[])

    monkeypatch.setattr(api.board_mod, 'build', build)
    monkeypatch.setattr(api.spend, 'summary', lambda: {})
    monkeypatch.setattr(api.llm_sentiment, 'ops_summary', lambda: {})
    monkeypatch.setattr(api.market_data, 'ops_summary', lambda now: {})
    return calls


def test_the_same_selection_within_a_minute_is_one_build(monkeypatch):
    calls = counting_build(monkeypatch)
    with flask_app.app_context():
        api.build_payload({'market': 'us'}, now=NOW)
        api.build_payload({'market': 'us'}, now=NOW + dt.timedelta(seconds=30))

    assert len(calls) == 1


def test_a_different_selection_is_its_own_build(monkeypatch):
    calls = counting_build(monkeypatch)
    with flask_app.app_context():
        api.build_payload({'market': 'us'}, now=NOW)
        api.build_payload({'market': 'us', 'window': '12'}, now=NOW)
        api.build_payload({'market': 'de'}, now=NOW)
        api.build_payload({'market': 'us', 'sources': 'bluesky'}, now=NOW)

    assert len(calls) == 4


def test_the_memo_expires(monkeypatch):
    calls = counting_build(monkeypatch)
    with flask_app.app_context():
        api.build_payload({'market': 'us'}, now=NOW)
        api.build_payload({'market': 'us'}, now=NOW + dt.timedelta(seconds=61))

    assert len(calls) == 2


def test_a_cached_board_keeps_its_own_build_time(monkeypatch):
    """`generated_at` is when the board was BUILT. A cached board saying it
    was built just now would make the head's freshness stamp a lie."""
    counting_build(monkeypatch)
    with flask_app.app_context():
        first = api.build_payload({'market': 'us'}, now=NOW)
        second = api.build_payload({'market': 'us'},
                                   now=NOW + dt.timedelta(seconds=30))

    assert second['generated_at'] == first['generated_at']

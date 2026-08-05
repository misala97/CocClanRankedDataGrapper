# -*- coding: utf-8 -*-
"""Unit tests for features.admin.insights - the assembly and its cache.

build_briefing, _data_version and load_attack_facts had zero tests before
this file, and the Study-A scoping bug (players_sae ranking rival players
against our own roster) lived in exactly that gap - nothing here would have
caught it happening again.

Every DB touch point is stubbed so the suite stays DB-free: _data_version's
four .query.count() calls, load_attack_facts, resolve_clan_tag,
load_correlation_inputs and Player.query. Everything between those points -
the five studies' pure functions - runs for real over small synthetic facts,
so this also exercises the actual assembly wiring, not a mock of it.
"""

import pytest

import features.admin.insights as insights
import models
from features.admin.insights import _data_version, build_briefing

_QUERY_MODELS = (models.Player, models.ClanWarAttack, models.CWLAttack,
                 models.RankedWeek, models.RaidWeekendLog)


@pytest.fixture(autouse=True)
def _reset_query_patches():
    """Model.query is a Flask-SQLAlchemy descriptor whose __get__ requires an
    app context - even reading it (as monkeypatch.setattr does, to save the
    old value for teardown) raises RuntimeError outside one. So .query is
    patched with plain setattr below, and this fixture removes the override
    afterward, letting the class fall back to the inherited descriptor."""
    yield
    for cls in _QUERY_MODELS:
        if 'query' in vars(cls):
            delattr(cls, 'query')


class _FakeCountQuery:
    """Stands in for Model.query when only .count() is called."""

    def __init__(self, n):
        self._n = n

    def count(self):
        return self._n


class _FakePlayer:
    def __init__(self, tag, name, in_clan):
        self.tag = tag
        self.name = name
        self.in_clan = in_clan


class _FakeAllQuery:
    """Stands in for Model.query when only .all() is called."""

    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


PLAYERS = [_FakePlayer('#A', 'Ann', True), _FakePlayer('#B', 'Bo', False)]


def _facts(n=25):
    """Enough attacks at one differential that build_curve's buckets aren't thin."""
    return [{'src': 'war', 'attacker_tag': '#A', 'attacker_th': 14,
             'defender_th': 14, 'stars': 3 if i % 2 else 1, 'destruction': 100.0,
             'clan_tag': '#US', 'war_id': i, 'ended_at': None,
             'attack_order': 1} for i in range(n)]


def _correlation_inputs():
    ranked_scores = {'#A': [60, 70, 80]}
    raid_scores   = {'#A': [50, 55, 60]}
    roster        = [{'tag': '#A', 'name': 'Ann', 'th': 14}]
    games         = {'#A': 9}
    attacks       = {'#A': 9}
    return ranked_scores, raid_scores, roster, games, attacks


def _patch_briefing(monkeypatch, version=('v1',), facts=None, calls=None):
    """Stubs every DB touch point build_briefing makes, and gives it a fresh
    cache so tests never see another test's cached entry."""
    monkeypatch.setattr(insights, '_CACHE', {})
    monkeypatch.setattr(insights, '_data_version', lambda: version)

    def fake_load_attack_facts():
        if calls is not None:
            calls['load_attack_facts'] = calls.get('load_attack_facts', 0) + 1
        return facts if facts is not None else _facts()

    monkeypatch.setattr(insights, 'load_attack_facts', fake_load_attack_facts)
    monkeypatch.setattr(insights, 'resolve_clan_tag', lambda: '#US')
    monkeypatch.setattr(insights, 'load_correlation_inputs', _correlation_inputs)
    models.Player.query = _FakeAllQuery(PLAYERS)


def _patch_counts(war=1, cwl=1, ranked=1, raid=1):
    models.ClanWarAttack.query = _FakeCountQuery(war)
    models.CWLAttack.query     = _FakeCountQuery(cwl)
    models.RankedWeek.query    = _FakeCountQuery(ranked)
    models.RaidWeekendLog.query = _FakeCountQuery(raid)


# ── _data_version ────────────────────────────────────────────────────────────

def test_data_version_is_unchanged_when_no_source_table_count_changes():
    _patch_counts(war=3, cwl=4, ranked=5, raid=6)
    assert _data_version() == _data_version()


def test_data_version_changes_when_a_source_table_count_changes():
    _patch_counts(war=3, cwl=4, ranked=5, raid=6)
    before = _data_version()

    models.CWLAttack.query = _FakeCountQuery(5)
    after = _data_version()

    assert before != after


# ── build_briefing / caching ────────────────────────────────────────────────

def test_build_briefing_returns_the_memoized_object_when_the_version_is_unchanged(monkeypatch):
    calls = {}
    _patch_briefing(monkeypatch, version=('v1',), calls=calls)

    first  = build_briefing()
    second = build_briefing()

    assert first is second
    assert calls['load_attack_facts'] == 1


def test_a_changed_version_key_busts_the_cache(monkeypatch):
    calls = {}
    _patch_briefing(monkeypatch, version=('v1',), calls=calls)
    first = build_briefing()

    _patch_briefing(monkeypatch, version=('v2',), calls=calls)
    second = build_briefing()

    assert first is not second
    assert calls['load_attack_facts'] == 2


def test_build_briefing_returns_every_key_the_route_passes_to_the_template(monkeypatch):
    _patch_briefing(monkeypatch)
    d = build_briefing()

    assert set(d) == {
        'curve', 'players_sae', 'benchmark', 'consistency_ranked',
        'consistency_raid', 'contrast_ranked', 'upgrade', 'correlation',
        'names', 'our_clan_tag',
    }
    assert d['our_clan_tag'] == '#US'
    assert d['names'] == {'#A': 'Ann', '#B': 'Bo'}

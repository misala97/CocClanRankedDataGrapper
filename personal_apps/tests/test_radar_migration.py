"""Behavioral guards for Radar migrations that must never touch the live DB."""
import importlib.util
from pathlib import Path

import pytest


def _load_source_width_migration():
    path = (Path(__file__).parents[1] / 'migrations' / 'versions' /
            '08316d3e4d77_widen_radar_source_columns.py')
    spec = importlib.util.spec_from_file_location('radar_source_width', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class _FakeBind:
    def __init__(self, lengths, events):
        self.lengths = lengths
        self.events = events

    def execute(self, statement):
        sql = str(statement)
        table = next(name for name in self.lengths if name in sql)
        self.events.append(('check', table))
        return _ScalarResult(self.lengths[table])


class _FakeOp:
    def __init__(self, lengths):
        self.events = []
        self.bind = _FakeBind(lengths, self.events)

    def get_bind(self):
        return self.bind

    def alter_column(self, table, column, **kwargs):
        self.events.append(('alter', table, column))

    def execute(self, statement):
        self.events.append(('execute', str(statement)))


@pytest.mark.parametrize('violating_table', [
    'radar_poll_state',
    'radar_bucket_sources',
])
def test_source_width_downgrade_aborts_before_ddl_for_either_violation(
        monkeypatch, violating_table):
    migration = _load_source_width_migration()
    lengths = {'radar_poll_state': 24, 'radar_bucket_sources': 24}
    lengths[violating_table] = 25
    fake_op = _FakeOp(lengths)
    monkeypatch.setattr(migration, 'op', fake_op)

    with pytest.raises(RuntimeError, match=violating_table):
        migration.downgrade()

    assert fake_op.events == [
        ('check', 'radar_poll_state'),
        ('check', 'radar_bucket_sources'),
    ]


def test_source_width_downgrade_checks_both_tables_before_ordered_ddl(
        monkeypatch):
    migration = _load_source_width_migration()
    fake_op = _FakeOp(
        {'radar_poll_state': 24, 'radar_bucket_sources': 22})
    monkeypatch.setattr(migration, 'op', fake_op)

    migration.downgrade()

    assert fake_op.events[:2] == [
        ('check', 'radar_poll_state'),
        ('check', 'radar_bucket_sources'),
    ]
    assert fake_op.events[2:] == [
        ('alter', 'radar_poll_state', 'source'),
        ('alter', 'radar_bucket_sources', 'source'),
        ('execute', "UPDATE radar_posts SET source = 'reddit' "
                    "WHERE source LIKE 'reddit:%'"),
        ('alter', 'radar_posts', 'source'),
    ]

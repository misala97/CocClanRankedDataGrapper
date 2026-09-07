"""How long the Bluesky drain is allowed to run.

Bluesky is a LIVE firehose: a minute not captured is gone, unlike Reddit's
archive which resumes from a cursor. Measured 2026-09-07, coverage fell
from 889 minutes of the day to 374 (out of 1440) between 09-04 and 09-07,
and Bluesky posts with it, 2,069/day -> 561/day. Nothing was deployed in
that window. The cause is arithmetic: the shared ingest cycle stretched to
roughly five minutes as the tables grew, while the drain budget stayed at
45 seconds, so each cycle could only replay a fraction of the backlog and
the cursor fell permanently behind.

The budget must therefore be a CONFIGURED value, tied to how far apart the
cycles actually are, not a literal buried in a default argument.
"""
from features.radar import config
from features.radar.sources import bluesky


def test_the_budget_is_configuration_not_a_buried_default():
    assert isinstance(config.BLUESKY_DRAIN_SECONDS, int)
    assert config.BLUESKY_DRAIN_SECONDS >= 45, 'never below the old default'


def test_the_budget_leaves_room_inside_the_cycle_it_rides():
    """The drain runs inside the shared cycle, so it must finish well
    before the next one is due or it starves every other source."""
    assert config.BLUESKY_DRAIN_SECONDS < config.CYCLE_SECONDS


def test_fetch_passes_the_configured_budget_to_the_drain():
    seen = {}

    def drain(cursor_us, budget_seconds):
        seen['budget'] = budget_seconds
        return []

    bluesky.fetch(__import__('datetime').datetime(2026, 9, 7), drain)
    assert seen['budget'] == config.BLUESKY_DRAIN_SECONDS


def test_an_explicit_budget_still_wins_for_tests_and_backfills():
    seen = {}

    def drain(cursor_us, budget_seconds):
        seen['budget'] = budget_seconds
        return []

    bluesky.fetch(__import__('datetime').datetime(2026, 9, 7), drain,
                  budget_seconds=5)
    assert seen['budget'] == 5

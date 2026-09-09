"""Keeping what two fixed board selections showed, quarter-hour by quarter-hour.

This is a bounded observation history and nothing larger. It records the rows
and coverage marks that the US and DE boards presented -- every configured
source, all segments, a 24-hour window, one venue, default ordering -- at the
moment the capture ran. It cannot answer what an unselected filter would have
shown, cannot resurrect a post whose retention has expired, and is not evidence
that an arbitrary historical strategy could have been replayed. Anything later
built on top of it has to respect that scope or capture more, prospectively.

Three boundaries are load-bearing.

A slot is written once. `slot_start` is unique in SQL, and only that conflict
is read as "already recorded": every other database error stays an error,
because swallowing an outage would turn it into a gap nobody notices.

A pair is the unit. Both boards are built before anything is stored, so a
capture that could build only one leaves no row at all -- half a pair would be
an observation of a selection nobody made.

`observed_at` is the instant the caller supplied, copied verbatim. It is
deliberately not the slot boundary and deliberately not the payload's own
`generated_at`: the board is memoised for a minute, so its stamp belongs to the
build it came from, and writing either of those here would file the observation
under a time it did not happen at.

What this function does NOT do is enforce that the instant is the wall clock.
`now` is an injected clock -- the tests need one, and determinism is the reason
the parameter exists. The guarantee that observations carry real time is a
property of the call path, not of this function: the only production caller is
`_scheduled_observations`, which passes `_utcnow()`, pinned by
`test_the_scheduled_job_captures_the_wall_clock`. There is no backfill entry
point and no user-supplied timestamp reaches here. Adding either would need a
provenance contract of its own, because a row would then no longer be
self-evidently something that was seen.

Account state never enters the archive. `build_payload`'s serializer also reads
spend and the operational summaries as a side effect of building any board;
those are live health rather than research evidence, and a watching list is
somebody's private mark. Both are stripped before storage.
"""
import datetime as dt
import logging
import os
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from extensions import db
from models import RadarBoardObservation

from .config import SOURCES, expand_sources
from .routes.api import build_payload

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
SLOT_MINUTES = 15
MARKETS = ('us', 'de')

# Explicit rather than inherited from the API's default, so the archive keeps
# comparing like with like if that default ever moves.
LIMIT = 50

# Read as a side effect of serializing any board, and none of it belongs in a
# research archive: the first two are the caller's own marks, the rest are
# operational health that the admin surface reads live.
EXCLUDED = frozenset({'watching', 'watch_rows', 'spend', 'sentiment_ops',
                      'market_data_ops'})

_TRUTHY = {'1', 'true', 'yes', 'on'}


def capture_enabled() -> bool:
    """Off until the migration has run and a staging pass has been watched."""
    return os.getenv('RADAR_OBSERVATION_CAPTURE_ENABLED', '').strip().lower() \
        in _TRUTHY


def producer_revision() -> str | None:
    """Which build produced an observation, supplied by configuration.

    Deliberately not `git rev-parse` per cycle: the ingest host runs from a
    deployed checkout and a subprocess every fifteen minutes to learn a
    constant is a strange way to spend a process. Unset stays NULL, which is
    the honest answer when the deployment did not say.
    """
    return (os.getenv('RADAR_PRODUCER_REVISION') or '').strip() or None


def _session():
    """A transaction of the recorder's own, bound to the shared engine."""
    return Session(bind=db.engine)


def _slot(now: dt.datetime) -> dt.datetime:
    return now.replace(minute=(now.minute // SLOT_MINUTES) * SLOT_MINUTES,
                       second=0, microsecond=0)


def _queries() -> dict[str, dict[str, str]]:
    """The fixed pair, spelled the way the API parses it. Stored with the
    answer so no later reader has to assume which selection produced it.

    `limit` is sent explicitly rather than left to the server's default. It
    decides how many rows the board holds, so an archive that did not record
    it would leave an analyst unable to see that the cap moved underneath a
    comparison.
    """
    return {market: {'market': market, 'sources': ','.join(SOURCES),
                     'segment': '', 'window': '24', 'venues': '1',
                     'limit': str(LIMIT)}
            for market in MARKETS}


def _selections() -> dict:
    """What was asked for, in both the vocabulary the API takes and the one it
    expands to.

    The roots alone are not enough to reconstruct the question later: `reddit`
    expands to whatever REDDIT_SUBS held at capture time, and that list
    changes. A row's own `sources` says which subs contributed, never which
    were searched, so the expansion is recorded here.
    """
    return {'queries': _queries(),
            'sources_expanded': sorted(expand_sources(SOURCES))}


def capture(now: dt.datetime, *, producer_revision: str | None = None) -> bool:
    """Record the pair for `now`'s quarter-hour.

    True when a new observation was stored, False when that slot already had
    one. Anything else raises, for the scheduled job to contain: a capture that
    failed is a gap, and a gap is the truth.
    """
    slot = _slot(now)
    selections = _selections()
    payloads = {
        # Top-level keys only, which is all the board payload puts them at.
        # A future account-scoped field nested inside a row would need its own
        # handling here rather than an entry in EXCLUDED.
        market: {key: value
                 for key, value in build_payload(query, now=now,
                                                 user_id=None).items()
                 if key not in EXCLUDED}
        for market, query in selections['queries'].items()
    }
    observation = RadarBoardObservation(
        id=str(uuid.uuid4()), slot_start=slot, observed_at=now,
        schema_version=SCHEMA_VERSION, producer_revision=producer_revision,
        selections_json=selections, payload_json=payloads)
    try:
        with _session() as session, session.begin():
            session.add(observation)
    except sa.exc.IntegrityError:
        # An IntegrityError is not automatically "already recorded". MariaDB
        # materialises a JSON column with its own json_valid CHECK, so a
        # payload this path could not serialise would arrive here too and be
        # logged as a benign duplicate while the slot silently stayed empty.
        # Ask what actually happened; only a slot that now exists is the
        # idempotent case. watch.py:add takes the same precaution.
        if not _slot_exists(slot):
            raise
        logger.info('radar observation slot %s was already recorded', slot)
        return False
    logger.info('radar observation stored for slot %s', slot)
    return True


def _slot_exists(slot: dt.datetime) -> bool:
    """Read in a session of its own -- the one that hit the conflict is dead."""
    with _session() as session:
        return session.query(
            sa.exists().where(RadarBoardObservation.slot_start == slot)
        ).scalar() is True


def latest_observed_at() -> dt.datetime | None:
    """How old the archive is. A database read and nothing else -- the admin
    surface asks this, and asking must never build a board or reach a
    provider."""
    return db.session.query(
        sa.func.max(RadarBoardObservation.observed_at)).scalar()

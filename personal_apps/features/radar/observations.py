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

`observed_at` is when the capture actually ran. It is deliberately not the slot
boundary and deliberately not the payload's own `generated_at`: the board is
memoised for a minute, so its stamp belongs to the build it came from. Writing
either of the other two here would manufacture a historical time.

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

from .config import SOURCES
from .routes.api import build_payload

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
SLOT_MINUTES = 15
MARKETS = ('us', 'de')

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
    answer so no later reader has to assume which selection produced it."""
    return {market: {'market': market, 'sources': ','.join(SOURCES),
                     'segment': '', 'window': '24', 'venues': '1'}
            for market in MARKETS}


def capture(now: dt.datetime, *, producer_revision: str | None = None) -> bool:
    """Record the pair for `now`'s quarter-hour.

    True when a new observation was stored, False when that slot already had
    one. Anything else raises, for the scheduled job to contain: a capture that
    failed is a gap, and a gap is the truth.
    """
    slot = _slot(now)
    queries = _queries()
    payloads = {
        market: {key: value
                 for key, value in build_payload(query, now=now,
                                                 user_id=None).items()
                 if key not in EXCLUDED}
        for market, query in queries.items()
    }
    observation = RadarBoardObservation(
        id=str(uuid.uuid4()), slot_start=slot, observed_at=now,
        schema_version=SCHEMA_VERSION, producer_revision=producer_revision,
        selections_json=queries, payload_json=payloads)
    try:
        with _session() as session, session.begin():
            session.add(observation)
    except sa.exc.IntegrityError:
        logger.info('radar observation slot %s was already recorded', slot)
        return False
    return True


def latest_observed_at() -> dt.datetime | None:
    """How old the archive is. A database read and nothing else -- the admin
    surface asks this, and asking must never build a board or reach a
    provider."""
    return db.session.query(
        sa.func.max(RadarBoardObservation.observed_at)).scalar()

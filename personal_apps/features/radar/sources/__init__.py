# personal_apps/features/radar/sources/__init__.py
"""The normalized shape every source produces.

Two sources exist in the design and one is implemented; nothing downstream may
assume which. status is per source per cycle and is what the rollup writes onto
buckets -- a source returning rows is not automatically `ok`, because hitting
the page cap makes it `truncated` (spec 4.1, 4.5).
"""
import dataclasses
import datetime as dt


@dataclasses.dataclass
class RawPost:
    source: str
    external_id: str
    channel: str
    author: str | None
    created_utc: dt.datetime
    title: str | None
    body: str
    score: int
    num_comments: int
    url: str
    native_tickers: list = dataclasses.field(default_factory=list)
    native_sentiment: str | None = None


@dataclasses.dataclass
class FetchResult:
    posts: list
    status: str                      # 'ok' | 'missing' | 'truncated'
    catchup_depth: int = 0
    # Earliest instant this fetch actually covers. Anything the caller asked
    # for before this was not delivered -- Jetstream clamps a too-old cursor
    # silently, and a caller that assumed otherwise would carry a hole it
    # believed was complete. None means the full requested range was covered.
    covered_since: object = None
    # Observed messages/hour per symbol, for the poll scheduler. Empty for
    # sources that are not polled per symbol.
    rates: dict = dataclasses.field(default_factory=dict)

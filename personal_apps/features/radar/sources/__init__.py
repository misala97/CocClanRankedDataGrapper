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
    # Status per emitted source name, where one fetch covers several. Reddit
    # reads a slice of subreddits and each is its own source; the rolled-up
    # `status` above is what the cycle reports, and this is what the rollup
    # stamps on each source's rows.
    #
    # THREE states, and the difference between the last two is the difference
    # between an absence and a zero:
    #
    #   None  -- this fetcher does not report per-source status at all, so
    #            `status` above applies to the single name it fetches under.
    #            Bluesky and 4chan.
    #   {...} -- these names were observed, with these verdicts.
    #   {}    -- explicitly NO source was observed. Reddit with nothing due
    #            did not read Reddit: there is no observation to record, so
    #            the rollup must write no row at all. Not an `ok` zero (a
    #            bucket child claiming coverage no fetch produced) and not a
    #            `missing` (which means we tried and failed).
    #
    # Consumers must therefore test `is not None`, never truthiness -- the
    # empty map and the absent map mean opposite things.
    per_source_status: dict | None = None

# Owner addendum — preload all supported US board windows

Date: 2026-09-17  
Status: binding immediately for `A-US-USD-ONLY-IMPLEMENT-1`

## Decision

Keep the backend producer's current total of eight proactively warmed boards, but allocate all eight to US-only Radar:

```text
1 US market × 2 segment selections × 4 windows = 8 warm boards
```

The segment selections remain:

- All: empty segment filter `''`
- Default Discover: `discover,mid,micro,unknown`

The warmed windows are every value accepted by the board API and exposed by the UI: 1 hour, 4 hours, 12 hours and 24 hours.

## Required implementation

`board_producer.py` must use:

```python
WARM_MARKETS = ('us',)
WARM_SEGMENTS = ('', DEFAULT_SEGMENT)
WARM_WINDOWS = (1, 4, 12, 24)
```

`warm_queries(now)` must return exactly eight unique US queries. No DE query may be generated, claimed or stored. Update producer/store/cache tests to prove:

```python
assert len(queries) == 8
assert {query.market for query in queries} == {'us'}
assert sorted(query.window for query in queries) == [1, 1, 4, 4, 12, 12, 24, 24]
```

Also prove both existing normalized segment selections are present; use `parse_query`'s actual normalized ordering rather than duplicating a parser in the test.

## Rationale and limits

The prior eight-board workload was four query shapes for each of two markets. Removing Germany frees four warm slots. Reassigning them to the 1h and 4h US windows keeps the same board count while making every user-selectable US time window eligible for an immediate warm read.

This does not add new windows, segments, jobs, polling frequency, database schema, market support or production authorization. Deployment still requires independent review and separate owner approval.


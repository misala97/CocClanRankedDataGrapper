
---

## CORRECTION — the single-flight is inert on the target as deployed

Checked on the target after `af3feb4` was written, read-only:

```
PID     NLWP  COMMAND
121328     2  gunicorn --workers 2 --bind 127.0.0.1:5001 app:app   (master)
121352     1  gunicorn --workers 2 --bind 127.0.0.1:5001 app:app   (worker)
121355     1  gunicorn --workers 2 --bind 127.0.0.1:5001 app:app   (worker)
```

`NLWP 1` on both workers, and there is no `gunicorn.conf.py` in the working
directory. They are **sync workers: single-threaded processes serving one
request at a time**. Two concurrent readers therefore land in two separate
PROCESSES, and the single-flight coalesces threads within one process. **It
cannot fire in production as the service is configured today.**

That invalidates the claim in `af3feb4`'s message that this is "the bigger
half" of the abort. It is not the bigger half; as deployed it is none of it.

### It also means the concurrency measurement over-stated the penalty

The `7.85s / 7.92s` pair was two THREADS in one process, so the roughly one
second of Python per build serialised on the GIL. Two processes on six vCPUs
do not serialise: each gets a core, and only the database work contends. The
concurrent pair in production is therefore **cheaper** than that number,
probably nearer 6-6.5s than 7.9s.

So concurrency is no longer established as *the* thing that crosses eight
seconds. What survives:

- a serial 24h build is ~5.4s on this fixture, and the target is ~25% faster
  on the one statement measurable on both, so call it ~4.5-5s there --
  **under the abort, without much room**
- the index removes ~0.9s of that, measured
- anything that adds ~3s tips it over, and the target has several candidates:
  3871 MB of radar data against a 2500 MB buffer pool, `radar_ingest` writing
  continuously, and coc_stats running three more gunicorn workers against the
  same MariaDB

Which of those it is cannot be settled from here, because the target has no
latency telemetry and running code on it is refused by the session's command
classifier.

### What the single-flight is still worth

It is correct code and it starts working the moment the service runs threaded
workers. That change is worth making for a reason that has nothing to do with
this patch: **with two sync workers, two five-second board builds occupy both
workers and block the whole of personal_apps**, not just Radar. `--threads 4`
on the unit would fix that and switch the single-flight on at the same time.

That is a target service-configuration change. It is not authorized by this
brief and has not been made.

Cross-process coalescing -- one board built once across both workers -- needs
shared state (a table, or a cache server) and is the same work as the warm- or
precomputed-board direction recommended above.

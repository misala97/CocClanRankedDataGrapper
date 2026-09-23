# Request-duration logging — a proposal, not a change

Codex's PERF1 ruling: *"Choose request-duration access logging first, not a
global slow-query-log change... approved for preparation/local verification,
not live activation."*

**Nothing here has been applied.** No unit file was edited, no service was
restarted, no log was enabled. The target was not contacted at all while this
was written.

## Why this and not the slow query log

PERF1 spent a session inferring what a request costs because the target records
nothing about request duration: nginx logs no `$request_time`, gunicorn runs
with no access log, the slow query log is OFF with `long_query_time` at 10 s,
and `performance_schema` is OFF. A slow query log answers *"which statement was
slow"*, which is the second question. The first is *"is the board request
actually slow in production, and when"* — and PERF2's whole design rests on an
answer nobody has. One line per request answers it.

It is also the cheaper change: an access-log format is a per-service argument
with a one-line reversal, where `long_query_time` is a server-global setting
affecting both applications on that MariaDB.

## The format

```
%(t)s %(m)s %(U)s %(s)s %(B)s %(L)s
```

| Atom | What it is | Why it is here |
| --- | --- | --- |
| `%(t)s` | request date | when |
| `%(m)s` | method | separates the watch `PUT`/`DELETE` from reads |
| `%(U)s` | **path, no query string** | which endpoint |
| `%(s)s` | status | tells a 200 from the login redirect |
| `%(B)s` | response bytes | payload size, which the board's own design is about |
| `%(L)s` | **elapsed seconds, decimal** | the number this exists for |

### Verified: it really does omit what it claims to

Run locally against **gunicorn 26.2.0's own `Logger.atoms`**, with a request
carrying a query string, a session cookie, an `Authorization` header, an
`X-Forwarded-For` and a referer:

```
FORMAT : %(t)s %(m)s %(U)s %(s)s %(B)s %(L)s
LINE   : [10/Sep/2026:17:52:59 +0200] GET /radar/api/board 200 148213 4.512000
```

The atoms that exist in that same request and are **not** referenced by the
format, listed so the omission is a demonstrated fact rather than a claim:

```
'h'                       = '203.0.113.44'
'q'                       = 'sources=bluesky,fourchan,reddit&window=24&segment=&market=us&t=GME'
'r'                       = 'GET /radar/api/board?sources=...&t=GME'
'{cookie}i'               = 'session=eyJfZnJlc2giOnRydWV9.aBcDeF.SECRETSESSIONVALUE'
'{authorization}i'        = 'Bearer supersecrettoken'
'{http_x_forwarded_for}e' = '198.51.100.7'
'{referer}i'              = 'https://mgemmel.viewdns.net/radar/?t=GME'
'{user-agent}i'           = 'Mozilla/5.0 (Windows NT 10.0)'
'{raw_uri}e'              = '/radar/api/board?sources=...&t=GME'
'{query_string}e'         = 'sources=...&t=GME'
```

Three of those matter specifically:

- **`%(r)s` must not be used.** It is the request line *with* the query string,
  which is the obvious-looking choice and the wrong one.
- **`?t=GME` is in the query string**, and it is which company a signed-in
  person looked at. `%(U)s` excludes it.
- **`%(h)s` is the client IP** and personal_apps is multi-user in production.
  It is excluded. Losing it costs nothing here: the question is how long a
  request took, not who made it.

**How the verification was run, stated plainly.** `gunicorn.util` imports
`fcntl`, `pwd` and `grp` at module scope, none of which exist on Windows, so
gunicorn cannot run on this machine. The probe injects three stub modules into
`sys.modules` and then calls gunicorn's **real** `Logger.atoms` and its real
`SafeAtoms` formatting — `atoms()` is pure string work and touches none of the
stubbed functions. The line above is gunicorn's own output, not a
reimplementation. Script: `radar-design/perf2-spike/telemetry_format_probe.py`.

**Version caveat:** 26.2.0 is what is installed here. The target's gunicorn
version was not read. Atom names have been stable for many major versions, but
the format should be echoed back from the running service once before it is
trusted.

## Volume

Measured, not estimated: the formatter's own output for eight representative
paths averages **70.5 bytes per line** including the newline.

| Requests/day | Log/day | 14 days retained |
| --- | --- | --- |
| 1,000 | 0.07 MB | 0.94 MB |
| 5,000 | 0.34 MB | 4.71 MB |
| 20,000 | 1.34 MB | 18.83 MB |
| 100,000 | 6.72 MB | 94.13 MB |

**The real requests-per-day figure was not read**, and this is the honest gap
in this section. `ssh` to the target is refused by this session's command
classifier, so nginx's existing access log — which already records every
request and only lacks the timing — could not be counted. One `wc -l` on a
rotated day answers it exactly, and should be run before this is enabled.

What can be said about the shape without the count:

- **Every static asset is a gunicorn request.** nginx on this box proxies all
  routes including `/static`, so a page load is one HTML line plus one line per
  bundle, stylesheet and font — not one line.
- **A hub tab left open costs 2 requests per minute** while it is visible:
  `hub/queries.ts` sets `refetchInterval: visible ? REFRESH_MS : false` with
  `REFRESH_MS = 60_000`, on activity and ops. That is 2,880 lines a day per
  open tab, and it is the largest steady contributor.
- **The board does not poll.** `ListPane.tsx`'s 60-second `setInterval` ticks a
  render counter for relative timestamps; it issues no request. Board requests
  are one per filter change.

Even the 100,000/day row is under 7 MB a day, which is not a capacity question
on this box. The volume section exists to prove that, not to gate the change.

## The delta

Add two arguments to the web service's gunicorn invocation:

```
--access-logfile /var/log/personal_apps/access.log
--access-logformat "%(t)s %(m)s %(U)s %(s)s %(B)s %(L)s"
```

**The unit file was not read in this session.** The invocation is known only
from the target's process listing recorded in PERF1's ledger:

```
gunicorn --workers 2 --bind 127.0.0.1:5001 app:app
```

so this delta must be reconciled against the real `personal_apps_web.service`
before anyone applies it, including whether `/var/log/personal_apps/` exists
and what user the service runs as. Writing a log file the service user cannot
create is the way this fails on first restart.

`--access-logfile -` (stdout, captured by journald) is the alternative that
needs no directory, no permissions and no logrotate stanza at all, at the cost
of living under journald's own retention. **It is the smaller change and is
probably the right one for a first look**; the file form is written out here
because Codex asked for rotation and retention.

### Rotation and retention, if the file form is used

```
/var/log/personal_apps/access.log {
    daily
    rotate 14
    missingok
    notifempty
    compress
    delaycompress
    copytruncate
}
```

`copytruncate` rather than `create` plus a signal: gunicorn reopens its access
log on `USR1`, and a rotation stanza that gets that wrong silently keeps
writing to the rotated inode until the next restart. `copytruncate` loses at
most the handful of lines written during the copy, which is the cheaper failure
for a diagnostic log.

**The box's existing logrotate conventions were not read** and this stanza does
not claim to match them. Reconcile before use.

### Rollback

Remove the two arguments, `systemctl daemon-reload`, restart the service. The
log stops. Nothing else changes and no data is lost, because nothing else reads
this file. If the file form was used, delete `/var/log/personal_apps/` and the
logrotate stanza.

The change is reversible in the strong sense: the service's behaviour with the
arguments removed is byte-identical to today's.

## What this is not

- **Not activated.** Activation is a target configuration change and a service
  restart. Nobody has authorized either.
- **Not a slow-query investigation.** If request timing shows the board slow on
  the target and leaves an unresolved database question, a *targeted* slow-query
  look follows — per session, not a global `long_query_time` change.
- **Not a substitute for PERF2.** The board build is measured at around 4.5 s
  locally; this log would tell us what it is on the target, which nobody knows.
  That is worth knowing whether or not the shared store ships.

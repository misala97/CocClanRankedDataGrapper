"""Pure aggregation for the background-task Monitor page (/admin/monitor).

Every function here takes UptimeTracker rows (or plain objects shaped like
them) and returns plain dicts. No Flask, no DB session, no template concerns —
so the whole module is verifiable from synthetic fixtures.

The load-bearing piece is `correlate_incidents`. A single upstream outage fails
every task that happens to be due while it lasts, and reporting that as N
separate per-task error counts destroys the one fact worth knowing. On
2026-07-31 the Clash API was down for 35 minutes and produced 31 failures
across three tasks; the page this module feeds has to say that, not print
"12 / 12 / 7" in three boxes.
"""

import datetime as dt
from collections import Counter, defaultdict

# ── Task registry ─────────────────────────────────────────────────────────────
# Order is fixed and meaningful: the page shows all six every time, in the same
# places, so a missing one reads as missing rather than as a shorter list.
TASKS = [
    ('task_update_battle_logs',  'Battle Logs',  'Ranked-Kampfprotokolle'),
    ('task_update_ranked_weeks', 'Ranked Weeks', 'Wochenwertung + Ligen'),
    ('task_update_clan_members', 'Clan Members', 'Roster + Spielerprofile'),
    ('task_update_raid_weekend', 'Raid Weekend', 'Hauptstadt-Raids'),
    ('task_update_clan_war',     'Clan War',     'Kriegsstand + Angriffe'),
    ('task_update_cwl',          'CWL',          'Liga-Saison'),
]
TASK_META = {k: {'key': k, 'short': k.replace('task_update_', ''),
                 'label': lbl, 'purpose': p} for k, lbl, p in TASKS}

# ── Tunable thresholds ────────────────────────────────────────────────────────
CADENCE_SAMPLE   = 20    # recent successful runs used to infer the current cadence
DOWN_FACTOR      = 2.5   # silence beyond cadence × this reads as "down"
WARN_FACTOR      = 1.5   # …and beyond cadence × this as "delayed"
GAP_FACTOR       = 2.5   # a run-to-run interval beyond cadence × this is a gap
NO_CADENCE_WARN  = 120   # minutes of silence that warn when cadence is unknowable
NO_CADENCE_DOWN  = 1440  # …and beyond a day of it, call the task down, not delayed

CLUSTER_GAP_MIN  = 20    # failures within this many minutes belong to one incident
LANE_POINTS      = 240   # downsample target per task for the shared lane strip

VALID_DAYS       = (1, 7, 14, 30)
DEFAULT_DAYS     = 7


def _duration(raw):
    try:
        return float(raw) if raw else 0.0
    except (ValueError, TypeError):
        return 0.0


def cause_label(message):
    """Collapse an API error blob into something a human can scan.

    The raw message stays available alongside; this is the scannable key that
    lets the same failure be counted once across tasks.
    """
    m = message or ''
    if '503' in m and 'inMaintenance' in m:
        return 'API in Wartung (503)'
    if '500' in m and 'unknownException' in m:
        return 'API-Ausnahme (500)'
    if '503' in m:
        return 'API nicht verfügbar (503)'
    if '429' in m:
        return 'Ratenlimit erreicht (429)'
    if 'season' in m.lower():
        return 'Saison-Key fehlt'
    if 'timeout' in m.lower() or 'timed out' in m.lower():
        return 'Zeitüberschreitung'
    return (m[:48] + '…') if len(m) > 49 else (m or 'Unbekannter Fehler')


def normalize_runs(rows):
    """UptimeTracker rows → plain per-task run dicts, oldest first."""
    by_task = defaultdict(list)
    for r in rows:
        by_task[r.function].append({
            'time':    r.time,
            'duration': _duration(r.duration),
            'status':  r.status or 'success',
            'summary': r.summary or '',
            'error':   r.error_message or '',
        })
    for runs in by_task.values():
        runs.sort(key=lambda x: x['time'])
    return by_task


def infer_cadence(runs):
    """Median interval between recent non-skipped runs, in minutes.

    Only the most recent CADENCE_SAMPLE runs count: clan_war switches between a
    3-minute and a 60-minute schedule, and averaging across both modes would
    describe neither.
    """
    active = [r for r in runs if r['status'] != 'skipped']
    recent = active[-CADENCE_SAMPLE:]
    gaps = [(recent[i]['time'] - recent[i - 1]['time']).total_seconds() / 60
            for i in range(1, len(recent))]
    if not gaps:
        return None
    return round(sorted(gaps)[len(gaps) // 2], 1)


def find_gaps(runs, cadence, now=None):
    """Intervals far enough beyond the cadence to count as silence.

    `now` matters: measuring only run-to-run intervals misses the most important
    silence there is — the one that hasn't ended. A task that simply stopped
    produced no gap at all, so its lane went blank with nothing marking it, and
    blank is also what "outside the window" looks like.
    """
    if not cadence:
        return []
    active = [r for r in runs if r['status'] != 'skipped']
    out = []
    for i in range(1, len(active)):
        minutes = (active[i]['time'] - active[i - 1]['time']).total_seconds() / 60
        if minutes > cadence * GAP_FACTOR:
            out.append({
                'start':   active[i - 1]['time'],
                'end':     active[i]['time'],
                'minutes': round(minutes, 1),
                'ongoing': False,
            })
    if now is not None and active:
        trailing = (now - active[-1]['time']).total_seconds() / 60
        if trailing > cadence * GAP_FACTOR:
            out.append({
                'start':   active[-1]['time'],
                'end':     now,
                'minutes': round(trailing, 1),
                'ongoing': True,
            })
    return out


def group_errors(runs):
    """Failures grouped by message: count, first and last occurrence.

    The route previously exposed only the last run's error_message, so a task
    with 12 failures showed one string and no way to tell whether it was one
    cause twelve times or twelve different problems.
    """
    errs = [r for r in runs if r['status'] == 'error']
    by_msg = defaultdict(list)
    for r in errs:
        by_msg[r['error']].append(r['time'])
    groups = []
    for msg, times in by_msg.items():
        times.sort()
        groups.append({
            'message': msg,
            'label':   cause_label(msg),
            'count':   len(times),
            'first':   times[0],
            'last':    times[-1],
        })
    groups.sort(key=lambda g: (-g['count'], g['first']))
    return groups


def downsample(runs, target=LANE_POINTS):
    """Evenly thin a run series for the lane strip.

    The route used to hand the template every row — roughly 45k at 30 days —
    purely so the client could draw charts from them.
    """
    if not runs:
        return []
    # Round the step UP: flooring it lets the result overshoot the target
    # (5000 // 240 = 20 → 250 points), so the "bound" wouldn't bound anything.
    step = max(1, -(-len(runs) // target))
    return [{'t': r['time'], 'd': round(r['duration'], 2), 's': r['status']}
            for r in runs[::step]]


def task_stats(key, runs, now):
    """Everything the register row and the per-task disclosure need."""
    meta = TASK_META.get(key, {'key': key, 'short': key,
                               'label': key, 'purpose': ''})
    active = [r for r in runs if r['status'] != 'skipped']
    durations = [r['duration'] for r in active]
    cadence = infer_cadence(runs)

    last = runs[-1] if runs else None
    minutes_since, health = None, 'absent'
    if last:
        minutes_since = round((now - last['time']).total_seconds() / 60, 1)
        # A recent skip still proves the task is alive — raid_weekend skips on
        # weekdays by design — so recency uses the last run of any status.
        if cadence:
            if minutes_since > cadence * DOWN_FACTOR:
                health = 'down'
            elif minutes_since > cadence * WARN_FACTOR:
                health = 'warn'
            else:
                health = 'up'
        # A single run in the window leaves no interval to measure, so cadence is
        # unknowable. Escalating on absolute age matters here: without it a task
        # last seen eleven days ago reported "delayed", never "down" — the rule
        # inverted exactly where the data was thinnest.
        elif minutes_since < NO_CADENCE_WARN:
            health = 'up'
        elif minutes_since < NO_CADENCE_DOWN:
            health = 'warn'
        else:
            health = 'down'

    return dict(
        meta,
        runs=len(runs),
        errors=sum(1 for r in runs if r['status'] == 'error'),
        skipped=sum(1 for r in runs if r['status'] == 'skipped'),
        avg_duration=round(sum(durations) / len(durations), 2) if durations else 0,
        max_duration=round(max(durations), 2) if durations else 0,
        cadence=cadence,
        minutes_since=minutes_since,
        health=health,
        last_time=last['time'] if last else None,
        last_status=last['status'] if last else None,
        last_summary=last['summary'] if last else '',
        gaps=find_gaps(runs, cadence, now),
        error_groups=group_errors(runs),
        series=downsample(runs),
    )


def correlate_incidents(by_task, tasks):
    """Merge failures into incidents, across tasks, by time.

    Failures land in the same incident when consecutive failures are no more
    than CLUSTER_GAP_MIN apart — regardless of which task produced them. An
    incident spanning more than one task is typed `upstream`, because the
    scheduler running six independent tasks does not fail three of them inside
    the same half hour by coincidence; something they all depend on did.

    Silence has no failure to cluster, so each gap becomes its own `silence`
    incident.
    """
    failures = []
    for key, runs in by_task.items():
        for r in runs:
            if r['status'] == 'error':
                failures.append({'time': r['time'], 'task': key, 'message': r['error']})
    failures.sort(key=lambda f: f['time'])

    clusters = []
    for f in failures:
        if clusters and (f['time'] - clusters[-1]['end']).total_seconds() / 60 <= CLUSTER_GAP_MIN:
            clusters[-1]['end'] = f['time']
            clusters[-1]['items'].append(f)
        else:
            clusters.append({'start': f['time'], 'end': f['time'], 'items': [f]})

    label_of = {t['key']: t['label'] for t in tasks}
    incidents = []
    for c in clusters:
        hit = sorted({f['task'] for f in c['items']},
                     key=lambda k: [t['key'] for t in tasks].index(k)
                     if k in [t['key'] for t in tasks] else 99)
        causes = [{'label': cause_label(msg), 'message': msg, 'count': n,
                   'task': task, 'task_label': label_of.get(task, task)}
                  for (task, msg), n in
                  Counter((f['task'], f['message']) for f in c['items']).most_common()]
        incidents.append({
            'kind':      'upstream' if len(hit) > 1 else 'task',
            'start':     c['start'],
            'end':       c['end'],
            'minutes':   round((c['end'] - c['start']).total_seconds() / 60),
            'ongoing':   False,
            'tasks':     hit,
            'task_labels': [label_of.get(k, k) for k in hit],
            'failures':  len(c['items']),
            'causes':    causes,
        })

    for t in tasks:
        for g in t['gaps']:
            incidents.append({
                'kind':      'silence',
                'start':     g['start'],
                'end':       g['end'],
                'minutes':   round(g['minutes']),
                'ongoing':   g.get('ongoing', False),
                'tasks':     [t['key']],
                'task_labels': [t['label']],
                'failures':  0,
                'causes':    [],
            })

    incidents.sort(key=lambda e: e['start'], reverse=True)
    return incidents


def rollup_causes(incidents):
    """One row per distinct cause, counted across every task it touched."""
    roll = {}
    for e in incidents:
        for c in e['causes']:
            r = roll.setdefault(c['label'], {
                'label': c['label'], 'message': c['message'], 'count': 0,
                'tasks': [], 'task_labels': [], 'first': e['start'],
            })
            r['count'] += c['count']
            if c['task'] not in r['tasks']:
                r['tasks'].append(c['task'])
                r['task_labels'].append(c['task_label'])
            if e['start'] < r['first']:
                r['first'] = e['start']
    rows = list(roll.values())
    rows.sort(key=lambda r: (-r['count'], r['first']))
    return rows


def build_verdict(tasks, shared, total_errors):
    """The page's lead finding, decided here rather than in the template.

    Order matters and is the whole point: a task that is not running outranks a
    task that ran and failed. An earlier version led with failure correlation
    unconditionally, so a window in which five of six tasks had stopped entirely
    rendered a green all-clear — the page was right about the rare question and
    silent on the urgent one.
    """
    stalled = [t for t in tasks if t['health'] in ('down', 'absent')]
    if stalled:
        return {
            'kind':    'silence',
            'stalled': [t['label'] for t in stalled],
            'count':   len(stalled),
            'of':      len(tasks),
            'absent':  [t['label'] for t in tasks if t['health'] == 'absent'],
        }
    if shared:
        return {
            'kind':     'upstream',
            'count':    len(shared),
            'lead':     max(shared, key=lambda e: e['failures']),
            'failures': sum(e['failures'] for e in shared),
            'of':       total_errors,
        }
    if total_errors:
        return {'kind': 'isolated', 'of': total_errors}
    return {'kind': 'clear', 'of': len(tasks)}


def build_monitor_page(rows, now, days=DEFAULT_DAYS):
    """The whole page payload: tasks, incidents, causes, summary, verdict."""
    by_task = normalize_runs(rows)
    # Every registry task, every time — a task with no runs at all is the most
    # important thing this page can report, so it must occupy its row rather
    # than shorten the list and leave the absence invisible.
    tasks = [task_stats(k, by_task.get(k, []), now) for k, _, _ in TASKS]
    # Anything logging under a name the registry doesn't know still shows up,
    # rather than silently vanishing from the one page meant to notice it.
    for key in sorted(set(by_task) - {k for k, _, _ in TASKS}):
        tasks.append(task_stats(key, by_task[key], now))

    incidents = correlate_incidents(by_task, tasks)
    causes = rollup_causes(incidents)
    shared = [e for e in incidents if e['kind'] == 'upstream']

    total_errors = sum(t['errors'] for t in tasks)
    # Only silence counts toward "longest gap". Ranging over every incident let a
    # figure labelled "längste Lücke" report the duration of an error storm.
    longest = max((e['minutes'] for e in incidents if e['kind'] == 'silence'),
                  default=0)
    verdict = build_verdict(tasks, shared, total_errors)

    return {
        'days':      days,
        'generated': now,
        # The lane strip's axis is the requested window, not the data's own
        # extent — so an idle task's lane reads as idle rather than rescaling.
        'window_start': now - dt.timedelta(days=days),
        'tasks':     tasks,
        'incidents': incidents,
        'causes':    causes,
        'verdict':   verdict,
        # Lead and figure now come from the same selection. They used to differ:
        # the sentence described the most recent shared outage while the number
        # counted the largest, so with two outages they named different events.
        'lead_incident': verdict.get('lead'),
        'summary': {
            'task_count':    len(tasks),
            'healthy':       sum(1 for t in tasks if t['health'] == 'up'),
            'stalled':       sum(1 for t in tasks if t['health'] in ('down', 'absent')),
            'absent':        sum(1 for t in tasks if t['health'] == 'absent'),
            'total_runs':    sum(t['runs'] for t in tasks),
            'total_errors':  total_errors,
            'total_skipped': sum(t['skipped'] for t in tasks),
            'cause_count':   len(causes),
            'longest_gap':   longest,
            'explained_by_shared': sum(e['failures'] for e in shared),
        },
    }

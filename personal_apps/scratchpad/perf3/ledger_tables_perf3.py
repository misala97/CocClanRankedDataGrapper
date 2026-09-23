"""The ledger's tables, derived from the JSON the Task 8 scripts saved.

No database, no app: it reads `measure.json`, `measure-<phase>.json`,
`admit_cost.json`, `profile_watch.json` and `two_workers.json` from one output
directory and prints markdown, so every number in the ledger's Measurements
section can be traced to a recorded sample rather than to a transcription.

    py -3.12 scratchpad/perf3/ledger_tables_perf3.py <out dir>

Statistics are median / p95 / max, p95 nearest-rank, as the scripts print.
"""
import json
import pathlib
import statistics
import sys


def load(out, name):
    path = out / name
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None


def trio(values, scale=1.0, digits=1):
    ordered = sorted(v for v in values if v is not None)
    if not ordered:
        return 'n=0', '-', '-', '-'
    p95 = ordered[max(0, round(0.95 * len(ordered)) - 1)]
    f = f'{{:,.{digits}f}}'
    return (str(len(ordered)), f.format(statistics.median(ordered) * scale),
            f.format(p95 * scale), f.format(ordered[-1] * scale))


def row(label, values, scale=1.0, digits=1, unit=''):
    n, median, p95, worst = trio(values, scale, digits)
    return f'| {label} | {n} | {median} | {p95} | {worst} |' + (
        f' {unit} |' if unit else '')


HEAD = '| | n | median | p95 | max |\n| --- | --- | --- | --- | --- |'
HEAD_UNIT = ('| | n | median | p95 | max | unit |\n'
             '| --- | --- | --- | --- | --- | --- |')


def cold_rows(reps, *, watch=True):
    got = [r for r in reps if r.get('seen_s') is not None
           and not r.get('first_was_board')]
    lines = [HEAD_UNIT,
             row('first answer: `pending`, rows null (NOT a board)',
                 [r['first_ms'] for r in got], unit='ms'),
             row('queue wait (`enqueued_at` -> `as_of`)',
                 [r.get('queue_wait_s') for r in got], digits=2, unit='s'),
             row('build (`build_ms`)',
                 [r['build_ms'] / 1000 for r in got if r.get('build_ms')],
                 digits=2, unit='s')]
    if watch:
        lines += [
            row('request -> publish (row polled every 50 ms)',
                [r.get('detected_s') for r in got], digits=2, unit='s'),
            row('a read issued at publication',
                [r.get('read_ms') for r in got], unit='ms'),
            row('**cold, read at publication -- UNMET <= 2 s goal**',
                [r['detected_s'] + r['read_ms'] / 1000 for r in got
                 if 'read_ms' in r], digits=2, unit='s')]
    lines += [
        row('build-to-usable (`as_of` -> board in hand)',
            [r.get('build_to_usable_s') for r in got], digits=2, unit='s'),
        row('**cold, as the client polls -- UNMET <= 2 s goal**',
            [r['seen_s'] for r in got], digits=2, unit='s')]
    within = sum(1 for r in got if r['seen_s'] <= 2.0)
    lines.append(f'\nBoards delivered: {len(got)} of {len(reps)}. First missing'
                 f' result within 2 s: **{within} of {len(got)}** -- the goal'
                 ' stays UNMET.')
    return '\n'.join(lines)


def section_measure(out):
    head = load(out, 'measure.json') or {}
    parts = []
    if head:
        parts.append(f"Prewarm from an empty store, producer start to eight"
                     f" fresh warm boards: **{head.get('prewarm_s')} s**;"
                     f" builds {head.get('prewarm_builds_ms')} ms (the first"
                     ' build in a fresh process fills its caches). Web-model'
                     f" workers listening after {head.get('web_ready_s')} s.")
    ready = load(out, 'measure-ready.json')
    if ready:
        lines = ['#### (a) Ready reads, an account watching three tickers',
                 f"Tickers {ready['tickers']} (the US 24h board's top three);"
                 ' the US All board, a warm key.', '', HEAD_UNIT]
        for window, entry in sorted(ready['windows'].items(),
                                    key=lambda item: int(item[0])):
            lines.append(row(f'{window}h `read_payload` ({entry["ready"]} ready,'
                             f' {entry["stale"]} stale)',
                             entry['raw_read_payload_ms'], unit='ms'))
            lines.append(row(f'{window}h over HTTP, web-model worker'
                             f' ({entry["http_ready"]} ready,'
                             f' {entry["http_stale"]} stale)',
                             entry['raw_http_ms'], unit='ms'))
        if ready.get('first_reads_ms'):
            lines.append('\nFirst read per process and window, outside the n'
                         ' (the first read with watches in a process meets'
                         ' its caches empty): '
                         + ', '.join(f'{k} {v} ms' for k, v in
                                     ready['first_reads_ms'].items()) + '.')
        parts.append('\n'.join(lines))
    empty = load(out, 'measure-empty.json')
    if empty:
        positions = sorted(r.get('built_position') for r in empty['reps'])
        parts.append('#### (b) Empty store: TRUNCATE both tables, then one'
                     ' request\n\nThe eight warm selections in turn; the'
                     ' requested board was built in position '
                     f'{positions} of 8.\n\n' + cold_rows(empty['reps']))
    restart = load(out, 'measure-restart.json')
    if restart:
        reps = restart['reps']
        parts.append('\n'.join([
            '#### (c) Restart: kill a web-model worker, start it, read', '',
            HEAD_UNIT,
            row('spawn -> listening (interpreter, launcher queries, app'
                ' import)',
                [r['startup_s'] for r in reps], digits=2, unit='s'),
            row('first read afterwards', [r['first_ms'] for r in reps],
                unit='ms'),
            row('second read', [r['second_ms'] for r in reps], unit='ms'),
            f"\nThe first read was a board in {sum(r['first_is_board'] for r in reps)}"
            f" of {len(reps)} ({sum(r['first_stale'] for r in reps)} stale)."]))
    cold = load(out, 'measure-cold.json')
    if cold:
        lines = ['#### (d) Cold on-demand selections, the producer running']
        for name in ('sort=lean 24h', 'limit=100 24h'):
            if name in cold:
                lines += ['', f'**{name}** (key deleted before every rep)', '',
                          cold_rows(cold[name])]
        repeated = cold.get('limit=100 repeated')
        if repeated:
            lines.append(f"\n**limit=100 repeated:** {repeated['ready']} ready"
                         f" reads of {repeated['rows']} rows, median / p95 /"
                         f" max {repeated['ms'][0]} / {repeated['ms'][1]} /"
                         f" {repeated['ms'][2]} ms.")
        parts.append('\n'.join(lines))
    memory = load(out, 'measure-memory.json')
    if memory:
        lines = ['#### (e) Memory, Windows working set (the local analogue of'
                 ' RSS), MB', '',
                 '| process | started | at rest | after 100 reads | peak |'
                 ' private |', '| --- | --- | --- | --- | --- | --- |']
        for name, after in memory['after_100_reads'].items():
            started = memory.get('started', {}).get(name, {}).get('ws_mb', '-')
            lines.append(f"| {name} | {started} | {memory['at_rest'][name]['ws_mb']}"
                         f" | {after['ws_mb']} | {after['peak_ws_mb']} |"
                         f" {after['private_mb']} |")
        if head.get('producer_end'):
            end = head['producer_end']
            lines.append(f"| producer at the end of Step 1 | | | {end['ws_mb']}"
                         f" | {end['peak_ws_mb']} | {end['private_mb']} |")
        parts.append('\n'.join(lines))
    for tag, title in (('queue', '(f) Queue age'),
                       ('contention', '(g) Under write contention')):
        data = load(out, f'measure-{tag}.json')
        if data:
            parts.append(queue_section(title, data))
    return '\n\n'.join(parts)


def queue_section(title, a):
    stale = a['warm_samples_stale']
    lines = [f'#### {title}', '',
             f"{a['samples']} table samples every 5 s; {a['builds_warm']} warm"
             f" and {a['builds_ondemand']} on-demand builds; the producer was"
             f" building {100 * a['producer_busy_share']:.0f}% of the window.",
             '', HEAD_UNIT,
             row('warm board age when its refresh landed',
                 a['warm_age_when_replaced_s'], unit='s'),
             row('warm refresh interval (`as_of` to `as_of`)',
                 a['warm_refresh_interval_s'], unit='s'),
             row('on-demand: request -> board in hand', a['demand_seen_s'],
                 digits=2, unit='s'),
             row('on-demand queue wait', a['demand_queue_wait_s'], digits=2,
                 unit='s'),
             row('on-demand first answer (pending)', a['demand_first_ms'],
                 unit='ms'),
             f"\nWorst warm age sampled: **{a['warm_age_sampled_max_s']} s**;"
             f" {stale} of {a['warm_samples']} warm samples"
             f" ({100 * stale / max(1, a['warm_samples']):.0f}%) past 120 s,"
             f" {a['warm_samples_expired']} past 600 s. On-demand delivered"
             f" {a['demand_delivered']} of {a['demand_requests']}; longest"
             f" sampled queued: {a['demand_sampled_waiting_max_s']} s."
             f" Build seconds median/p95/max: warm {a.get('build_s_warm')},"
             f" on-demand {a.get('build_s_ondemand')}. Slowest on-demand: "
             + '; '.join(f"{i['label']} {i['build_ms'] / 1000:.1f} s"
                         for i in a.get('slowest_ondemand', []))
             + f". Row-lock waits: {a['locks']['waits']}"
             f" ({a['locks']['time_ms']} ms)."]
    if 'writes' in a:
        lines += ['', '| write (16,792 live-hour rows) | update runs, s |'
                  ' restore runs, s |', '| --- | --- | --- |']
        for side, runs in (('alone, producer stopped', a['writes_alone']['runs']),
                           ('under the sweep', a['writes']['runs'])):
            lines.append(f"| {side} | "
                         + ', '.join(f"{r['update_s']:.2f}" for r in runs)
                         + ' | ' + ', '.join(f"{r['restore_s']:.2f}"
                                             for r in runs) + ' |')
    return '\n'.join(lines)


def section_admit(out):
    a = load(out, 'admit_cost.json')
    if not a:
        return ''
    lines = [f"`admit_cost_perf3.py`: {a['n']} admissions and {a['n']} polls per"
             f" arm and round, {a['rounds']} rounds, alternating order.", '',
             '| arm | kind | p50 with | p50 without | p95 with | p95 without |'
             ' p95 delta |', '| --- | --- | --- | --- | --- | --- | --- |']
    for name, s in a['verdict']['summary'].items():
        arm, kind = name.split('_')
        lines.append(f"| {'one process' if arm == 'single' else 'two processes'}"
                     f" | {kind} | {s['p50_with_ms']} | {s['p50_without_ms']} |"
                     f" {s['p95_with_ms']} | {s['p95_without_ms']} |"
                     f" {s['p95_delta_ms']:+.2f} |")
    lines += ['', '| arm | round | mode | row-lock waits | wait time ms |',
              '| --- | --- | --- | --- | --- |']
    for arm in ('single', 'pair'):
        for entry in a[arm]:
            lines.append(f"| {arm} | {entry['round']} | {entry['mode']} |"
                         f" {entry['locks']['waits']} |"
                         f" {entry['locks']['time_ms']} |")
    verdict = a['verdict']
    lines.append('\nVerdict: **' + ('TRIGGERED -- ' + '; '.join(verdict['reasons'])
                                    if verdict['triggered'] else 'NOT TRIGGERED')
                 + '**')
    return '\n'.join(lines)


def section_profile(out):
    p = load(out, 'profile_watch.json')
    if not p:
        return ''
    lines = [f"Watched tickers from {p['origin']}: {p['tickers']}.", '',
             '| board | watching | n | median ms | p95 ms | max ms | watch rows |',
             '| --- | --- | --- | --- | --- | --- | --- |']
    for case in p['cases']:
        n, median, p95, worst = trio(case['raw_ms'])
        lines.append(f"| {case['market']} {case['window']}h | {case['watching']}"
                     f" | {n} | {median} | {p95} | {worst} |"
                     f" {case['watch_rows']} |")
    if p.get('reads'):
        lines += ['', '| whole `read_payload`, US 24h, watching | median ms |'
                  ' p95 ms | max ms | ready/stale |', '| --- | --- | --- | --- | --- |']
        for read in p['reads']:
            lines.append(f"| {read['watching']} | {read['ms'][0]} |"
                         f" {read['ms'][1]} | {read['ms'][2]} |"
                         f" {read['kinds'].count('ready')}/"
                         f"{read['kinds'].count('stale')} |")
    v = p['verdict']
    lines.append(f"\nThe worst 25-ticker median"
                 f" ({v.get('governing_case', 'US 24h')}):"
                 f" **{v['governing_median_ms']} ms** against"
                 f" {v['limit_ms']:.0f} ms ->"
                 f" {'TRIGGERED' if v['triggered'] else 'NOT TRIGGERED'}.")
    return '\n'.join(lines)


def section_two_workers(out):
    t = load(out, 'two_workers.json')
    if not t:
        return ''
    lines = ['| flag | `/` idle median / p95 / max ms | `/` during two cold'
             ' boards: n, median / p95 / max ms | boards in hand, median /'
             ' p95 / max s | statuses |', '| --- | --- | --- | --- | --- |']
    for flag in ('on', 'off'):
        if flag not in t:
            continue
        f = t[flag]
        cheap = [c['ms'] for e in f['episodes'] for c in e['cheap']]
        n, median, p95, worst = trio(cheap)
        idle = trio(f['idle_ms'])
        boards = [b['board_s'] for e in f['episodes'] for b in e['boards']]
        b = trio(boards, digits=2)
        lines.append(f'| {flag.upper()} | {idle[1]} / {idle[2]} / {idle[3]} |'
                     f' {n}, {median} / {p95} / {worst} | {b[1]} / {b[2]} /'
                     f" {b[3]} | {f['cheap_statuses']} |")
    if 'on' in t:
        lines.append(f"\nRow-lock waits across the flag-ON episodes:"
                     f" {t['on']['locks']['waits']} ({t['on']['locks']['time_ms']}"
                     ' ms).')
    return '\n'.join(lines)


def main():
    out = pathlib.Path(sys.argv[1])
    for title, text in (('Step 1', section_measure(out)),
                        ('Decision 6', section_admit(out)),
                        ('Step 3', section_profile(out)),
                        ('Step 2', section_two_workers(out))):
        print(f'\n<!-- {title} -->\n{text}\n')


if __name__ == '__main__':
    main()

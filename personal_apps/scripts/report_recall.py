# personal_apps/scripts/report_recall.py
"""What the extractor's rules throw away, per week, in real mentions.

Joins the recall wave's labels to the candidates they were drawn from and
turns a per-cause hit rate into a weekly count, using the volumes the
population pass measured over the same seven days.

    cd personal_apps && PYTHONPATH=. python -m scripts.report_recall \\
        --labels C:/Users/michi/Desktop/radar_labels/labels-recall.jsonl \\
        --candidates C:/Users/michi/Desktop/radar_labels/candidates-2026-09-06.jsonl \\
        --population C:/Users/michi/Desktop/radar_labels/raw/population/population.json

UNCERTAIN IS A BAND, NOT A VOTE. A label of `uncertain` says the text does
not support a decision, so it is neither a recovered mention nor a
confirmed miss. The report gives the low estimate (uncertain counts as
junk) and the high one (uncertain counts as real); the truth is between,
and the width of the band is itself worth reading.

The per-symbol table is the actionable half: a cause is a class, but what
ships is a name token or a lowercase symbol, and only the symbols whose
own hit rate is high AND whose volume is real are worth the change.

No model is called here.
"""
import argparse
import collections
import json


def _rate(hits, total):
    return (hits / total) if total else None


def build(labels, candidates, volumes, symbol_volumes=None):
    """The report. `volumes` is candidates per cause per week; the optional
    `symbol_volumes` is {cause: {symbol: per-week}} for the symbol table."""
    by_id = {c['mention_id']: c for c in candidates}
    per_cause = collections.defaultdict(collections.Counter)
    per_symbol = collections.defaultdict(collections.Counter)
    for label in labels:
        candidate = by_id.get(label['mention_id'])
        if candidate is None:
            raise KeyError('label %s has no candidate row' % label['mention_id'])
        cause = candidate['candidate']['cause']
        per_cause[cause][label['relevance']] += 1
        per_symbol[(cause, candidate['ticker'])][label['relevance']] += 1

    by_cause = {}
    for cause, volume in volumes.items():
        counts = per_cause.get(cause, collections.Counter())
        labelled = sum(counts.values())
        relevant = counts['relevant']
        uncertain = counts['uncertain']
        low = _rate(relevant, labelled)
        high = _rate(relevant + uncertain, labelled)
        by_cause[cause] = {
            'labelled': labelled, 'relevant': relevant,
            'irrelevant': counts['irrelevant'], 'uncertain': uncertain,
            'hit_rate': low, 'hit_rate_low': low, 'hit_rate_high': high,
            'weekly_volume': volume,
            'weekly_recovered': None if low is None else round(low * volume),
            'weekly_recovered_high': None if high is None else round(high * volume),
        }

    rows = []
    for (cause, symbol), counts in per_symbol.items():
        labelled = sum(counts.values())
        rate = _rate(counts['relevant'], labelled)
        volume = (symbol_volumes or {}).get(cause, {}).get(symbol)
        if volume is None:
            # Fall back to the cause's volume shared by labelled share.
            cause_labelled = sum(per_cause[cause].values())
            volume = (volumes.get(cause, 0) * labelled / cause_labelled
                      if cause_labelled else 0)
        rows.append({
            'cause': cause, 'symbol': symbol, 'labelled': labelled,
            'relevant': counts['relevant'], 'irrelevant': counts['irrelevant'],
            'uncertain': counts['uncertain'], 'hit_rate': rate,
            'weekly_volume': round(volume),
            'weekly_recovered': round((rate or 0) * volume),
        })
    rows.sort(key=lambda r: (-r['weekly_recovered'], -(r['hit_rate'] or 0), r['symbol']))

    total = sum(row['weekly_recovered'] for row in by_cause.values()
                if row['weekly_recovered'] is not None)
    return {'by_cause': by_cause, 'by_symbol': rows, 'weekly_recovered_total': total,
            'labelled_total': sum(sum(c.values()) for c in per_cause.values())}


def _read_jsonl(path):
    with open(path, encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--labels', required=True)
    parser.add_argument('--candidates', required=True)
    parser.add_argument('--population', required=True)
    parser.add_argument('--rejected', default=None,
                        help='rejected-candidates.jsonl, for exact per-symbol volumes')
    parser.add_argument('--out', default=None, help='write the report as JSON too')
    args = parser.parse_args(argv)

    labels = _read_jsonl(args.labels)
    candidates = _read_jsonl(args.candidates)
    with open(args.population, encoding='utf-8') as handle:
        population = json.load(handle)
    # The invisible arm is the recall question: a candidate beside an
    # accepted ticker rode in on a post the pipeline already stored.
    volumes = population['rejected_by_cause_invisible']

    symbol_volumes = None
    if args.rejected:
        symbol_volumes = collections.defaultdict(collections.Counter)
        for row in _read_jsonl(args.rejected):
            if not row['stored_today']:
                symbol_volumes[row['cause']][row['symbol']] += 1

    report = build(labels, candidates, volumes, symbol_volumes)

    print('labelled %d rows\n' % report['labelled_total'])
    print('%-24s %7s %7s %7s %7s   %7s  %9s  %s'
          % ('cause', 'labels', 'real', 'junk', 'unsure', 'hit', 'per week', 'recovered/wk'))
    for cause, row in sorted(report['by_cause'].items(),
                             key=lambda kv: -(kv[1]['weekly_recovered'] or 0)):
        hit = '   -  ' if row['hit_rate'] is None else '%5.1f%%' % (100 * row['hit_rate'])
        rec = '   -' if row['weekly_recovered'] is None else '%d' % row['weekly_recovered']
        high = '' if row['weekly_recovered_high'] is None else ' (up to %d)' % row['weekly_recovered_high']
        print('%-24s %7d %7d %7d %7d   %7s  %9d  %s%s'
              % (cause, row['labelled'], row['relevant'], row['irrelevant'],
                 row['uncertain'], hit, row['weekly_volume'], rec, high))
    print('\ntotal recovered per week (measured causes): %d'
          % report['weekly_recovered_total'])

    print('\ntop symbols by weekly mentions recovered:')
    print('%-24s %-8s %6s %6s %7s %9s %s'
          % ('cause', 'symbol', 'labels', 'real', 'hit', 'per week', 'recovered/wk'))
    for row in report['by_symbol'][:40]:
        print('%-24s %-8s %6d %6d %6.0f%% %9d %d'
              % (row['cause'], row['symbol'], row['labelled'], row['relevant'],
                 100 * (row['hit_rate'] or 0), row['weekly_volume'],
                 row['weekly_recovered']))

    if args.out:
        with open(args.out, 'w', encoding='utf-8') as handle:
            json.dump(report, handle, indent=1)
        print('\nwrote %s' % args.out)


if __name__ == '__main__':
    main()

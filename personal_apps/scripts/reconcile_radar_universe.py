# personal_apps/scripts/reconcile_radar_universe.py
"""Report what two local Nasdaq directory files and the database disagree about.

    python scripts/reconcile_radar_universe.py \
        nasdaqlisted.txt otherlisted.txt --report run.json

Dry run is the default and the only mode reachable without a reviewed
manifest. In dry run this reads two local files and issues bounded `SELECT`s;
it writes nothing to the database, acquires no lock and mutates no ORM object.

It downloads nothing. The two inputs are local paths bound by basename to the
two documented files, because which column carries the listing code depends on
which file it came from.
"""
import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, '.')

from features.radar.universe_directory import (  # noqa: E402
    parse_directory, source_kind_for, validate_pair,
)
from features.radar.universe_reconcile import (  # noqa: E402
    apply_approved_mappings, load_approved_mappings, load_current_state,
    reconcile,
)

DRY_RUN = 'dry-run'
APPLY = 'apply'


def build_parser():
    parser = argparse.ArgumentParser(
        prog='reconcile_radar_universe',
        description='Reconcile local Nasdaq directory files against the '
                    'Radar universe and its US instrument mappings.')
    parser.add_argument('paths', nargs=2, metavar='DIRECTORY_FILE',
                        help='local nasdaqlisted.txt and otherlisted.txt')
    parser.add_argument('--report', required=True, metavar='PATH',
                        help='where to write the deterministic JSON report')
    parser.add_argument('--apply-mappings', action='store_true',
                        help='insert the approved US primary rows; requires '
                             '--approved-mappings')
    parser.add_argument('--approved-mappings', metavar='PATH',
                        help='a reviewed approval manifest')
    return parser


def parse_args(argv):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.apply_mappings and not args.approved_mappings:
        parser.error('--apply-mappings requires --approved-mappings PATH')
    if args.approved_mappings and not args.apply_mappings:
        parser.error('--approved-mappings is only meaningful with '
                     '--apply-mappings')
    return args


def read_snapshots(paths):
    """Parse both inputs, bound by basename, and refuse an unusable pair."""
    snapshots = {}
    for path in paths:
        kind = source_kind_for(path)
        if kind in snapshots:
            raise ValueError(f'{path}: {kind} was supplied twice')
        snapshots[kind] = parse_directory(path, kind)
    missing = {'nasdaqlisted', 'otherlisted'} - set(snapshots)
    if missing:
        raise ValueError(f'missing {", ".join(sorted(missing))}')
    nasdaq, other = snapshots['nasdaqlisted'], snapshots['otherlisted']
    validate_pair(nasdaq, other)
    return nasdaq, other


def build_report(nasdaq, other, session, *, mode=DRY_RUN):
    """The report payload. Deterministic: no clock, no host, no environment."""
    identities, mappings = load_current_state(session)
    result = reconcile([*nasdaq.rows, *other.rows], identities, mappings,
                       mapping_source=nasdaq.mapping_source,
                       source_digests={snapshot.source_kind: snapshot.sha256
                                       for snapshot in (nasdaq, other)})
    return result, {
        'mode': mode,
        'mapping_source': nasdaq.mapping_source,
        'sources': {snapshot.source_kind: {
            'sha256': snapshot.sha256,
            'file_created_at': snapshot.file_created_at.isoformat(),
            'bom_present': snapshot.bom_present,
            'usable_rows': len(snapshot.rows),
        } for snapshot in (nasdaq, other)},
        'current_state': {'identities': len(identities),
                          'us_instrument_rows': len(mappings)},
        'counts': result.counts,
        'cohorts': result.as_dict(),
    }


def write_report(path, payload):
    """Write the report in one replace, so a reader never sees a partial file."""
    text = json.dumps(payload, indent=2, sort_keys=True) + '\n'
    temporary = f'{path}.partial'
    with open(temporary, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(text)
    os.replace(temporary, path)


def summarise(payload, report_path):
    lines = [f'mode: {payload["mode"]}',
             f'mapping source: {payload["mapping_source"]}']
    for kind, source in sorted(payload['sources'].items()):
        lines.append(f'{kind}: {source["usable_rows"]} usable rows, created '
                     f'{source["file_created_at"]}, sha256 {source["sha256"]}')
    lines.append(f'current: {payload["current_state"]["identities"]} '
                 f'identities, '
                 f'{payload["current_state"]["us_instrument_rows"]} US rows')
    for name, count in payload['counts'].items():
        lines.append(f'{name}: {count}')
    if 'apply' in payload:
        for name in ('inserted', 'skipped', 'refused'):
            lines.append(f'{name}: {len(payload["apply"][name])}')
        lines.extend(payload['apply']['problems'])
    lines.append(f'report: {report_path}')
    return '\n'.join(lines)


def _run(args, session, lock=None):
    nasdaq, other = read_snapshots(args.paths)
    result, payload = build_report(nasdaq, other, session)
    outcome = None
    if args.apply_mappings:
        payload, outcome = _apply(args, session, result, payload, lock)
    write_report(args.report, payload)
    print(summarise(payload, args.report))
    if outcome is not None and not outcome.ok:
        return 1
    return 0


def _apply(args, session, result, payload, lock=None):
    """Insert the reviewed rows, then report what actually happened.

    The manifest is validated before the transaction opens, and the report is
    written by the caller only once the transaction's outcome is known, so a
    report can never claim a write the database did not take.
    """
    approvals = load_approved_mappings(args.approved_mappings)
    # The report's reads ran before any lock existed. End their transaction
    # here, so nothing after this line can see through its snapshot; the
    # writer rechecks everything in a transaction of its own, under the lock.
    session.rollback()
    outcome = apply_approved_mappings(session, result, approvals,
                                      dt.datetime.now(dt.timezone.utc),
                                      lock=lock)
    payload = dict(payload)
    payload['mode'] = APPLY
    payload['approved'] = [item.symbol for item in approvals]
    payload['apply'] = {'inserted': list(outcome.inserted),
                        'skipped': list(outcome.skipped),
                        'refused': list(outcome.refused),
                        'problems': list(outcome.problems)}
    return payload, outcome


def main(argv=None, *, session_factory=None, lock=None):
    """`session_factory` and `lock` are test seams for an isolated target.

    Production passes neither, so it binds the configured database and the
    real named MySQL lock, which refuses on any bind that cannot provide one.
    """
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if session_factory is not None:
        return _run(args, session_factory(), lock)

    from app import app
    from extensions import db

    with app.app_context():
        return _run(args, db.session, lock)


if __name__ == '__main__':
    raise SystemExit(main())

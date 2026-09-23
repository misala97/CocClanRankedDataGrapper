"""Candidate fingerprint for MD-SELECTED-PRICE-CORRECTION-2.

    py -3.12 radar-design/artifacts/md-selected-price-correction-2/fingerprint.py [--check-only] [--out NAME]

Same method as ../md-selected-price-implementation/fingerprint.py (which is
left untouched with its fingerprint.json): every application/test file under
personal_apps that Git reports modified or untracked (non-ignored), hashed
with line endings normalized to LF, plus the generated Radar bundle
(static/radar/dist, Git-ignored) byte for byte. Writes into THIS directory
only (default fingerprint-final.json); --check-only prints without writing and
lists paths whose hash differs from a previous manifest given by --compare.
"""
import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def git(*args):
    return subprocess.run(['git', '-c', 'safe.directory=*', *args], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout


def compute():
    changed = git('diff', '--name-only', '--', 'personal_apps').split()
    added = git('ls-files', '--others', '--exclude-standard', '--', 'personal_apps').split()
    sources = sorted({p for p in changed + added if '__pycache__' not in p and (ROOT / p).is_file()})
    dist = sorted(str(p.relative_to(ROOT)).replace('\\', '/')
                  for p in (ROOT / 'personal_apps/static/radar/dist').rglob('*') if p.is_file())
    files = {}
    for path in sources:
        data = (ROOT / path).read_bytes().replace(b'\r\n', b'\n')
        files[path] = {'sha256_lf': hashlib.sha256(data).hexdigest(),
                       'kind': 'modified' if path in changed else 'added'}
    for path in dist:
        files[path] = {'sha256': hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), 'kind': 'generated'}
    lines = ''.join(f"{path}\t{info.get('sha256_lf') or info['sha256']}\n" for path, info in sorted(files.items()))
    return {
        'recorded_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'branch': git('rev-parse', '--abbrev-ref', 'HEAD').strip(),
        'head': git('rev-parse', 'HEAD').strip(),
        'digest': hashlib.sha256(lines.encode('utf-8')).hexdigest(),
        'counts': {'modified': len(changed), 'added': len([p for p in sources if p not in changed]),
                   'generated': len(dist)},
        'files': files,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--out', default='fingerprint-final.json')
    parser.add_argument('--compare')
    args = parser.parse_args()
    out = compute()
    summary = {k: out[k] for k in ('branch', 'head', 'digest', 'counts')}
    if args.compare:
        previous = json.loads(Path(args.compare).read_text(encoding='utf-8'))['files']
        def digest(info):
            return info.get('sha256_lf') or info.get('sha256') if info else None
        summary['differs_from_compare'] = sorted(
            p for p in set(previous) | set(out['files']) if digest(previous.get(p)) != digest(out['files'].get(p)))
    if not args.check_only:
        (HERE / args.out).write_text(json.dumps(out, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()

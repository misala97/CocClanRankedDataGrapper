"""Candidate fingerprint for MD-SELECTED-PRICE-IMPLEMENT-1.

    py -3.12 radar-design/artifacts/md-selected-price-implementation/fingerprint.py

Hashes every application/test file this assignment changed or added under
personal_apps (from Git: tracked modifications plus untracked, non-ignored
files) with line endings normalized to LF -- the repository stores LF and this
Windows checkout uses core.autocrlf=true -- plus the generated Radar bundle
(static/radar/dist, ignored by Git) byte for byte. Writes fingerprint.json.
"""
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


def main():
    changed = git('diff', '--name-only', '--', 'personal_apps').split()
    added = git('ls-files', '--others', '--exclude-standard', '--', 'personal_apps').split()
    sources = sorted({p for p in changed + added if '__pycache__' not in p and (ROOT / p).is_file()})
    dist = sorted(str(p.relative_to(ROOT)).replace('\\', '/')
                  for p in (ROOT / 'personal_apps/static/radar/dist').rglob('*') if p.is_file())
    files = {}
    for path in sources:
        data = (ROOT / path).read_bytes().replace(b'\r\n', b'\n')
        files[path] = {'sha256_lf': hashlib.sha256(data).hexdigest(), 'kind': 'modified' if path in changed else 'added'}
    for path in dist:
        files[path] = {'sha256': hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), 'kind': 'generated'}
    lines = ''.join(f"{path}\t{info.get('sha256_lf') or info['sha256']}\n" for path, info in sorted(files.items()))
    out = {
        'recorded_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'branch': git('rev-parse', '--abbrev-ref', 'HEAD').strip(),
        'head': git('rev-parse', 'HEAD').strip(),
        'digest': hashlib.sha256(lines.encode('utf-8')).hexdigest(),
        'counts': {'modified': len(changed), 'added': len([p for p in sources if p not in changed]),
                   'generated': len(dist)},
        'files': files,
    }
    (HERE / 'fingerprint.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
    print(json.dumps({k: out[k] for k in ('branch', 'head', 'digest', 'counts')}, indent=1))


if __name__ == '__main__':
    main()

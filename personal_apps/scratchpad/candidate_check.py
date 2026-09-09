"""Acceptance evidence for the P2 candidate transplant.

Codex requires: the selected and excluded SHAs, the resulting file diff, proof
that no excluded commit is an ancestor of the candidate, and proof that no
unapproved research change entered through conflict resolution.
"""
import subprocess
import sys

CANDIDATE = r'C:/Users/michi/Desktop/CodingStuff-worktrees/radar-release-candidate'
SOURCE = r'C:/Users/michi/Desktop/CodingStuff-worktrees/radar-foundations'
BASE = '7a9ffe4'


def git(*args, cwd=CANDIDATE):
    return subprocess.run(['git', *args], cwd=cwd, capture_output=True,
                          text=True, check=False).stdout.strip()


head = git('rev-parse', 'HEAD')
origin_main = git('rev-parse', 'origin/main')
print(f'candidate HEAD      {head[:12]}')
print(f'branched from       origin/main {origin_main[:12]}')
print(f'source branch       codex/radar-foundations '
      f'{git("rev-parse", "codex/radar-foundations")[:12]}')

selected = [line for line in
            git('rev-list', '--reverse', f'{BASE}..codex/radar-foundations',
                cwd=SOURCE).split('\n') if line]
transplanted = [line for line in
                git('rev-list', '--reverse', 'origin/main..HEAD').split('\n')
                if line]
print(f'\nselected from source  {len(selected)} commits')
print(f'transplanted on cand. {len(transplanted)} commits')
print(f'counts match          {len(selected) == len(transplanted)}')

excluded = [line for line in
            git('rev-list', f'origin/main..{BASE}', cwd=SOURCE).split('\n')
            if line]
print(f'excluded (below the base, unpublished) {len(excluded)} commits')

print('\n--- is any EXCLUDED commit an ancestor of the candidate? ---')
leaked = []
for sha in excluded:
    result = subprocess.run(
        ['git', 'merge-base', '--is-ancestor', sha, 'HEAD'],
        cwd=CANDIDATE, capture_output=True)
    if result.returncode == 0:
        leaked.append(sha)
print(f'leaked: {leaked or "NONE"}')

print('\n--- does the candidate tree contain any file from those 12? ---')
# Every path the excluded commits touched, and whether the candidate differs
# from origin/main there. A difference would mean research content rode along.
touched = set()
for sha in excluded:
    for path in git('show', '--name-only', '--pretty=format:', sha,
                    cwd=SOURCE).split('\n'):
        if path.strip():
            touched.add(path.strip())
print(f'paths touched by the excluded 12: {len(touched)}')
contaminated = []
for path in sorted(touched):
    diff = git('diff', '--name-only', f'origin/main..HEAD', '--', path)
    if diff:
        contaminated.append(path)
print(f'of those, changed by the candidate: {contaminated or "NONE"}')

print('\n--- the candidate diff against origin/main ---')
stat = git('diff', '--stat', 'origin/main..HEAD')
print(stat.split('\n')[-1] if stat else '(empty)')

print('\n--- same tree as the source branch? ---')
cand_tree = git('rev-parse', 'HEAD^{tree}')
src_tree = git('rev-parse', 'codex/radar-foundations^{tree}', cwd=SOURCE)
print(f'candidate tree {cand_tree[:12]}')
print(f'source tree    {src_tree[:12]}')
print(f'identical      {cand_tree == src_tree}')
if cand_tree != src_tree:
    print('  differing paths (expected: only what the 12 contributed):')
    names = subprocess.run(
        ['git', 'diff', '--name-only', 'codex/radar-foundations', 'HEAD'],
        cwd=CANDIDATE, capture_output=True, text=True).stdout.strip()
    for line in names.split('\n')[:40]:
        if line:
            print(f'    {line}')

sys.exit(1 if leaked or contaminated else 0)

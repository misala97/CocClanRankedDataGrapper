"""Acceptance evidence for the P2 release candidate.

Codex requires: the selected and excluded SHAs, the resulting file diff, proof
that no excluded commit is an ancestor of the candidate, and proof that no
unapproved research change entered through conflict resolution.

    py -3.12 personal_apps/scratchpad/candidate_check.py

Exits non-zero if ANY claim fails. The first version of this script exited 0
whatever it printed -- it failed only on a leaked ancestor -- so it could report
`counts match False` and still pass. It also swallowed git's stderr and return
code, which made a mistyped revision look like "nothing found, all clear". Both
are fixed: every claim is a check, and a failing git invocation raises.

TRANSPLANT_TIP is the commit the file counts describe. Documentation commits
land on top of it afterwards, so the counts are quoted against that tip rather
than against a moving HEAD; ancestry and contamination are checked against HEAD,
where they matter.
"""
import subprocess
import sys

CANDIDATE = r'C:/Users/michi/Desktop/CodingStuff-worktrees/radar-release-candidate'
SOURCE = r'C:/Users/michi/Desktop/CodingStuff-worktrees/radar-foundations'
BASE = '7a9ffe4'
SOURCE_BRANCH = 'codex/radar-foundations'
TRANSPLANT_TIP = '91d3e2b'

FAILURES = []


def check(label, condition, detail=''):
    mark = 'PASS' if condition else 'FAIL'
    print(f'  {mark}  {label}' + (f' -- {detail}' if detail else ''))
    if not condition:
        FAILURES.append(label)


def git(*args, cwd=CANDIDATE):
    """git, where a failure is a failure.

    Checking the return code matters more than it looks: a silent empty result
    from a mistyped revision would make every "nothing found" check pass.
    """
    result = subprocess.run(['git', *args], cwd=cwd, capture_output=True,
                            text=True)
    if result.returncode != 0:
        raise SystemExit(
            f'git {" ".join(args)} failed in {cwd}:\n{result.stderr.strip()}')
    return result.stdout.strip()


def lines(*args, **kwargs):
    return [line for line in git(*args, **kwargs).split('\n') if line]


def main():
    head = git('rev-parse', 'HEAD')
    print(f'candidate HEAD      {head[:12]}')
    print(f'transplant tip      {git("rev-parse", TRANSPLANT_TIP)[:12]}')
    print(f'branched from       origin/main '
          f'{git("rev-parse", "origin/main")[:12]}')
    print(f'source branch       {git("rev-parse", SOURCE_BRANCH)[:12]}\n')

    selected = lines('rev-list', '--reverse', f'{BASE}..{SOURCE_BRANCH}',
                     cwd=SOURCE)
    transplanted = lines('rev-list', '--reverse',
                         f'origin/main..{TRANSPLANT_TIP}')
    check('every selected commit was transplanted',
          len(selected) == len(transplanted),
          f'{len(selected)} selected, {len(transplanted)} transplanted')

    excluded = lines('rev-list', f'origin/main..{BASE}', cwd=SOURCE)
    check('the excluded set is the twelve unpublished commits',
          len(excluded) == 12, f'{len(excluded)} commits')

    leaked = []
    for sha in excluded:
        result = subprocess.run(
            ['git', 'merge-base', '--is-ancestor', sha, 'HEAD'],
            cwd=CANDIDATE, capture_output=True)
        if result.returncode == 0:
            leaked.append(sha[:12])
    check('no excluded commit is an ancestor of the candidate',
          not leaked, f'leaked: {leaked}' if leaked else '')

    touched = set()
    for sha in excluded:
        for path in git('show', '--name-only', '--pretty=format:', sha,
                        cwd=SOURCE).split('\n'):
            if path.strip():
                touched.add(path.strip())
    check('the excluded commits touch the expected 19 paths',
          len(touched) == 19, f'{len(touched)} paths')

    # Content, not merely commit ancestry: a cherry-pick conflict resolved the
    # wrong way would change one of these with no excluded commit ever becoming
    # an ancestor.
    contaminated = [path for path in sorted(touched)
                    if git('diff', '--name-only', 'origin/main..HEAD', '--',
                           path)]
    check('the candidate changes none of those paths',
          not contaminated, f'changed: {contaminated}' if contaminated else '')

    stat = lines('diff', '--stat', f'origin/main..{TRANSPLANT_TIP}')
    print(f'\n  diff at the transplant tip: {stat[-1].strip()}')

    cand_tree = git('rev-parse', f'{TRANSPLANT_TIP}^{{tree}}')
    src_tree = git('rev-parse', f'{SOURCE_BRANCH}^{{tree}}', cwd=SOURCE)
    differing = set(lines('diff', '--name-only', SOURCE_BRANCH,
                          TRANSPLANT_TIP))
    check('at the transplant tip the tree differs from the source branch by '
          'exactly the excluded work',
          cand_tree != src_tree and differing == touched,
          f'{len(differing)} differing paths, expected {len(touched)}')

    print(f'\n{"FAILURES: " + "; ".join(FAILURES) if FAILURES else "all checks passed"}')
    return 1 if FAILURES else 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Put each defect back and check the test that claims to catch it fails.

A test that passes against the bug it is named for is worse than no test: the
independent review proved one of these was exactly that. So each mutation is
applied to a COPY of api.py, the suite is run, and the file is restored.
"""
import shutil
import subprocess
import sys

API = 'features/radar/routes/api.py'
BACKUP = API + '.mutation-backup'

MUTATIONS = [
    ('cache written AFTER the waiters are woken',
     'test_the_board_is_cached_before_the_waiters_are_woken',
     """        with _board_lock:
            board_cache[key] = (now + BOARD_TTL, board)""",
     """        _mutation_wake()
        with _board_lock:
            board_cache[key] = (now + BOARD_TTL, board)"""),

    ('waiter falls through unclaimed (the herd)',
     'test_a_failed_build_does_not_start_a_herd',
     """        if attempts >= 2:""",
     """        if attempts >= 1:"""),

    ('timeout does not clear the dead claim (poisoning)',
     'test_a_hung_build_does_not_poison_the_key_forever',
     """            with _board_lock:
                if _board_builds.get(key) is building:
                    del _board_builds[key]
        if attempts >= 2:""",
     """            pass
        if attempts >= 2:"""),
]

WAKE_HELPER = '''

def _mutation_wake():
    """Injected by mutate.py only."""
    import inspect
    frame = inspect.currentframe().f_back
    building = frame.f_locals.get('building')
    mine = frame.f_locals.get('mine')
    if mine and building is not None:
        building.set()
'''


def run(test):
    return subprocess.run(
        [sys.executable, '-m', 'pytest', 'tests/test_radar_api.py', '-q',
         '-k', test, '-p', 'no:randomly'],
        capture_output=True, text=True).returncode


def main():
    shutil.copyfile(API, BACKUP)
    try:
        for label, test, old, new in MUTATIONS:
            src = open(BACKUP, encoding='utf-8').read()
            if old not in src:
                print('  SKIP  %-52s anchor not found' % label)
                continue
            mutated = src.replace(old, new, 1)
            if '_mutation_wake()' in new:
                mutated += WAKE_HELPER
            open(API, 'w', encoding='utf-8').write(mutated)
            code = run(test)
            verdict = 'CAUGHT' if code != 0 else '*** MISSED ***'
            print('  %-14s %-52s (%s)' % (verdict, label, test))
    finally:
        shutil.copyfile(BACKUP, API)
        import os
        os.remove(BACKUP)
        print('api.py restored')


if __name__ == '__main__':
    main()

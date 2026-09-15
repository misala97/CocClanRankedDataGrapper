"""TEST-ONLY child program for test_launcher_isolation.py.

Started by the PRODUCTION subprocess launcher exactly as the fetch child is
(`python -E -s -B -m tests.selected_price_unit.probe_child MARKER BASE`), it
points the Yahoo module at the test's loopback server, runs the production
child's own `price_chart_fetch.main()` over the real stdin/stdout pipes, and
then appends what this child process actually had to the marker file: its
pid, whether any application/Flask/database module was loaded, its
environment KEYS (never values, apart from the dummy sentinel's presence) and
its interpreter flags. Nothing in production imports or selects this module.
"""
import json
import os
import sys

HEAVY = ('flask', 'flask_sqlalchemy', 'sqlalchemy', 'extensions', 'models', 'app', 'auth',
         'dotenv', 'pymysql', 'MySQLdb')


def main():
    marker, base = sys.argv[1], sys.argv[2]
    from features.radar.prices import yahoo
    yahoo.API_BASE = base
    from features.radar import price_chart_fetch as fetch
    code = fetch.main()
    main_module = sys.modules['__main__']
    record = {
        'role': 'child',
        'pid': os.getpid(),
        'main_spec': getattr(getattr(main_module, '__spec__', None), 'name', None),
        'heavy_modules': sorted(name for name in HEAVY if name in sys.modules),
        'env_keys': sorted(os.environ),
        'dummy_sentinel_present': 'RADAR_SP_DUMMY_SECRET' in os.environ,
        'sitecustomize_hook_loaded': 'sitecustomize' in sys.modules
                                     and 'RADAR_SP_HOOK' in getattr(sys.modules['sitecustomize'], '__doc__', ''),
        'flags': {'ignore_environment': sys.flags.ignore_environment,
                  'no_user_site': sys.flags.no_user_site,
                  'dont_write_bytecode': sys.flags.dont_write_bytecode},
    }
    with open(marker, 'a', encoding='utf-8') as handle:
        handle.write(json.dumps(record) + '\n')
    return code


if __name__ == '__main__':
    sys.exit(main())

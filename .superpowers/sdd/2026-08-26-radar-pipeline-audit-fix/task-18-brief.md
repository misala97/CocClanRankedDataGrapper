## Task 18: The discovery script stops fighting the daemon

**Files:**
- Modify: `personal_apps/scripts/discover_reddit_sources.py`

**Interfaces:**
- Consumes: nothing.
- Produces: a `--anyway` flag; without it the script exits non-zero when `radar_ingest` is running.

The script polls the same `/comments/.rss` feeds at `SLEEP = 45.0`. The daemon polls one feed per 120 seconds against a budget measured at `x-ratelimit-remaining = 0.0` after a single request. From one IP they 429 each other, and the daemon's cycle then reports `missing` and writes no buckets.

- [ ] **Step 1: Add the guard**

In `personal_apps/scripts/discover_reddit_sources.py`, above `main()`:

```python
def _daemon_is_running():
    """True when radar_ingest holds the Reddit budget.

    Reddit's anonymous feed budget is per IP and is one request per window --
    `x-ratelimit-remaining` reads 0.0 after a single call, measured on the VPS
    2026-08-25. This script asks every 45 seconds and the daemon every 120, so
    run together they refuse each other, and the daemon's cycle then reports
    `missing` and writes no buckets at all. Nothing else coordinates them.

    systemctl only exists where the daemon is deployed. Anywhere else the
    answer is no, which is right: a dev machine is not sharing the budget.
    """
    import shutil
    import subprocess

    if shutil.which('systemctl') is None:
        return False
    result = subprocess.run(['systemctl', 'is-active', 'radar_ingest'],
                            capture_output=True, text=True)
    return result.stdout.strip() == 'active'
```

and in `main()`, immediately after parsing arguments:

```python
    if _daemon_is_running() and not args.anyway:
        print('radar_ingest is running and shares this IP\'s Reddit budget --\n'
              'one request per window, so the two will refuse each other and\n'
              'the daemon will write no buckets while this runs.\n\n'
              'Stop it first:  systemctl stop radar_ingest\n'
              'Or override:    --anyway', file=sys.stderr)
        return 1
```

Add the flag to the parser:

```python
    parser.add_argument('--anyway', action='store_true',
                        help='run even while radar_ingest holds the budget')
```

and make `main()`'s return value the process exit code:

```python
if __name__ == '__main__':
    sys.exit(main() or 0)
```

- [ ] **Step 2: Verify the guard is inert locally**

```bash
python -c "import sys; sys.path.insert(0,'.'); from scripts.discover_reddit_sources import _daemon_is_running; print(_daemon_is_running())"
```

Expected: `False` on Windows, where `systemctl` does not exist.

- [ ] **Step 3: Commit**

```bash
git add personal_apps/scripts/discover_reddit_sources.py
git commit -m "fix(radar): the discovery script no longer 429s the daemon it shares an IP with"
```

---


## Task 5: Delete the superseded `PAGE_CAP`

**Files:**
- Modify: `personal_apps/features/radar/config.py`
- Modify: `personal_apps/tests/test_radar_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: no new runtime names.

`PAGE_CAP` has zero references anywhere; `sources/fourchan.py` paginates under
its own `THREAD_CAP`. Delete the obsolete promise rather than preserving a
second page-cap vocabulary that no source implements.

Do not add the earlier draft's raw-source “reachability” test. It counted names
inside comments, docstrings and unused imports, so the exact
`single_letter_cashtags_allowed` defect could satisfy it without a runtime call.
The durable guards are behavioral and already live where the omissions
happened: ingest tests exercise the bot filter and Task 4's single-letter hook;
daemon tests assert the profile and sentiment jobs are scheduled.

- [ ] **Step 1: Pin the deliberate deletion**

Add to `test_radar_config.py`:

```python
def test_the_superseded_page_cap_is_gone():
    from features.radar import config

    assert not hasattr(config, 'PAGE_CAP')
```

Run it before deletion and confirm it fails because `PAGE_CAP` exists.

- [ ] **Step 2: Delete `PAGE_CAP`**

Remove the constant and its page-cap comment from `config.py`. Do not replace
it: Fourchan's `THREAD_CAP` is the live limit and owns its own truncation
status.

- [ ] **Step 3: Run the relevant behavioral guards**

```bash
python -m pytest tests/test_radar_config.py \
  tests/test_radar_ingest.py -k "bot_feed or single_letter or page_cap" -v
python -m pytest tests/test_radar_daemon.py \
  -k "schedules_a_profile_job or schedules_a_sentiment_job" -v
```

- [ ] **Step 4: Commit**

```bash
git add personal_apps/features/radar/config.py personal_apps/tests/test_radar_config.py
git commit -m "fix(radar): delete the superseded page-cap config"
```

---


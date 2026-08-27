## Task 15: Render the disagreement

**Files:**
- Modify: `personal_apps/features/radar/routes/api.py` (`serialize_detail`)
- Modify: `personal_apps/static/radar/src/types.ts`, `detail/Breakdown.tsx`
- Modify: `personal_apps/tests/test_radar_api.py`

**Interfaces:**
- Consumes: `Breakdown.disagreements` (Task 14).
- Produces: `breakdown.disagreements` in the detail payload.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_api.py`:

```python
def test_the_detail_payload_carries_the_sarcasm_signal():
    """Two sentiment scores are kept so their DISAGREEMENT can be read. Until
    now nothing compared them, which made the second one decoration.

    Asserted on the serializer rather than through a route, so it does not
    depend on which tickers the local database happens to hold.
    """
    import dataclasses

    from features.radar import detail_panel
    from features.radar.routes import api

    breakdown = detail_panel.Breakdown(
        venues=[], bullish=3, neutral=1, bearish=2, disagreements=2,
        top_author_share=None, top_two_share=None, peak_hour=None,
        peak_count=0, first_seen=None, mentions=6, voices=4)
    built = _stub_detail(breakdown)

    payload = api.serialize_detail(built)
    assert payload['breakdown']['disagreements'] == 2
```

`_stub_detail` builds the minimal `detail_panel.build` return the serializer
reads. If `test_radar_api.py` has no such helper, add one that constructs the
dataclass with the same field names `serialize_detail` touches — `ticker`,
`name`, `exchange`, `segment`, `market_cap`, `ipo_date`, `price`,
`price_move`, `price_status`, `session`, `mentions`, `expected`,
`baseline_days`, `chart`, `breakdown`, `posts`, `post_total`, `span` — reading
them off `detail_panel.py`'s own dataclass definitions.

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_radar_api.py::test_the_detail_payload_carries_the_sarcasm_signal -v
```

Expected: `KeyError: 'disagreements'`.

- [ ] **Step 3: Serialize it**

In `personal_apps/features/radar/routes/api.py`, inside `serialize_detail`'s `'breakdown'` dict:

```python
            'bearish': b.bearish,
            # How often the word list and the model read the same post the
            # opposite way. Both scores exist so this is answerable, and a
            # disagreement is the sarcasm the lexicon cannot see.
            'disagreements': b.disagreements,
```

- [ ] **Step 4: Render it**

In `personal_apps/static/radar/src/types.ts`, add `disagreements: number` to the breakdown type.

In `personal_apps/static/radar/src/detail/Breakdown.tsx`, beside the existing bullish/bearish wording, render it only when non-zero:

```tsx
      {b.disagreements > 0 && (
        <span className="wording">
          <b>{b.disagreements}</b> read differently by the model
        </span>
      )}
```

Follow the file's existing markup and class conventions. The tone bar's colours are unchanged — green and red stay reserved for price direction, as the file's own comment at line 20 already says.

- [ ] **Step 5: Run the tests and build**

```bash
python -m pytest tests/test_radar_api.py -v && npm run build
```

Expected: tests pass, build succeeds.

- [ ] **Step 6: Commit**

```bash
git add personal_apps/features/radar/routes/api.py personal_apps/static/radar/src personal_apps/tests/test_radar_api.py
git commit -m "feat(radar): show where the model and the word list disagree"
```

---


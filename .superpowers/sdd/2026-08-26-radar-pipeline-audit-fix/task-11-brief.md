## Task 11: An unpriced model does not cost nothing

**Files:**
- Modify: `personal_apps/features/radar/spend.py`
- Modify: `personal_apps/features/radar/routes/api.py` (`serialize`)
- Modify: `personal_apps/static/radar/src/types.ts`, `list/Spend.tsx`
- Modify: `personal_apps/tests/test_radar_spend.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `spend.cost_micros(model, input_tokens, output_tokens)` returns `int | None`. `spend.summary()` returns `{'today_usd', 'month_usd', 'unpriced_tokens'}` where `unpriced_tokens` is an int.

`cost_micros` returns `0` for a model with no rate, `record` adds that zero, and `summary()` reports only dollars — so the tokens that were meant to make the omission visible never surface. A model swap makes the bill read as free.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_spend.py`:

```python
def test_an_unpriced_model_costs_null_not_nothing():
    """Zero is a price. Not knowing the price is not one."""
    from features.radar import spend

    assert spend.cost_micros('claude-not-a-real-model', 1000, 100) is None
    assert spend.cost_micros('claude-haiku-4-5', 1_000_000, 0) == 1_000_000


def test_the_summary_surfaces_what_it_could_not_price(clean_spend):
    """The docstring's claim that 'the tokens are still recorded, so the
    omission is visible' was only true of the table. summary() returned
    dollars alone, so a model swap read as a free day on the board."""
    import datetime as dt

    from features.radar import spend

    day = dt.date(2026, 4, 15)
    spend.record('claude-haiku-4-5', calls=1, input_tokens=1_000_000,
                 output_tokens=0, day=day)
    spend.record('claude-unknown-9', calls=1, input_tokens=500_000,
                 output_tokens=1000, day=day)

    result = spend.summary(today=day)
    assert result['today_usd'] == 1.0
    assert result['unpriced_tokens'] == 501_000
```

Add a `clean_spend` fixture to that file if none exists, deleting `RadarLlmSpend` rows for `day=dt.date(2026, 4, 15)` before and after.

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_radar_spend.py -v -k "unpriced_model or surfaces_what"
```

Expected: `assert 0 is None`, then `KeyError: 'unpriced_tokens'`.

- [ ] **Step 3: Make the absence a NULL**

In `personal_apps/features/radar/spend.py`:

```python
def cost_micros(model, input_tokens, output_tokens):
    """Integer micro-dollars for this usage, or None at an unknown rate.

    None, not zero. Zero is a price -- it says the call was free -- and a model
    swap would then read as a free day on the board. The tokens are still
    recorded either way, and summary() reports the ones it could not price so
    the omission is visible where anyone looks.
    """
    rate = MODEL_RATES.get(model)
    if rate is None:
        return None
    per_in, per_out = rate
    return round((input_tokens * per_in + output_tokens * per_out)
                 * MICROS_PER_USD / 1_000_000)
```

In `record`, guard the accumulation:

```python
    cost = cost_micros(model, input_tokens, output_tokens)
    if cost is not None:
        # Added at the rate that applies NOW, so a later price change cannot
        # reach backwards into a day that was already paid for.
        row.cost_micros += cost
```

In `summary`, add the unpriced total:

```python
    def unpriced(since, until):
        """Tokens booked against a model with no rate on file.

        Read off the same rows: a model absent from MODEL_RATES contributed
        tokens and no cost, so its token totals are what is missing from the
        dollar figures above.
        """
        known = list(MODEL_RATES)
        total = db.session.query(
            sa.func.coalesce(
                sa.func.sum(RadarLlmSpend.input_tokens
                            + RadarLlmSpend.output_tokens), 0)).filter(
                RadarLlmSpend.day >= since,
                RadarLlmSpend.day <= until,
                RadarLlmSpend.model.notin_(known)).scalar()
        # int() at the boundary: SUM over BIGINT is Decimal on MySQL and
        # MariaDB alike, and Flask's JSON encoder raises on Decimal.
        return int(total or 0)

    return {
        'today_usd': _usd(total(today, today)),
        'month_usd': _usd(total(first, today)),
        # Never folded into the dollars. A token nobody could price is not
        # worth zero dollars; it is worth an unknown amount, and saying so is
        # the only honest option the board has.
        'unpriced_tokens': unpriced(first, today),
    }
```

- [ ] **Step 4: Surface it**

In `personal_apps/static/radar/src/types.ts`:

```ts
  spend?: { today_usd: number; month_usd: number; unpriced_tokens: number }
```

In `personal_apps/static/radar/src/list/Spend.tsx`, after the existing line, render the caveat only when it applies:

```tsx
      {spend.unpriced_tokens > 0 && (
        <span className="caveat">
          plus {spend.unpriced_tokens.toLocaleString()} tokens at an unknown
          rate
        </span>
      )}
```

Use whatever class the file already uses for secondary text — do not introduce a new colour, and do not use green or red.

- [ ] **Step 5: Run the tests and the frontend build**

```bash
python -m pytest tests/test_radar_spend.py tests/test_radar_api.py -v && npm run build
```

Expected: tests pass, build succeeds.

- [ ] **Step 6: Commit**

```bash
git add personal_apps/features/radar/spend.py personal_apps/features/radar/routes/api.py personal_apps/static/radar/src personal_apps/tests/test_radar_spend.py
git commit -m "fix(radar): an unpriced model reads as unknown, not as free"
```

---


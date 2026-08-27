## Task 14: The detail breakdown reads the model verdict

**Files:**
- Modify: `personal_apps/features/radar/detail_panel.py:118-170`
- Modify: `personal_apps/tests/test_radar_detail.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Breakdown` gains `disagreements: int` (Task 15 renders it; this task computes the verdict precedence only).

`board._tones` prefers the model verdict correctly and is serialized as `row.tone` — which no component renders. `detail/Breakdown.tsx` draws the one tone bar that exists, and it is fed by `detail_panel._breakdown`, which selects `lexicon_sentiment` and never joins `llm_sentiment`. So 11,789 paid-for verdicts reach no pixel.

- [ ] **Step 1: Write the failing test**

Append to `personal_apps/tests/test_radar_detail.py`:

```python
def test_the_breakdown_prefers_the_model_verdict_over_the_lexicon():
    """The one surface that draws a tone bar never read the verdicts.

    Production 2026-08-26: 11,789 of 11,794 scored mentions carried a model
    verdict, at $1.24 a day, and the panel rendered the forty-word lexicon.
    """
    from features.radar import detail_panel

    assert detail_panel._tone_of(lexicon=0.8, verdict='bearish') == 'bearish'
    assert detail_panel._tone_of(lexicon=0.8, verdict=None) == 'bullish'
    # `unclear` votes neither way AND blocks the lexicon: it means the post
    # named the ticker without saying anything about it, and that read is
    # better informed than the word list it overrides.
    assert detail_panel._tone_of(lexicon=0.8, verdict='unclear') is None
    assert detail_panel._tone_of(lexicon=None, verdict=None) is None
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python -m pytest tests/test_radar_detail.py::test_the_breakdown_prefers_the_model_verdict_over_the_lexicon -v
```

Expected: `AttributeError: module 'features.radar.detail_panel' has no attribute '_tone_of'`.

- [ ] **Step 3: Add the precedence and join the verdict**

In `personal_apps/features/radar/detail_panel.py`, above `_breakdown`:

```python
def _tone_of(lexicon, verdict):
    """'bullish', 'bearish' or None, from the two scores together.

    The model outranks the word list where both spoke. The lexicon is forty
    words with a negation window: it reads "great, another green day" after a
    crash as bullish, which is exactly the case spec 6.11 specified a re-read
    for.

    `unclear` votes neither way and BLOCKS the lexicon. It means the post named
    the ticker without expressing a view, and that read is better informed than
    the word list it overrides.

    A NULL verdict falls back to the lexicon rather than counting as toneless:
    verdicts arrive on a scheduled pass, so a fresh mention has none, and
    treating that as silence would make the newest posts look even-handed.
    """
    if verdict == 'bullish':
        return 'bullish'
    if verdict == 'bearish':
        return 'bearish'
    if verdict is not None:            # 'neutral' or 'unclear'
        return None
    if lexicon and lexicon > 0:
        return 'bullish'
    if lexicon and lexicon < 0:
        return 'bearish'
    return None
```

In `_breakdown`, select the verdict alongside the score and use the helper:

```python
    score = RadarMention.lexicon_sentiment
    verdict = RadarMention.llm_sentiment
    rows = (db.session.query(RadarPost.source, RadarPost.author,
                             RadarPost.channel, RadarPost.created_utc,
                             score, verdict)
            .join(RadarMention, RadarMention.post_id == RadarPost.id)
            .filter(...)                       # unchanged
            .all())
```

```python
    bullish = bearish = disagreements = 0

    for source, author, channel, when, sentiment, llm in rows:
        ...
        tone = _tone_of(sentiment, llm)
        if tone == 'bullish':
            bullish += 1
        elif tone == 'bearish':
            bearish += 1
        # A post the word list read one way and the model read the other is a
        # post that was being sarcastic. Both scores are kept precisely so this
        # comparison is possible; nothing performed it until now.
        lexicon_only = _tone_of(sentiment, None)
        if llm is not None and lexicon_only is not None and tone != lexicon_only:
            disagreements += 1
```

Add `disagreements: int` to the `Breakdown` dataclass and pass it in the return.

- [ ] **Step 4: Run it to verify it passes**

```bash
python -m pytest tests/test_radar_detail.py tests/test_radar_api.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add personal_apps/features/radar/detail_panel.py personal_apps/tests/test_radar_detail.py
git commit -m "fix(radar): the panel's tone bar reads the verdicts it has been paying for"
```

---


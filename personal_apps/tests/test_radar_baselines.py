# personal_apps/tests/test_radar_baselines.py
"""How loud a ticker normally is on one source.

The estimator divides by the observed MASS of the buckets it used, not by their
count. That is what makes dropping buckets safe: a dropped bucket removes its
share from the denominator too, so the rate stays unbiased no matter which ones
went missing. Every gap rule in the design rests on this one division.
"""
import datetime as dt

import pytest

from features.radar import baselines

MONDAY = dt.datetime(2026, 8, 17, 0, 0, 0)


def flat_profile():
    """Every bucket-of-week equally likely -- 1/672 each."""
    return {index: 1.0 / 672 for index in range(672)}


def obs(hours, count, status='ok', config_version='v1'):
    return baselines.Observation(
        bucket_start=MONDAY + dt.timedelta(hours=hours),
        count=count, status=status, config_version=config_version)


def test_a_flat_week_recovers_its_own_rate():
    """672 buckets of 1 mention each is 672 mentions a week."""
    observations = [obs(i * 0.25, 1) for i in range(672)]
    rate, mass = baselines.weekly_rate(observations, flat_profile())
    assert rate == pytest.approx(672.0)
    assert mass == pytest.approx(1.0)


def test_dropping_buckets_leaves_the_rate_unbiased():
    """The property the whole gap design rests on. Half the week is missing and
    the estimate is unchanged, because the denominator shrank with it."""
    full = [obs(i * 0.25, 1) for i in range(672)]
    half = full[::2]
    full_rate, _ = baselines.weekly_rate(full, flat_profile())
    half_rate, half_mass = baselines.weekly_rate(half, flat_profile())
    assert half_rate == pytest.approx(full_rate)
    assert half_mass == pytest.approx(0.5)


def test_dropping_a_busy_stretch_is_also_unbiased():
    """Bucket counts alone would be fooled here: the dropped buckets are the
    loud ones, so a count-based divisor would report the ticker as gone quiet."""
    prof = {index: (2.0 / 672 if index < 336 else 1.0 / 1008)
            for index in range(672)}
    total = sum(prof.values())
    prof = {k: v / total for k, v in prof.items()}

    everything = [obs(i * 0.25, 10 if i < 336 else 1) for i in range(672)]
    quiet_only = [o for i, o in enumerate(everything) if i >= 336]

    all_rate, _ = baselines.weekly_rate(everything, prof)
    quiet_rate, _ = baselines.weekly_rate(quiet_only, prof)
    assert quiet_rate == pytest.approx(all_rate, rel=0.15)


def test_missing_and_truncated_are_not_usable():
    observations = [obs(0, 5), obs(1, 0, status='missing'),
                    obs(2, 3, status='truncated')]
    assert [o.count for o in baselines.usable(observations, 'v1', set())] == [5]


def test_a_stale_config_version_is_not_usable():
    """Adding a source changes the population being measured, so history from
    before it describes something else (spec 6.6)."""
    observations = [obs(0, 5), obs(1, 9, config_version='v0')]
    assert [o.count for o in baselines.usable(observations, 'v1', set())] == [5]


def test_excluded_buckets_are_dropped():
    """The hook Plan 3 wires to open spikes: a ticker that squeezed last week
    must not carry an inflated mean into this week's baseline."""
    observations = [obs(0, 5), obs(1, 500)]
    excluded = {MONDAY + dt.timedelta(hours=1)}
    assert [o.count for o in baselines.usable(observations, 'v1', excluded)] == [5]


def test_no_usable_history_gives_a_zero_rate_and_zero_mass():
    rate, mass = baselines.weekly_rate([], flat_profile())
    assert rate == 0.0
    assert mass == 0.0


def test_a_prior_pulls_a_thin_estimate_towards_it():
    """Cold start. Two buckets of history should not be trusted on their own."""
    thin = [obs(0, 100), obs(1, 100)]
    alone, _ = baselines.weekly_rate(thin, flat_profile())
    shrunk, _ = baselines.weekly_rate(thin, flat_profile(),
                                      prior_rate=10.0, prior_weight=0.05)
    assert shrunk < alone
    assert shrunk > 10.0


def test_a_prior_barely_moves_a_thick_estimate():
    """Once there is real history, the prior should stop mattering."""
    thick = [obs(i * 0.25, 1) for i in range(672)]
    alone, _ = baselines.weekly_rate(thick, flat_profile())
    shrunk, _ = baselines.weekly_rate(thick, flat_profile(),
                                      prior_rate=10.0, prior_weight=0.05)
    assert shrunk == pytest.approx(alone, rel=0.1)

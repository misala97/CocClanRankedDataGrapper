# -*- coding: utf-8 -*-
"""Unit tests for features.admin.insights.curve — Study A.

The curve is the model B and D also depend on, so its edges matter more than
its happy path. Bucket merging never fires on current data (all 14 buckets
clear n=20), which is exactly why it is tested here: a rule that only runs
under conditions nobody has seen is the kind that ships broken.
"""

from features.admin.insights.curve import (
    DIFF_CLAMP,
    MIN_BUCKET_N,
    build_curve,
    clamp_diff,
)


def facts(src, diff, n, stars):
    """n attacks at one differential, all scoring `stars`."""
    return [{'src': src, 'attacker_th': 14, 'defender_th': 14 + diff,
             'stars': stars, 'destruction': 100.0, 'attacker_tag': f'#P{i}',
             'clan_tag': '#US', 'war_id': 1, 'ended_at': None,
             'attack_order': i} for i in range(n)]


def test_clamp_holds_ordinary_differentials_unchanged():
    assert clamp_diff(14, 15) == 1
    assert clamp_diff(14, 14) == 0
    assert clamp_diff(15, 13) == -2


def test_clamp_folds_the_long_tail():
    """The war tail runs to +7 on single attacks; those are not their own bucket."""
    assert clamp_diff(9, 16) == DIFF_CLAMP
    assert clamp_diff(16, 4) == -DIFF_CLAMP


def test_clamp_survives_missing_town_halls():
    assert clamp_diff(None, 14) == DIFF_CLAMP
    assert clamp_diff(14, None) == -DIFF_CLAMP


def test_bucket_reports_mean_stars_and_triple_rate():
    f = facts('war', 0, 20, 3) + facts('war', 0, 20, 1)
    c = build_curve(f)
    assert c[('war', 0)]['n'] == 40
    assert c[('war', 0)]['mean_stars'] == 2.0
    assert c[('war', 0)]['triple_rate'] == 0.5


def test_war_and_cwl_are_fitted_separately():
    """They are not the same game - 76.6% against 44.8% same-TH triples."""
    c = build_curve(facts('war', 0, 30, 3) + facts('cwl', 0, 30, 1))
    assert c[('war', 0)]['mean_stars'] == 3.0
    assert c[('cwl', 0)]['mean_stars'] == 1.0


def test_every_differential_is_present_for_every_source():
    c = build_curve(facts('war', 0, 30, 2))
    for d in range(-DIFF_CLAMP, DIFF_CLAMP + 1):
        assert ('war', d) in c, d


def test_a_thin_outer_bucket_merges_toward_zero():
    """+3 with too few attacks folds into +2, and both report the merged stats."""
    f = facts('war', 2, MIN_BUCKET_N, 2) + facts('war', 3, 4, 0)
    c = build_curve(f)
    assert c[('war', 3)]['merged'] is True
    assert c[('war', 3)] == c[('war', 2)]
    assert c[('war', 2)]['n'] == MIN_BUCKET_N + 4


def test_a_bucket_at_the_threshold_stands_alone():
    """Exactly MIN_BUCKET_N is enough - the boundary, not one past it."""
    f = facts('war', 2, MIN_BUCKET_N, 2) + facts('war', 3, MIN_BUCKET_N, 0)
    c = build_curve(f)
    assert c[('war', 3)]['merged'] is False
    assert c[('war', 3)]['n'] == MIN_BUCKET_N
    assert c[('war', 3)]['mean_stars'] == 0.0


def test_thin_buckets_cascade_all_the_way_to_zero():
    f = facts('war', 0, MIN_BUCKET_N, 3) + facts('war', 2, 2, 1) + facts('war', 3, 2, 1)
    c = build_curve(f)
    assert c[('war', 3)] == c[('war', 2)] == c[('war', 0)]
    assert c[('war', 0)]['n'] == MIN_BUCKET_N + 4


def test_an_empty_bucket_reports_no_expectation_rather_than_zero():
    """A differential nobody attacked at must not claim an expected 0.0 stars."""
    c = build_curve(facts('war', 0, 30, 3))
    assert c[('war', -3)]['n'] == 0
    assert c[('war', -3)]['mean_stars'] is None


def test_no_facts_yields_no_curve():
    assert build_curve([]) == {}


def test_a_self_sufficient_bucket_is_not_merged_by_an_empty_diff():
    """30 attacks at diff 0 alone: every other diff is empty, not thin, so
    diff 0 never borrows anything and must not be flagged merged."""
    c = build_curve(facts('war', 0, 30, 3))
    assert c[('war', 0)]['merged'] is False


def test_a_self_sufficient_inner_bucket_is_not_merged_by_an_empty_outer_diff():
    """Diff 2 stands five clear of MIN_BUCKET_N on its own; diff 3 is empty,
    not thin. Diff 2 must not report merged=True just because an empty label
    rode along the cascade."""
    f = facts('war', 2, 25, 2) + facts('war', 0, 25, 0)
    c = build_curve(f)
    assert c[('war', 2)]['merged'] is False
    assert c[('war', 2)]['n'] == 25


def test_a_genuinely_thin_bucket_still_merges():
    """Guard against over-correcting: diff -3 really is thin (6 attacks of
    its own, not zero) and must still fold into -2 and report merged=True."""
    f = facts('war', -2, 22, 1) + facts('war', -3, 6, 3)
    c = build_curve(f)
    assert c[('war', -3)]['merged'] is True
    assert c[('war', -3)] == c[('war', -2)]
    assert c[('war', -2)]['n'] == 28


def test_a_multi_diff_cascade_still_merges_into_centre():
    """Thin-but-real evidence on both flanks (+1 and -1) still pools into the
    centre bucket and reports merged=True, with n covering every contributor."""
    f = facts('war', 0, 15, 3) + facts('war', 1, 3, 1) + facts('war', -1, 2, 0)
    c = build_curve(f)
    assert c[('war', 0)]['merged'] is True
    assert c[('war', 1)] == c[('war', 0)] == c[('war', -1)]
    assert c[('war', 0)]['n'] == 20


def test_a_thin_arm_into_an_empty_centre_is_not_merged():
    """Diff 0 has no attacks of its own, so a lone thin +1 cascading through
    it pools with nothing. It must report merged=False, mirroring the same
    fix already applied to the arm loop: a label only counts as merged when
    it actually pooled with another diff's attacks."""
    c = build_curve(facts('war', 1, 3, 1))
    assert c[('war', 1)]['merged'] is False
    assert c[('war', 1)]['n'] == 3


def test_two_thin_arms_into_an_empty_centre_both_merge():
    """Diff 0 is empty but +1 and -1 both carry thin, real evidence: two
    diffs genuinely pooled together, so both report merged=True with
    identical stats."""
    f = facts('war', 1, 3, 1) + facts('war', -1, 2, 0)
    c = build_curve(f)
    assert c[('war', 1)]['merged'] is True
    assert c[('war', 1)] == c[('war', -1)]
    assert c[('war', 1)]['n'] == 5


def test_an_empty_centre_with_a_thin_arm_still_reports_no_expectation():
    """Diff 0 itself never had attacks: even though a neighbouring diff folds
    through it, diff 0's own bucket stays n=0/None rather than borrowing the
    pooled stats that ended up on the neighbour."""
    c = build_curve(facts('war', 1, 3, 1))
    assert c[('war', 0)]['n'] == 0
    assert c[('war', 0)]['mean_stars'] is None


def test_a_populated_centre_absorbs_thin_arms_on_both_sides():
    """Diff 0 has its own attacks and both +1/-1 are thin: all three keys
    pool together and report identical merged stats covering every
    contributor."""
    f = facts('war', 0, 10, 2) + facts('war', 1, 5, 3) + facts('war', -1, 4, 0)
    c = build_curve(f)
    assert c[('war', 0)]['merged'] is True
    assert c[('war', 0)] == c[('war', 1)] == c[('war', -1)]
    assert c[('war', 0)]['n'] == 19

"""Pure name matching for the shared-session confirm screen. No ORM here --
these are plain tuples, like the tests for stats.py."""


def test_normalise_ignores_case_and_padding():
    from features.gym import matching
    assert matching.normalise('  Bankdrücken ') == matching.normalise('bankdrücken')


def test_normalise_collapses_inner_whitespace():
    from features.gym import matching
    assert matching.normalise('KH  Bankdrücken') == matching.normalise('KH Bankdrücken')


def test_an_exact_name_is_matched_and_asks_nothing():
    """Both people call it Bankdrücken. There is nothing to confirm, and asking
    seven times per shared workout would make the common path the annoying one."""
    from features.gym import matching
    proposals = matching.propose_matches(
        ['Bankdrücken'], [(4, 'Bankdrücken'), (5, 'Kniebeuge')])
    assert proposals[0]['exact_id'] == 4


def test_an_exact_match_ignores_case_and_padding():
    from features.gym import matching
    proposals = matching.propose_matches(['Bankdrücken'], [(4, ' bankdrücken')])
    assert proposals[0]['exact_id'] == 4


def test_a_name_with_no_counterpart_has_no_exact_match():
    from features.gym import matching
    proposals = matching.propose_matches(['Bankdrücken'], [(5, 'Kniebeuge')])
    assert proposals[0]['exact_id'] is None


def test_substring_candidates_come_first():
    """Deliberately dull: containment either way, then alphabetical. Enough to
    float "KH Bankdrücken" to the top without pretending to understand German
    gym vocabulary."""
    from features.gym import matching
    proposals = matching.propose_matches(
        ['Bankdrücken'],
        [(1, 'Zug zum Kinn'), (2, 'KH Bankdrücken'), (3, 'Beinpresse')])
    assert proposals[0]['candidates'][0] == (2, 'KH Bankdrücken')


def test_candidates_after_the_substring_hits_are_alphabetical():
    from features.gym import matching
    proposals = matching.propose_matches(
        ['Bankdrücken'], [(1, 'Zug zum Kinn'), (3, 'Beinpresse')])
    assert [name for _, name in proposals[0]['candidates']] == [
        'Beinpresse', 'Zug zum Kinn']


def test_every_candidate_is_offered_even_when_an_exact_match_exists():
    """The follower may disagree with the exact match -- two people can use the
    same word for different machines. The dropdown still lists everything."""
    from features.gym import matching
    proposals = matching.propose_matches(
        ['Bankdrücken'], [(4, 'Bankdrücken'), (5, 'Kniebeuge')])
    assert len(proposals[0]['candidates']) == 2


def test_the_leader_name_is_returned_verbatim():
    """It is what a newly created exercise will be called, so it must not
    arrive normalised."""
    from features.gym import matching
    proposals = matching.propose_matches(['  KH Bankdrücken '], [])
    assert proposals[0]['name'] == '  KH Bankdrücken '


def test_an_empty_catalogue_proposes_nothing_and_does_not_crash():
    """The third lifter's first shared workout: she owns no exercises at all."""
    from features.gym import matching
    proposals = matching.propose_matches(['Bankdrücken'], [])
    assert proposals == [{'name': 'Bankdrücken', 'exact_id': None, 'candidates': []}]


def test_each_leader_name_is_ranked_against_itself():
    """A whole routine is matched in one call, so every name must rank against
    its OWN best candidate. The ranking closure captures the name being
    processed; if that capture were ever deferred past the loop, every
    proposal would silently rank against the LAST name instead -- and the
    result would still look plausible, which is what makes it worth pinning."""
    from features.gym import matching
    proposals = matching.propose_matches(
        ['Bankdrücken', 'Kniebeuge'],
        [(1, 'KH Bankdrücken'), (2, 'Kniebeugen'), (3, 'Rudern')])
    assert proposals[0]['candidates'][0] == (1, 'KH Bankdrücken')
    assert proposals[1]['candidates'][0] == (2, 'Kniebeugen')

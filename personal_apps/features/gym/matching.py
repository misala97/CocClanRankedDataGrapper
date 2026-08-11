"""Matching one lifter's exercise names against another's catalogue.

Exercises are per-user, so a shared workout has to be translated before it can
be carried across. This module decides what to propose; the follower decides
what is true. Pure functions over plain values -- no ORM, so the tests can pass
tuples.
"""


def normalise(name):
    """Casefolded and whitespace-collapsed, for comparison only.

    Never store this: a created exercise takes the name as typed.
    """
    return ' '.join((name or '').split()).casefold()


def propose_matches(leader_names, follower_catalogue):
    """What to show the follower for each of the leader's exercises.

    `follower_catalogue` is an iterable of (id, name) -- the follower's own
    exercises. Returns one dict per leader name, in the order given:

        {'name': str,            # the leader's name, VERBATIM
         'exact_id': int | None, # normalised-equal match, needs no question
         'candidates': [(id, name), ...]}  # best-first, always the full list

    Candidate order is deliberately dull: names that contain the leader's name
    (or are contained by it) first, then everything else alphabetically. Enough
    to float "KH Bankdruecken" to the top for "Bankdruecken" without pretending
    to understand German gym vocabulary -- and a wrong guess only costs a
    scroll, because the follower confirms.
    """
    catalogue = [(row_id, name) for row_id, name in follower_catalogue]

    proposals = []
    for leader_name in leader_names:
        target = normalise(leader_name)

        exact_id = None
        for row_id, name in catalogue:
            if normalise(name) == target:
                exact_id = row_id
                break

        def rank(row):
            name = normalise(row[1])
            related = target and (target in name or name in target)
            return (0 if related else 1, name)

        proposals.append({
            'name': leader_name,
            'exact_id': exact_id,
            'candidates': sorted(catalogue, key=rank),
        })
    return proposals

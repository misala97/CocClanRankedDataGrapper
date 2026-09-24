"""Barcode scanner: code rules, upstream normalizers, routes and access.

DB-free: logins are faked by monkeypatching `auth.current_user`, as
test_showoff.py does, and upstream HTTP is replaced by recorded fixtures.
"""
import pytest

from features.barcode import codes


def _with_check(body):
    """`body` plus the GS1 check digit that makes it a valid code."""
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return body + str((10 - total % 10) % 10)


# --- codes ------------------------------------------------------------------

@pytest.mark.parametrize('raw, expected', [
    ('4001686301265', '4001686301265'),      # EAN-13, Haribo Goldbären
    (' 4001686 301265 ', '4001686301265'),   # spaces from a hand-typed code
    ('978-3-423-28239-0', '9783423282390'),  # ISBN as printed on the back
    ('40111445', '40111445'),                # EAN-8
    ('036000291452', '0036000291452'),       # a UPC-A is the EAN-13 with a leading 0
])
def test_normalize_accepts_valid_codes(raw, expected):
    assert codes.normalize(raw) == expected


@pytest.mark.parametrize('raw', [
    '4001686301266',              # wrong check digit
    '40016863012',                # 11 digits
    '4001686301265x',             # letters
    '',
    None,
    '４００１６８６３０１２６５',  # full-width digits pass str.isdigit()
    '3423282395',                 # an ISBN-10 is not a barcode
])
def test_normalize_rejects(raw):
    with pytest.raises(codes.InvalidCode):
        codes.normalize(raw)


@pytest.mark.parametrize('code, kind', [
    ('9783423282390', 'book'),
    (_with_check('979100000000'), 'book'),
    ('4001686301265', 'product'),
    ('40111445', 'product'),
    (_with_check('200123400000'), 'instore'),  # weighed goods, own labels
    (_with_check('020123400000'), 'instore'),  # UPC number system 2
    (_with_check('040123400000'), 'instore'),
    (_with_check('2004723'), 'instore'),       # EAN-8 restricted circulation (Lidl, Aldi)
    (_with_check('0012345'), 'instore'),
])
def test_classify(code, kind):
    assert codes.classify(code) == kind


@pytest.mark.parametrize('code, label', [
    ('4001686301265', 'Deutschland'),
    (_with_check('400000000000'), 'Deutschland'),
    (_with_check('440000000000'), 'Deutschland'),
    (_with_check('441000000000'), None),
    ('40111445', 'Deutschland'),
    ('0036000291452', 'USA & Kanada'),
    (_with_check('900000000000'), 'Österreich'),
    (_with_check('977000000000'), 'ISSN (Zeitschrift)'),
    ('9783423282390', 'ISBN (Buch)'),
    (_with_check('140000000000'), None),
    (_with_check('200000000000'), 'Handelsinterne Nummer'),
    (_with_check('2004723'), 'Handelsinterne Nummer'),
])
def test_gs1_label(code, label):
    assert codes.gs1_label(code) == label

"""Barcode numbers: what counts as a product code, and what its prefix says.

Pure functions, no I/O. The lookup route and the tests share this one
definition; the page repeats only the check-digit rule, to skip a round trip
on a misread.
"""
import re

_SHAPE = re.compile(r'[0-9]{8}|[0-9]{12}|[0-9]{13}')

# GS1 member organisations by prefix. The prefix names the organisation that
# issued the number -- where the brand registered it -- not where the product
# was made. In-store ranges are answered by classify() before this table.
_PREFIXES = [
    (0, 19, 'USA & Kanada'), (30, 39, 'USA & Kanada'), (50, 59, 'Gutschein'),
    (60, 139, 'USA & Kanada'),
    (300, 379, 'Frankreich'), (380, 380, 'Bulgarien'), (383, 383, 'Slowenien'),
    (385, 385, 'Kroatien'), (387, 387, 'Bosnien und Herzegowina'), (389, 389, 'Montenegro'),
    (390, 390, 'Kosovo'),
    (400, 440, 'Deutschland'),
    (450, 459, 'Japan'), (460, 469, 'Russland'), (470, 470, 'Kirgisistan'),
    (471, 471, 'Taiwan'), (474, 474, 'Estland'), (475, 475, 'Lettland'),
    (476, 476, 'Aserbaidschan'), (477, 477, 'Litauen'), (478, 478, 'Usbekistan'),
    (479, 479, 'Sri Lanka'), (480, 480, 'Philippinen'), (481, 481, 'Belarus'),
    (482, 482, 'Ukraine'), (483, 483, 'Turkmenistan'), (484, 484, 'Moldau'),
    (485, 485, 'Armenien'), (486, 486, 'Georgien'), (487, 487, 'Kasachstan'),
    (488, 488, 'Tadschikistan'), (489, 489, 'Hongkong'), (490, 499, 'Japan'),
    (500, 509, 'Vereinigtes Königreich'), (520, 521, 'Griechenland'), (528, 528, 'Libanon'),
    (529, 529, 'Zypern'), (530, 530, 'Albanien'), (531, 531, 'Nordmazedonien'),
    (535, 535, 'Malta'), (539, 539, 'Irland'), (540, 549, 'Belgien & Luxemburg'),
    (560, 560, 'Portugal'), (569, 569, 'Island'), (570, 579, 'Dänemark'),
    (590, 590, 'Polen'), (594, 594, 'Rumänien'), (599, 599, 'Ungarn'),
    (600, 601, 'Südafrika'), (603, 603, 'Ghana'), (604, 604, 'Senegal'),
    (608, 608, 'Bahrain'), (609, 609, 'Mauritius'), (611, 611, 'Marokko'),
    (613, 613, 'Algerien'), (615, 615, 'Nigeria'), (616, 616, 'Kenia'),
    (618, 618, 'Elfenbeinküste'), (619, 619, 'Tunesien'), (620, 620, 'Tansania'),
    (621, 621, 'Syrien'), (622, 622, 'Ägypten'), (624, 624, 'Libyen'),
    (625, 625, 'Jordanien'), (626, 626, 'Iran'), (627, 627, 'Kuwait'),
    (628, 628, 'Saudi-Arabien'), (629, 629, 'Vereinigte Arabische Emirate'),
    (640, 649, 'Finnland'), (690, 699, 'China'), (700, 709, 'Norwegen'),
    (729, 729, 'Israel'), (730, 739, 'Schweden'), (740, 740, 'Guatemala'),
    (741, 741, 'El Salvador'), (742, 742, 'Honduras'), (743, 743, 'Nicaragua'),
    (744, 744, 'Costa Rica'), (745, 745, 'Panama'), (746, 746, 'Dominikanische Republik'),
    (750, 750, 'Mexiko'), (754, 755, 'Kanada'), (759, 759, 'Venezuela'),
    (760, 769, 'Schweiz & Liechtenstein'), (770, 771, 'Kolumbien'), (773, 773, 'Uruguay'),
    (775, 775, 'Peru'), (777, 777, 'Bolivien'), (778, 779, 'Argentinien'),
    (780, 780, 'Chile'), (784, 784, 'Paraguay'), (786, 786, 'Ecuador'),
    (789, 790, 'Brasilien'), (800, 839, 'Italien'), (840, 849, 'Spanien'),
    (850, 850, 'Kuba'), (858, 858, 'Slowakei'), (859, 859, 'Tschechien'),
    (860, 860, 'Serbien'), (865, 865, 'Mongolei'), (867, 867, 'Nordkorea'),
    (868, 869, 'Türkei'), (870, 879, 'Niederlande'), (880, 880, 'Südkorea'),
    (884, 884, 'Kambodscha'), (885, 885, 'Thailand'), (888, 888, 'Singapur'),
    (890, 890, 'Indien'), (893, 893, 'Vietnam'), (896, 896, 'Pakistan'),
    (899, 899, 'Indonesien'), (900, 919, 'Österreich'), (930, 939, 'Australien'),
    (940, 949, 'Neuseeland'), (950, 951, 'GS1 Global Office'), (955, 955, 'Malaysia'),
    (958, 958, 'Macau'), (960, 969, 'GS1 Global Office'),
    (977, 977, 'ISSN (Zeitschrift)'), (978, 979, 'ISBN (Buch)'),
    (980, 980, 'Rückgabebeleg'), (981, 984, 'Gutschein'), (990, 999, 'Gutschein'),
]


class InvalidCode(ValueError):
    """Not an EAN-8, UPC-A or EAN-13, or the check digit does not add up."""


def checksum_ok(code):
    """GS1 mod-10: weights 3, 1, 3, ... leftwards from the digit before the check digit."""
    body, check = code[:-1], int(code[-1])
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def normalize(raw):
    """The digits of an EAN-8 or EAN-13; a UPC-A comes back as the EAN-13 it is.

    `[0-9]`, not `str.isdigit()`: that accepts full-width digits and '²',
    which `int()` would then read as real ones.
    """
    code = re.sub(r'[\s-]', '', raw or '')
    if not _SHAPE.fullmatch(code) or not checksum_ok(code):
        raise InvalidCode(raw)
    return '0' + code if len(code) == 12 else code


def classify(code):
    """'book', 'instore' or 'product' for a normalized code.

    In-store numbers are still looked up: Lidl and Aldi print them on their
    own brands and Open Food Facts has many. The class only changes what the
    page says when nothing is found.
    """
    if len(code) == 8:
        return 'instore' if code[0] in '02' else 'product'
    prefix = int(code[:3])
    if prefix in (978, 979):
        return 'book'
    if 20 <= prefix <= 29 or 40 <= prefix <= 49 or 200 <= prefix <= 299:
        return 'instore'
    return 'product'


def gs1_label(code):
    """Who issued the number, in German, or None for an unassigned prefix."""
    if classify(code) == 'instore':
        return 'Handelsinterne Nummer'
    prefix = int(code[:3])
    for low, high, label in _PREFIXES:
        if low <= prefix <= high:
            return label
    return None

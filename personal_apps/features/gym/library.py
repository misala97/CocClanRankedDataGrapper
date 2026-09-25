"""The exercise library: one preconfigured list, the same for every lifter.

Static data, grown by editing this file: the app offers no "create exercise"
(owner, 2026-09-23 -- two lifters, one gym). Each entry has one read-only row
in gym_exercises, keyed by `key`, which exercises.ensure_library() keeps in
step with this file; a lifter's own settings sit on top, and the values here
are their defaults (features/gym/exercises.py). A first-time user finds their
exercise already set up -- every entry answers the questions the nine-field
form used to ask.

Every name reads `Bewegung (Gerät[, Variante, ...])`, e.g.
`Bankdrücken (Langhantel)` or `Latzug (Kabel, eng)`. The Gerät decides how
the exercise is loaded (_GERAET), so an entry states only what differs from
its Gerät's defaults. tests/test_gym_library.py holds the mechanical rules;
the judgement calls are these:

- `key` is stable. Once seeded it never changes: a rename changes the name.
- Entries sharing a Bewegung are variants of one movement, each with its own
  history: `Scottcurls (Maschine)` and `Scottcurls (Maschine, Scheiben)` are
  two machines. A second machine of the same kind at the gym is one more
  variant word here.
- `unilateral` means the logged number is ONE side's load -- one dumbbell,
  one stack of a crossover, one horn of an iso-lateral machine -- and volume
  doubles (stats.set_volume). The name does not decide it, "Maschine" least
  of all, so every plate-loaded machine states it.
- A machine found with both kinds of loading gets two entries: `(Maschine)`
  is a weight stack, `(Maschine, Scheiben)` is plate-loaded. Plate-loaded
  pressing and pulling machines are iso-lateral, so their number is per side;
  sleds (leg press, hack squat) are not.
- `increment`, `bar` and `rest` are defaults a lifter can override: an 8 kg
  stack, 2.5 kg dumbbell steps or a 7 kg SZ bar are gym facts no list can
  know.
- `bar` is dead weight already inside the logged number, as on
  models.Exercise.list_bar_weight. The Multipresse, T-Bar, Landmine and leg-press
  sled carry none: counterbalanced, resting on the floor or never counted,
  their number is the plates.
- `aka` feeds search, which finds an exercise by its English name as well as
  its German one: "chest fly" and "butterfly" both find the pec deck, and
  every name the lifters used before the list still finds its entry.
  matches() is that contract. An alias never repeats another entry's name or
  alias: the list's migration looks an old name up by it. What every variant
  of a movement is called goes in MOVEMENT_AKA instead, which only search
  reads.
- No bodyweight exercises: the app logs kg x reps, and the owner dropped
  them for now (2026-09-23).
"""
import re
from dataclasses import dataclass

HEAVY, COMPOUND, ISOLATION, CORE = 180, 150, 90, 60
REST_TIERS = (HEAVY, COMPOUND, ISOLATION, CORE)

# Gerät -> equipment, bar (kg inside the logged number), step, per side.
_GERAET = {
    'Langhantel':    ('plate_loaded', 20.0, 2.5, False),
    'SZ-Stange':     ('plate_loaded', 10.0, 2.5, False),
    'Trap-Bar':      ('plate_loaded', 25.0, 2.5, False),
    'Multipresse':   ('plate_loaded', None, 2.5, False),
    'T-Bar':         ('plate_loaded', None, 2.5, False),
    'Landmine':      ('plate_loaded', None, 2.5, False),
    'Beinpresse':    ('plate_loaded', None, 2.5, False),
    'Kurzhantel':    ('dumbbell', None, 2.0, True),
    'Kettlebell':    ('dumbbell', None, 4.0, False),
    'Kabel':         ('stack', None, 5.0, False),
    'Maschine':      ('stack', None, 5.0, False),
}
GERAETE = tuple(_GERAET)
ONE_SIDE_VARIANTS = ('einarmig', 'einbeinig')
_NAME = re.compile(r'^(?P<move>[^(),]+) \((?P<inside>[^()]+)\)$')


def parse_name(name):
    """(Bewegung, Gerät, [Variante, ...]) of a list name; ValueError if the
    name does not follow the pattern."""
    match = _NAME.match(name)
    if not match:
        raise ValueError(f'{name!r} does not read "Bewegung (Gerät[, Variante])"')
    geraet, *variants = (part.strip() for part in match['inside'].split(','))
    return match['move'], geraet, variants


@dataclass(frozen=True)
class Entry:
    key: str
    name: str
    group: str
    secondary: tuple
    equipment: str
    unilateral: bool
    increment: float
    bar: float | None
    rest: int
    aka: tuple

    @property
    def movement(self):
        return parse_name(self.name)[0]

    @property
    def geraet(self):
        return parse_name(self.name)[1]

    @property
    def label(self):
        """What sets it apart from the other variants of its movement: the
        inside of the brackets, `Kabel, einarmig`."""
        _, geraet, variants = parse_name(self.name)
        return ', '.join((geraet, *variants))

    @property
    def search_text(self):
        """The folded name, aliases and movement aliases, a line each: what
        find() looks in."""
        return fold_apart((self.name, *self.aka, *MOVEMENT_AKA.get(self.movement, ())))


def fold(text):
    """The search form of a name or a query: casefolded, ä/ae -> a (likewise
    ö and ü, and ß -> ss), punctuation to spaces. Typing "Bankdruecken",
    "bankdrucken" or "T Bar" finds what the list spells otherwise."""
    text = text.casefold()
    for pair, vowel in (('ae', 'a'), ('oe', 'o'), ('ue', 'u')):
        text = text.replace(pair, vowel)
    text = text.translate(_FOLD)
    return ' '.join(text.split())


_FOLD = str.maketrans({'ä': 'a', 'ö': 'o', 'ü': 'u', '-': ' ', ',': ' ',
                       '(': ' ', ')': ' ', '°': ' ', "'": ' '})


def fold_apart(parts):
    """`parts` folded one by one, a line each: a query's words may come from
    any of them, its whole phrase only from one (find's 'phrase' tier)."""
    return '\n'.join(fold(part) for part in parts)


#: A query word this long may be one typo off. A shorter one stays exact:
#: one edit is most of a four-letter word, and "bank" would find "dank".
#: Letters only: "31.07" one edit off is 01.07., 03.07., 13.07. and 31.08.
FUZZY_FROM = 5


def _may_be_a_typo(word):
    return len(word) >= FUZZY_FROM and word.isalpha()


def _has_words(search, words, typos=False):
    return all(word in search
               or (typos and _may_be_a_typo(word) and _one_edit_off(word, search))
               for word in words)


def matches(search, query, typos=False):
    """True when every word of the folded `query` occurs in `search`, a folded
    text -- Entry.search_text, or a page's own (a Verlauf workout's).

    Words may come from different aliases and in any order, and a fragment
    counts ("lat raise" finds Lateral Raise). With `typos`, a word of
    FUZZY_FROM letters or more may be one edit off ("Bankdrüken",
    "legpress"). A query that folds to nothing ("-") is no query and matches
    everything."""
    return _has_words(search, fold(query).split(), typos)


def find(texts, query):
    """(positions, tier): which of the folded `texts` answer `query`, and by
    which of three tiers -- the first that finds anything:

    - 'phrase': the whole query as one run. "Push 2" is the workout Push 2,
      not every Push of 2026, and "Bankdrücken Kurzhantel" that exercise, not
      a workout with Bankdrücken (Langhantel) and Seitheben (Kurzhantel). A
      text made of several things (a Verlauf workout: its name, its date, each
      exercise) separates them with a newline, which no folded query holds,
      so a run never spans two of them.
    - 'words': every word somewhere, in any order: "lat raise" finds Lateral
      Raise, "Push 23.09" the Push of that day.
    - 'typos': the same, with a word of FUZZY_FROM letters or more one edit
      off. Only as the fallback: "bench" one edit off is "rench", and French
      Press is no bench press.

    A query that folds to nothing is no query: every text, by 'words'.

    The one search (walkthrough G-145): the add sheet, Übungen and Verlauf all
    search with static/gym/src/search.ts, which mirrors this rule for rule;
    tests/test_gym_search_cases.py holds the two to the same answers."""
    phrase = fold(query)
    words = phrase.split()
    if not words:
        return list(range(len(texts))), 'words'
    hits = [i for i, text in enumerate(texts) if phrase in text]
    if hits:
        return hits, 'phrase'
    hits = [i for i, text in enumerate(texts) if _has_words(text, words)]
    if hits or not any(_may_be_a_typo(word) for word in words):
        return hits, 'words'
    return [i for i, text in enumerate(texts) if _has_words(text, words, typos=True)], 'typos'


def _one_edit_off(word, text):
    """Whether some stretch of `text` is at most one edit from `word`: a
    letter added, dropped or changed, or two neighbours swapped.

    Sellers' dynamic programme -- the edit distance with the match free to
    start anywhere in `text` -- with the swap of optimal string alignment.
    `above[j]` is the fewest edits that turn the word so far into a stretch
    of `text` ending at j. That minimum never falls from one letter of the
    word to the next, so past one edit the search stops."""
    before, above = None, [0] * (len(text) + 1)
    for i in range(1, len(word) + 1):
        row = [i] + [0] * len(text)
        for j in range(1, len(text) + 1):
            best = min(above[j] + 1, row[j - 1] + 1,
                       above[j - 1] + (word[i - 1] != text[j - 1]))
            if i > 1 and j > 1 and word[i - 1] == text[j - 2] and word[i - 2] == text[j - 1]:
                best = min(best, before[j - 2] + 1)
            row[j] = best
        if min(row) > 1:
            return False
        before, above = above, row
    return True


def _e(key, name, group, secondary=(), *, rest=ISOLATION, uni=None, aka=()):
    _, geraet, variants = parse_name(name)
    equipment, bar, increment, per_side = _GERAET[geraet]
    if geraet == 'Maschine' and 'Scheiben' in variants:
        equipment, increment = 'plate_loaded', 2.5
        if uni is None:
            raise ValueError(f'{name}: a plate-loaded machine must say whether it logs per side')
    if uni is None:
        uni = per_side or any(v in ONE_SIDE_VARIANTS for v in variants)
    return Entry(key, name, group, tuple(secondary), equipment, uni, increment, bar, rest, tuple(aka))


LIBRARY = (
    # -- Brust --------------------------------------------------------------
    _e('barbell_bench_press', 'Bankdrücken (Langhantel)', 'Brust', ('Trizeps', 'Schultern'),
       rest=HEAVY, aka=('Bench Press', 'Barbell Bench Press', 'Flachbankdrücken')),
    _e('barbell_incline_bench_press', 'Schrägbankdrücken (Langhantel)', 'Brust', ('Schultern', 'Trizeps'),
       rest=HEAVY, aka=('Incline Bench Press', 'Barbell Incline Press')),
    _e('barbell_decline_bench_press', 'Negativbankdrücken (Langhantel)', 'Brust', ('Trizeps',),
       rest=HEAVY, aka=('Decline Bench Press',)),
    _e('barbell_floor_press', 'Floor Press (Langhantel)', 'Brust', ('Trizeps',),
       rest=COMPOUND, aka=('Bodendrücken',)),
    _e('dumbbell_bench_press', 'Bankdrücken (Kurzhantel)', 'Brust', ('Trizeps', 'Schultern'),
       rest=COMPOUND, aka=('Dumbbell Bench Press', 'Bench Press (Dumbbell)', 'Kurzhanteldrücken', 'KH Bankdrücken')),
    _e('dumbbell_incline_bench_press', 'Schrägbankdrücken (Kurzhantel)', 'Brust', ('Schultern', 'Trizeps'),
       rest=COMPOUND, aka=('Incline Dumbbell Press', 'KH Schrägbankdrücken')),
    _e('dumbbell_decline_bench_press', 'Negativbankdrücken (Kurzhantel)', 'Brust', ('Trizeps',),
       rest=COMPOUND, aka=('Decline Dumbbell Press',)),
    _e('dumbbell_fly', 'Fliegende (Kurzhantel)', 'Brust', ('Schultern',),
       aka=('Dumbbell Fly', 'Flys', 'Kurzhantel-Fliegende')),
    _e('dumbbell_incline_fly', 'Fliegende (Kurzhantel, schräg)', 'Brust', ('Schultern',),
       aka=('Incline Dumbbell Fly',)),
    _e('dumbbell_pullover', 'Überzüge (Kurzhantel)', 'Brust', ('Rücken', 'Trizeps'),
       uni=False, aka=('Dumbbell Pullover', 'Pullover')),
    _e('smith_bench_press', 'Bankdrücken (Multipresse)', 'Brust', ('Trizeps', 'Schultern'),
       rest=COMPOUND, aka=('Smith Machine Bench Press',)),
    _e('smith_incline_bench_press', 'Schrägbankdrücken (Multipresse)', 'Brust', ('Schultern', 'Trizeps'),
       rest=COMPOUND, aka=('Smith Machine Incline Press',)),
    _e('smith_decline_bench_press', 'Negativbankdrücken (Multipresse)', 'Brust', ('Trizeps',),
       rest=COMPOUND, aka=('Smith Machine Decline Press',)),
    _e('cable_fly', 'Fliegende (Kabel)', 'Brust', ('Schultern',),
       uni=True, aka=('Cable Fly', 'Cable Crossover', 'Kabelzug über Kreuz', 'Kabelziehen')),
    _e('cable_fly_high_to_low', 'Fliegende (Kabel, von oben)', 'Brust',
       uni=True, aka=('High to Low Cable Fly',)),
    _e('cable_fly_low_to_high', 'Fliegende (Kabel, von unten)', 'Brust', ('Schultern',),
       uni=True, aka=('Low to High Cable Fly',)),
    _e('machine_chest_press', 'Brustpresse (Maschine)', 'Brust', ('Trizeps', 'Schultern'),
       rest=COMPOUND, aka=('Chest Press', 'Chest Press (Machine)')),
    _e('machine_incline_chest_press', 'Brustpresse (Maschine, schräg)', 'Brust', ('Schultern', 'Trizeps'),
       rest=COMPOUND, aka=('Incline Chest Press (Machine)',)),
    _e('machine_fly', 'Butterfly (Maschine)', 'Brust',
       aka=('Pec Deck', 'Chest Fly (Machine)', 'Butterflymaschine')),
    _e('plate_chest_press', 'Brustpresse (Maschine, Scheiben)', 'Brust', ('Trizeps', 'Schultern'),
       rest=COMPOUND, uni=True, aka=('Iso-Lateral Chest Press', 'Chest Press (Plate Loaded)')),
    _e('plate_bench_press', 'Bankdrücken (Maschine, Scheiben)', 'Brust', ('Trizeps', 'Schultern'),
       rest=COMPOUND, uni=True, aka=('Iso-Lateral Bench Press', 'Lying Chest Press', 'Chest Press (Machine, Lying)',
            'Brustpresse liegend')),
    _e('plate_incline_chest_press', 'Schrägbankdrücken (Maschine, Scheiben)', 'Brust', ('Schultern', 'Trizeps'),
       rest=COMPOUND, uni=True, aka=('Iso-Lateral Incline Press',)),
    _e('plate_decline_chest_press', 'Negativbankdrücken (Maschine, Scheiben)', 'Brust', ('Trizeps',),
       rest=COMPOUND, uni=True, aka=('Iso-Lateral Decline Press',)),

    # -- Rücken -------------------------------------------------------------
    _e('barbell_deadlift', 'Kreuzheben (Langhantel)', 'Rücken', ('Beine', 'Gesäß', 'Unterarme'),
       rest=HEAVY, aka=('Deadlift', 'Conventional Deadlift')),
    _e('barbell_rack_pull', 'Rack Pulls (Langhantel)', 'Rücken', ('Gesäß', 'Unterarme'),
       rest=HEAVY, aka=('Rack Pull', 'Teilkreuzheben')),
    _e('barbell_row', 'Rudern (Langhantel)', 'Rücken', ('Bizeps', 'Schultern'),
       rest=COMPOUND, aka=('Barbell Row', 'Bent Over Row', 'Langhantelrudern', 'Vorgebeugtes Rudern')),
    _e('barbell_row_underhand', 'Rudern (Langhantel, Untergriff)', 'Rücken', ('Bizeps',),
       rest=COMPOUND, aka=('Underhand Barbell Row', 'Yates Row')),
    _e('barbell_pendlay_row', 'Rudern (Langhantel, Pendlay)', 'Rücken', ('Bizeps', 'Schultern'),
       rest=COMPOUND, aka=('Pendlay Row',)),
    _e('barbell_shrug', 'Shrugs (Langhantel)', 'Rücken', ('Unterarme',),
       aka=('Barbell Shrug', 'Schulterheben')),
    _e('dumbbell_row', 'Rudern (Kurzhantel)', 'Rücken', ('Bizeps', 'Schultern'),
       rest=COMPOUND, aka=('Dumbbell Row', 'Bent Over Dumbbell Row')),
    _e('dumbbell_row_one_arm', 'Rudern (Kurzhantel, einarmig)', 'Rücken', ('Bizeps',),
       rest=COMPOUND, aka=('One Arm Dumbbell Row', 'Kurzhantelrudern')),
    _e('dumbbell_row_chest_supported', 'Rudern (Kurzhantel, brustgestützt)', 'Rücken', ('Bizeps', 'Schultern'),
       rest=COMPOUND, aka=('Chest Supported Dumbbell Row', 'Incline Dumbbell Row', 'Seal Row')),
    _e('dumbbell_shrug', 'Shrugs (Kurzhantel)', 'Rücken', ('Unterarme',),
       aka=('Dumbbell Shrug',)),
    _e('smith_row', 'Rudern (Multipresse)', 'Rücken', ('Bizeps', 'Schultern'),
       rest=COMPOUND, aka=('Smith Machine Row',)),
    _e('smith_shrug', 'Shrugs (Multipresse)', 'Rücken',
       aka=('Smith Machine Shrug',)),
    _e('trap_bar_shrug', 'Shrugs (Trap-Bar)', 'Rücken', ('Unterarme',),
       aka=('Trap Bar Shrug',)),
    _e('tbar_row', 'Rudern (T-Bar, stehend)', 'Rücken', ('Bizeps', 'Schultern'),
       rest=COMPOUND, aka=('T-Bar Row', 'T Bar Row (Standing)', 'T-Bar-Rudern')),
    _e('tbar_row_chest_supported', 'Rudern (T-Bar, liegend)', 'Rücken', ('Bizeps', 'Schultern'),
       rest=COMPOUND, aka=('Chest Supported T-Bar Row', 'T Bar Row (Lying)', 'T-Bar-Rudern liegend')),
    _e('cable_lat_pulldown', 'Latzug (Kabel)', 'Rücken', ('Bizeps',),
       rest=COMPOUND, aka=('Lat Pulldown', 'Lat Pulldown (Kabelzug)', 'Latziehen', 'Latzug breit')),
    _e('cable_lat_pulldown_close', 'Latzug (Kabel, eng)', 'Rücken', ('Bizeps',),
       rest=COMPOUND, aka=('Close Grip Lat Pulldown', 'Latzug V-Griff')),
    _e('cable_lat_pulldown_underhand', 'Latzug (Kabel, Untergriff)', 'Rücken', ('Bizeps',),
       rest=COMPOUND, aka=('Reverse Grip Lat Pulldown',)),
    _e('cable_lat_pulldown_one_arm', 'Latzug (Kabel, einarmig)', 'Rücken', ('Bizeps',),
       aka=('Single Arm Lat Pulldown',)),
    _e('cable_row', 'Rudern (Kabel)', 'Rücken', ('Bizeps', 'Schultern'),
       rest=COMPOUND, aka=('Seated Cable Row', 'Kabelrudern', 'Rudern sitzend')),
    _e('cable_row_wide', 'Rudern (Kabel, breit)', 'Rücken', ('Schultern', 'Bizeps'),
       rest=COMPOUND, aka=('Wide Grip Cable Row',)),
    _e('cable_row_one_arm', 'Rudern (Kabel, einarmig)', 'Rücken', ('Bizeps',),
       aka=('Single Arm Cable Row',)),
    _e('cable_straight_arm_pulldown', 'Überzüge (Kabel)', 'Rücken', ('Trizeps',),
       aka=('Straight Arm Pulldown', 'Lat Pullover', 'Pullover am Kabel')),
    _e('machine_lat_pulldown', 'Latzug (Maschine)', 'Rücken', ('Bizeps',),
       rest=COMPOUND, aka=('Lat Pulldown (Machine)',)),
    _e('machine_row', 'Rudern (Maschine)', 'Rücken', ('Bizeps', 'Schultern'),
       rest=COMPOUND, aka=('Seated Row (Machine)', 'Row Machine', 'Rudermaschine')),
    _e('machine_back_extension', 'Rückenstrecker (Maschine)', 'Rücken', ('Gesäß',),
       aka=('Back Extension (Machine)', 'Lower Back Machine')),
    _e('plate_lat_pulldown', 'Latzug (Maschine, Scheiben)', 'Rücken', ('Bizeps',),
       rest=COMPOUND, uni=True, aka=('Iso-Lateral Lat Pulldown', 'Lat Pulldown (Plate Loaded)',
            'Lat Pulldown (Single Arm)')),
    _e('plate_row', 'Rudern (Maschine, Scheiben)', 'Rücken', ('Bizeps', 'Schultern'),
       rest=COMPOUND, uni=True, aka=('Iso-Lateral Row', 'Low Row')),
    _e('plate_high_row', 'High Row (Maschine, Scheiben)', 'Rücken', ('Bizeps',),
       rest=COMPOUND, uni=True, aka=('Iso-Lateral High Row', 'Rudern von oben')),

    # -- Schultern ----------------------------------------------------------
    _e('barbell_overhead_press', 'Schulterdrücken (Langhantel, stehend)', 'Schultern', ('Trizeps',),
       rest=HEAVY, aka=('Military Press', 'Overhead Press', 'OHP', 'Überkopfdrücken')),
    _e('barbell_overhead_press_seated', 'Schulterdrücken (Langhantel, sitzend)', 'Schultern', ('Trizeps',),
       rest=COMPOUND, aka=('Seated Barbell Press', 'Seated Military Press')),
    _e('barbell_upright_row', 'Aufrechtes Rudern (Langhantel)', 'Schultern', ('Rücken',),
       aka=('Upright Row', 'Barbell Upright Row')),
    _e('ez_upright_row', 'Aufrechtes Rudern (SZ-Stange)', 'Schultern', ('Rücken',),
       aka=('EZ Bar Upright Row',)),
    _e('dumbbell_shoulder_press', 'Schulterdrücken (Kurzhantel, sitzend)', 'Schultern', ('Trizeps',),
       rest=COMPOUND, aka=('Dumbbell Shoulder Press', 'Seated Dumbbell Press')),
    _e('dumbbell_shoulder_press_standing', 'Schulterdrücken (Kurzhantel, stehend)', 'Schultern', ('Trizeps',),
       rest=COMPOUND, aka=('Standing Dumbbell Press',)),
    _e('arnold_press', 'Arnold Press (Kurzhantel)', 'Schultern', ('Trizeps',),
       rest=COMPOUND, aka=('Arnold-Drücken',)),
    _e('dumbbell_lateral_raise', 'Seitheben (Kurzhantel)', 'Schultern',
       aka=('Lateral Raise', 'Dumbbell Lateral Raise', 'Seitenheben')),
    _e('dumbbell_front_raise', 'Frontheben (Kurzhantel)', 'Schultern',
       aka=('Front Raise', 'Dumbbell Front Raise')),
    _e('dumbbell_rear_delt_fly', 'Vorgebeugtes Seitheben (Kurzhantel)', 'Schultern', ('Rücken',),
       aka=('Rear Delt Fly', 'Reverse Fly (Dumbbell)', 'Reverse Flys')),
    _e('smith_shoulder_press', 'Schulterdrücken (Multipresse)', 'Schultern', ('Trizeps',),
       rest=COMPOUND, aka=('Smith Machine Shoulder Press',)),
    _e('landmine_press', 'Schulterdrücken (Landmine, einarmig)', 'Schultern', ('Brust', 'Trizeps'),
       rest=COMPOUND, aka=('Landmine Press',)),
    _e('cable_lateral_raise', 'Seitheben (Kabel, einarmig)', 'Schultern',
       aka=('Cable Lateral Raise',)),
    _e('cable_front_raise', 'Frontheben (Kabel)', 'Schultern',
       aka=('Cable Front Raise',)),
    _e('cable_front_raise_one_arm', 'Frontheben (Kabel, einarmig)', 'Schultern',
       aka=('Single Arm Cable Front Raise', 'Front Raises (Cable, One Arm)')),
    _e('cable_face_pull', 'Face Pulls (Kabel)', 'Schultern', ('Rücken',),
       aka=('Face Pull',)),
    _e('cable_rear_delt_fly', 'Reverse Butterfly (Kabel)', 'Schultern', ('Rücken',),
       uni=True, aka=('Cable Reverse Fly', 'Rear Delt Cable Fly')),
    _e('cable_upright_row', 'Aufrechtes Rudern (Kabel)', 'Schultern', ('Rücken',),
       aka=('Cable Upright Row',)),
    _e('cable_external_rotation', 'Außenrotation (Kabel)', 'Schultern',
       uni=True, aka=('External Rotation', 'Rotatorenmanschette')),
    _e('machine_shoulder_press', 'Schulterpresse (Maschine)', 'Schultern', ('Trizeps',),
       rest=COMPOUND, aka=('Shoulder Press (Machine)', 'Shoulder Press')),
    _e('machine_lateral_raise', 'Seitheben (Maschine)', 'Schultern',
       aka=('Lateral Raise (Machine)', 'Seitheben-Maschine')),
    _e('machine_rear_delt_fly', 'Reverse Butterfly (Maschine)', 'Schultern', ('Rücken',),
       aka=('Reverse Fly (Machine)', 'Rear Delt Machine', 'Butterfly reverse')),
    _e('plate_shoulder_press', 'Schulterpresse (Maschine, Scheiben)', 'Schultern', ('Trizeps',),
       rest=COMPOUND, uni=True, aka=('Iso-Lateral Shoulder Press',)),
    _e('plate_lateral_raise', 'Seitheben (Maschine, Scheiben)', 'Schultern',
       uni=True, aka=('Lateral Raise (Plate Loaded)', 'Iso-Lateral Lateral Raise')),

    # -- Bizeps -------------------------------------------------------------
    _e('barbell_curl', 'Bizepscurls (Langhantel)', 'Bizeps', ('Unterarme',),
       aka=('Barbell Curl', 'Langhantelcurls')),
    _e('ez_curl', 'Bizepscurls (SZ-Stange)', 'Bizeps', ('Unterarme',),
       aka=('EZ Bar Curl', 'SZ-Curls')),
    _e('ez_preacher_curl', 'Scottcurls (SZ-Stange)', 'Bizeps',
       aka=('Preacher Curl', 'Preacher Curl (EZ Bar)', 'Scott-Curls')),
    _e('dumbbell_curl', 'Bizepscurls (Kurzhantel)', 'Bizeps', ('Unterarme',),
       aka=('Dumbbell Curl', 'Biceps Curl', 'Biceps Curl (Rotating)', 'Kurzhantelcurls')),
    _e('dumbbell_hammer_curl', 'Hammercurls (Kurzhantel)', 'Bizeps', ('Unterarme',),
       aka=('Hammer Curl', 'Hammer Curl (Dumbbell)')),
    _e('dumbbell_concentration_curl', 'Konzentrationscurls (Kurzhantel)', 'Bizeps',
       aka=('Concentration Curl',)),
    _e('dumbbell_incline_curl', 'Schrägbankcurls (Kurzhantel)', 'Bizeps',
       aka=('Incline Dumbbell Curl',)),
    _e('dumbbell_preacher_curl', 'Scottcurls (Kurzhantel)', 'Bizeps',
       aka=('Dumbbell Preacher Curl',)),
    _e('cable_curl', 'Bizepscurls (Kabel)', 'Bizeps', ('Unterarme',),
       aka=('Cable Curl', 'Kabelcurls', 'Bizeps SZ Kabel')),
    _e('cable_curl_one_arm', 'Bizepscurls (Kabel, einarmig)', 'Bizeps',
       aka=('Single Arm Cable Curl',)),
    _e('cable_hammer_curl', 'Hammercurls (Kabel, Seil)', 'Bizeps', ('Unterarme',),
       aka=('Cable Hammer Curl', 'Rope Hammer Curl')),
    _e('cable_bayesian_curl', 'Bayesian Curls (Kabel)', 'Bizeps',
       uni=True, aka=('Bayesian Curl',)),
    _e('machine_preacher_curl', 'Scottcurls (Maschine)', 'Bizeps',
       aka=('Preacher Curl (Machine)', 'Preacher Curl (Bilateral)', 'Bizepsmaschine',
            'Bizeps-Curl-Maschine')),
    _e('plate_preacher_curl', 'Scottcurls (Maschine, Scheiben)', 'Bizeps',
       uni=True, aka=('Preacher Curl (Machine, Plate Loaded)', 'Iso-Lateral Preacher Curl')),

    # -- Trizeps ------------------------------------------------------------
    _e('barbell_close_grip_bench_press', 'Bankdrücken (Langhantel, eng)', 'Trizeps', ('Brust', 'Schultern'),
       rest=COMPOUND, aka=('Close Grip Bench Press', 'Enges Bankdrücken')),
    _e('ez_skull_crusher', 'French Press (SZ-Stange)', 'Trizeps',
       aka=('Skull Crusher', 'Stirndrücken', 'Lying Triceps Extension')),
    _e('dumbbell_skull_crusher', 'French Press (Kurzhantel)', 'Trizeps',
       aka=('Dumbbell Skull Crusher',)),
    _e('dumbbell_overhead_extension', 'Trizepsstrecken über Kopf (Kurzhantel)', 'Trizeps',
       uni=False, aka=('Overhead Triceps Extension (Dumbbell)',)),
    _e('dumbbell_overhead_extension_one_arm', 'Trizepsstrecken über Kopf (Kurzhantel, einarmig)', 'Trizeps',
       aka=('Single Arm Overhead Extension',)),
    _e('ez_overhead_extension', 'Trizepsstrecken über Kopf (SZ-Stange)', 'Trizeps',
       aka=('EZ Bar Overhead Extension',)),
    _e('dumbbell_triceps_kickback', 'Trizeps-Kickbacks (Kurzhantel)', 'Trizeps',
       aka=('Triceps Kickback',)),
    _e('cable_pushdown', 'Trizepsdrücken (Kabel, Stange)', 'Trizeps',
       aka=('Triceps Pushdown', 'Triceps Pushdown (Cable, EZ Bar)', 'Pushdown',
            'Trizepsdrücken am Kabel', 'Trizepsdrücken V-Griff')),
    _e('cable_pushdown_rope', 'Trizepsdrücken (Kabel, Seil)', 'Trizeps',
       aka=('Rope Pushdown',)),
    _e('cable_pushdown_reverse', 'Trizepsdrücken (Kabel, Untergriff)', 'Trizeps',
       aka=('Reverse Grip Pushdown',)),
    _e('cable_pushdown_one_arm', 'Trizepsdrücken (Kabel, einarmig)', 'Trizeps',
       aka=('Single Arm Pushdown',)),
    _e('cable_overhead_extension', 'Trizepsstrecken über Kopf (Kabel)', 'Trizeps',
       aka=('Overhead Cable Extension', 'Overhead Triceps Extension (Cable)')),
    _e('cable_triceps_kickback', 'Trizeps-Kickbacks (Kabel)', 'Trizeps',
       uni=True, aka=('Cable Triceps Kickback',)),
    _e('machine_dip', 'Dips (Maschine)', 'Trizeps', ('Brust',),
       rest=COMPOUND, aka=('Dip Machine', 'Seated Dip')),
    _e('machine_triceps_extension', 'Trizepsstrecken (Maschine)', 'Trizeps',
       aka=('Triceps Extension (Machine)', 'Trizepsmaschine')),

    # -- Beine --------------------------------------------------------------
    _e('barbell_squat', 'Kniebeugen (Langhantel)', 'Beine', ('Gesäß', 'Rücken'),
       rest=HEAVY, aka=('Squat', 'Back Squat', 'Kniebeuge')),
    _e('barbell_front_squat', 'Frontkniebeugen (Langhantel)', 'Beine', ('Gesäß', 'Bauch'),
       rest=HEAVY, aka=('Front Squat',)),
    _e('barbell_lunge', 'Ausfallschritte (Langhantel)', 'Beine', ('Gesäß',),
       rest=COMPOUND, aka=('Barbell Lunge',)),
    _e('barbell_romanian_deadlift', 'Rumänisches Kreuzheben (Langhantel)', 'Beine', ('Gesäß', 'Rücken'),
       rest=COMPOUND, aka=('Romanian Deadlift', 'RDL')),
    _e('barbell_stiff_leg_deadlift', 'Kreuzheben (Langhantel, gestreckte Beine)', 'Beine', ('Gesäß', 'Rücken'),
       rest=COMPOUND, aka=('Stiff Leg Deadlift', 'Steifbeiniges Kreuzheben')),
    _e('barbell_sumo_deadlift', 'Kreuzheben (Langhantel, Sumo)', 'Beine', ('Gesäß', 'Rücken'),
       rest=HEAVY, aka=('Sumo Deadlift',)),
    _e('barbell_good_morning', 'Good Mornings (Langhantel)', 'Beine', ('Rücken', 'Gesäß'),
       rest=COMPOUND, aka=('Good Morning',)),
    _e('trap_bar_deadlift', 'Kreuzheben (Trap-Bar)', 'Beine', ('Gesäß', 'Rücken'),
       rest=HEAVY, aka=('Trap Bar Deadlift', 'Hex Bar Deadlift', 'Hexbar')),
    _e('dumbbell_goblet_squat', 'Goblet Squat (Kurzhantel)', 'Beine', ('Gesäß',),
       rest=COMPOUND, uni=False, aka=('Goblet Squat', 'Goblet-Kniebeuge')),
    _e('kettlebell_goblet_squat', 'Goblet Squat (Kettlebell)', 'Beine', ('Gesäß',),
       rest=COMPOUND, aka=('Kettlebell Goblet Squat',)),
    _e('dumbbell_sumo_squat', 'Kniebeugen (Kurzhantel, Sumo)', 'Beine', ('Gesäß',),
       rest=COMPOUND, uni=False, aka=('Sumo Squat', 'Sumo-Kniebeuge')),
    _e('dumbbell_lunge', 'Ausfallschritte (Kurzhantel)', 'Beine', ('Gesäß',),
       rest=COMPOUND, aka=('Dumbbell Lunge', 'Lunges')),
    _e('dumbbell_bulgarian_split_squat', 'Bulgarische Kniebeugen (Kurzhantel)', 'Beine', ('Gesäß',),
       rest=COMPOUND, aka=('Bulgarian Split Squat', 'Split Squat')),
    _e('dumbbell_step_up', 'Step-ups (Kurzhantel)', 'Beine', ('Gesäß',),
       rest=COMPOUND, aka=('Step Up', 'Aufsteiger')),
    _e('dumbbell_romanian_deadlift', 'Rumänisches Kreuzheben (Kurzhantel)', 'Beine', ('Gesäß', 'Rücken'),
       rest=COMPOUND, aka=('Dumbbell Romanian Deadlift', 'Dumbbell RDL')),
    _e('dumbbell_single_leg_rdl', 'Rumänisches Kreuzheben (Kurzhantel, einbeinig)', 'Beine', ('Gesäß',),
       rest=COMPOUND, aka=('Single Leg RDL',)),
    _e('smith_squat', 'Kniebeugen (Multipresse)', 'Beine', ('Gesäß',),
       rest=COMPOUND, aka=('Smith Machine Squat',)),
    _e('smith_split_squat', 'Bulgarische Kniebeugen (Multipresse)', 'Beine', ('Gesäß',),
       rest=COMPOUND, aka=('Smith Machine Split Squat',)),
    _e('machine_leg_extension', 'Beinstrecker (Maschine)', 'Beine',
       aka=('Leg Extension', 'Beinstrecken')),
    _e('machine_leg_curl_seated', 'Beinbeuger (Maschine, sitzend)', 'Beine',
       aka=('Seated Leg Curl',)),
    _e('machine_leg_curl_lying', 'Beinbeuger (Maschine, liegend)', 'Beine',
       aka=('Lying Leg Curl',)),
    _e('machine_leg_curl_standing', 'Beinbeuger (Maschine, stehend)', 'Beine',
       uni=True, aka=('Standing Leg Curl',)),
    _e('machine_leg_press', 'Beinpresse (Maschine)', 'Beine', ('Gesäß',),
       rest=COMPOUND, aka=('Leg Press (Machine)', 'Seated Leg Press', 'Sitzbeinpresse')),
    _e('machine_adductor', 'Adduktoren (Maschine)', 'Beine',
       aka=('Adductor Machine', 'Adduktion', 'Hip Adduction')),
    _e('plate_leg_press', 'Beinpresse (Maschine, Scheiben)', 'Beine', ('Gesäß',),
       rest=COMPOUND, uni=False, aka=('Leg Press', 'Leg Press (Plate Loaded)', '45° Beinpresse')),
    _e('plate_hack_squat', 'Hackenschmidt (Maschine, Scheiben)', 'Beine', ('Gesäß',),
       rest=COMPOUND, uni=False, aka=('Hack Squat', 'Hackenschmidt-Kniebeuge')),
    _e('plate_pendulum_squat', 'Pendulum Squat (Maschine, Scheiben)', 'Beine', ('Gesäß',),
       rest=COMPOUND, uni=False, aka=('Pendel-Kniebeuge',)),
    _e('plate_belt_squat', 'Belt Squat (Maschine, Scheiben)', 'Beine', ('Gesäß',),
       rest=COMPOUND, uni=False, aka=('Gürtelkniebeuge',)),

    # -- Gesäß --------------------------------------------------------------
    _e('barbell_hip_thrust', 'Hip Thrust (Langhantel)', 'Gesäß', ('Beine',),
       rest=COMPOUND, aka=('Barbell Hip Thrust', 'Hip Thrusts')),
    _e('barbell_glute_bridge', 'Glute Bridge (Langhantel)', 'Gesäß', ('Beine',),
       rest=COMPOUND, aka=('Barbell Glute Bridge', 'Beckenheben')),
    _e('smith_hip_thrust', 'Hip Thrust (Multipresse)', 'Gesäß', ('Beine',),
       rest=COMPOUND, aka=('Smith Machine Hip Thrust',)),
    _e('machine_hip_thrust', 'Hip Thrust (Maschine)', 'Gesäß', ('Beine',),
       rest=COMPOUND, aka=('Hip Thrust Machine',)),
    _e('plate_hip_thrust', 'Hip Thrust (Maschine, Scheiben)', 'Gesäß', ('Beine',),
       rest=COMPOUND, uni=False, aka=('Glute Drive',)),
    _e('cable_glute_kickback', 'Glute-Kickbacks (Kabel)', 'Gesäß', ('Beine',),
       uni=True, aka=('Cable Kickback', 'Glute Kickback')),
    _e('machine_glute_kickback', 'Glute-Kickbacks (Maschine)', 'Gesäß', ('Beine',),
       uni=True, aka=('Glute Machine', 'Glute Kickback Machine')),
    _e('machine_abductor', 'Abduktoren (Maschine)', 'Gesäß',
       aka=('Abductor Machine', 'Hip Abduction')),
    _e('cable_abduction', 'Abduktion (Kabel)', 'Gesäß',
       uni=True, aka=('Cable Hip Abduction',)),
    _e('cable_pull_through', 'Pull-Through (Kabel)', 'Gesäß', ('Beine',),
       aka=('Cable Pull Through',)),
    _e('kettlebell_swing', 'Swings (Kettlebell)', 'Gesäß', ('Beine', 'Rücken'),
       rest=COMPOUND, aka=('Kettlebell Swing', 'KB Swings')),

    # -- Waden --------------------------------------------------------------
    _e('machine_standing_calf_raise', 'Wadenheben (Maschine, stehend)', 'Waden',
       aka=('Standing Calf Raise',)),
    _e('machine_seated_calf_raise', 'Wadenheben (Maschine, sitzend)', 'Waden',
       aka=('Seated Calf Raise',)),
    _e('leg_press_calf_raise', 'Wadenheben (Beinpresse)', 'Waden',
       aka=('Calf Press', 'Wadendrücken')),
    _e('smith_calf_raise', 'Wadenheben (Multipresse)', 'Waden',
       aka=('Smith Machine Calf Raise',)),
    _e('dumbbell_calf_raise_one_leg', 'Wadenheben (Kurzhantel, einbeinig)', 'Waden',
       aka=('Single Leg Calf Raise',)),

    # -- Bauch --------------------------------------------------------------
    _e('cable_crunch', 'Crunches (Kabel)', 'Bauch',
       rest=CORE, aka=('Cable Crunch', 'Kabelcrunch')),
    _e('machine_crunch', 'Crunches (Maschine)', 'Bauch',
       rest=CORE, aka=('Ab Crunch Machine', 'Bauchmaschine')),
    _e('machine_torso_rotation', 'Rumpfrotation (Maschine)', 'Bauch',
       rest=CORE, uni=True, aka=('Torso Rotation', 'Rotationsmaschine')),
    _e('cable_woodchopper', 'Holzhacker (Kabel)', 'Bauch', ('Schultern',),
       rest=CORE, uni=True, aka=('Woodchopper', 'Wood Chop')),
    _e('cable_pallof_press', 'Pallof Press (Kabel)', 'Bauch',
       rest=CORE, uni=True, aka=('Pallof',)),
    _e('dumbbell_side_bend', 'Seitbeugen (Kurzhantel)', 'Bauch',
       rest=CORE, aka=('Side Bend',)),

    # -- Unterarme ----------------------------------------------------------
    _e('barbell_wrist_curl', 'Handgelenkcurls (Langhantel)', 'Unterarme',
       aka=('Wrist Curl',)),
    _e('dumbbell_wrist_curl', 'Handgelenkcurls (Kurzhantel)', 'Unterarme',
       aka=('Dumbbell Wrist Curl',)),
    _e('ez_reverse_curl', 'Reverse Curls (SZ-Stange)', 'Unterarme', ('Bizeps',),
       aka=('Reverse Curl', 'Obergriff-Curls')),
)

BY_KEY = {entry.key: entry for entry in LIBRARY}

# The group the add sheet lists a movement under: its first entry's. A variant
# can work something else first -- `Bankdrücken (Langhantel, eng)` is a
# triceps lift -- but it is looked for beside the rest of Bankdrücken, so one
# movement's variants never split across two sections.
MOVEMENT_GROUP = {}
for _entry in LIBRARY:
    MOVEMENT_GROUP.setdefault(_entry.movement, _entry.group)
# Those groups in the list's own order, Brust first: the sheet's sections.
LIST_GROUPS = tuple(dict.fromkeys(MOVEMENT_GROUP.values()))

# What every variant of a movement is also called, for search only (G-006):
# "bench" found the variants whose own aliases happened to say it and missed
# the rest -- Negativbankdrücken (Kurzhantel) among them. Kept apart from
# `aka`, where a name must belong to one entry.
MOVEMENT_AKA = {
    'Bankdrücken': ('Bench Press', 'Flachbankdrücken'),
    'Schrägbankdrücken': ('Incline Bench Press',),
    'Negativbankdrücken': ('Decline Bench Press',),
    'Rudern': ('Row', 'Rowing'),
    'Shrugs': ('Shrug', 'Schulterheben'),
    'Latzug': ('Lat Pulldown', 'Latziehen'),
    'Schulterdrücken': ('Shoulder Press', 'Overhead Press'),
    'Seitheben': ('Lateral Raise', 'Seitenheben'),
    'Bizepscurls': ('Biceps Curl',),
    'French Press': ('Skull Crusher', 'Stirndrücken'),
    'Trizepsstrecken über Kopf': ('Overhead Triceps Extension',),
    'Trizepsdrücken': ('Triceps Pushdown',),
    'Kniebeugen': ('Squat',),
    'Rumänisches Kreuzheben': ('Romanian Deadlift', 'RDL'),
    'Bulgarische Kniebeugen': ('Bulgarian Split Squat',),
    'Goblet Squat': ('Goblet Kniebeuge',),
    'Wadenheben': ('Calf Raise',),
}

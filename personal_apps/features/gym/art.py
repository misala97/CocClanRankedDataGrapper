"""Exercise pictures: which file under static/gym/art/ shows an exercise.

One drawing per movement for now (gym_exercise_art/make_prompts.py), later
one per list entry: an entry's own picture wins, else its movement's, else
there is none and the page shows its placeholder. make_art.py writes the
files under the same names.

The folder is read once, at import: the pictures only change with a deploy.
Each URL carries a hash of its file, so a redrawn picture is fetched again
instead of being served from a browser's cache under the old name.
"""
import hashlib
import os
import re

from flask import url_for

from .library import BY_KEY

ART = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                   'static', 'gym', 'art')


def slug(text):
    """A file name from a German name: `Bankdrücken (Kurzhantel)` ->
    `bankdruecken-kurzhantel`. The same rule make_prompts.py names the
    drawings by."""
    text = text.lower()
    for umlaut, spelled in (('ä', 'ae'), ('ö', 'oe'), ('ü', 'ue'), ('ß', 'ss')):
        text = text.replace(umlaut, spelled)
    return re.sub(r'[^a-z0-9]+', '-', text).strip('-')


def _scan(folder):
    """{name: short content hash} of every .webp in `folder`."""
    try:
        names = sorted(os.listdir(folder))
    except FileNotFoundError:
        return {}
    found = {}
    for name in names:
        stem, ext = os.path.splitext(name)
        if ext == '.webp':
            with open(os.path.join(folder, name), 'rb') as handle:
                found[stem] = hashlib.md5(handle.read()).hexdigest()[:8]
    return found


PICTURES = _scan(ART)


def picture_name(library_key, pictures=None):
    """The picture file (without extension) for a list entry, or None."""
    pictures = PICTURES if pictures is None else pictures
    entry = BY_KEY.get(library_key)
    if entry is None:
        return None
    for name in (slug(entry.name), slug(entry.movement)):
        if name in pictures:
            return name
    return None


def picture_url(library_key):
    """Where the page loads an exercise's picture from, or None."""
    name = picture_name(library_key)
    if name is None:
        return None
    return url_for('static', filename=f'gym/art/{name}.webp', v=PICTURES[name])

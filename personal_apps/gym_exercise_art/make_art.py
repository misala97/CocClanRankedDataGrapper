"""Writes static/gym/art/<slug>.webp, the exercise pictures the app shows,
from Michi's drawings in raw/ (gitignored; the prompts come from
make_prompts.py).

A picture is named after a movement (`bankdruecken`), or after one list
entry (`bankdruecken-kurzhantel`) once variants get their own; the app looks
for the entry's file first and falls back to the movement's
(features/gym/art.py). A .png wins over a .webp of the same name: raw PNGs are
lossless, so the webp written here is the only lossy step.

Per picture:
- cropped to a square around the drawing, the same margin for every one: the
  generator's margins vary, and a tile shows whatever margin it is given;
- scaled to SIZE px;
- the background snapped to one exact colour, PLATE: the generator never hits
  the hex it was asked for (235-236 / 226-229 / 242-245 across the set), and
  a picture a shade off its tile shows a seam. Only background connected to
  the border changes, so a light shirt beside it keeps its colour.

Run from personal_apps after new drawings land in raw/:
  py -3.12 gym_exercise_art/make_art.py
Needs numpy and scipy (dev machine only; the app just serves the files).
"""
import os
import re
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, 'raw')
OUT = os.path.join(os.path.dirname(HERE), 'static', 'gym', 'art')
sys.path.insert(0, os.path.dirname(HERE))
from features.gym.art import slug  # noqa: E402
from features.gym.library import LIBRARY  # noqa: E402

PLATE = (0xEE, 0xE5, 0xF3)      # gym.css --art-plate
SIZE = 640
MARGIN = 0.08                   # of the drawing's longer side, each way
BACKGROUND = 24                 # summed RGB distance still counted as background
INK = 60                        # summed RGB distance that is surely drawing
TYPES = ('.png', '.webp')


def sources():
    """{slug: raw file}, a .png preferred over a .webp of the same slug."""
    found = {}
    for name in sorted(os.listdir(RAW)):
        stem, ext = os.path.splitext(name)
        if ext.lower() in TYPES and stem != 'reference':
            if stem not in found or ext.lower() == '.png':
                found[stem] = os.path.join(RAW, name)
    return found


def _border_colour(pixels):
    edge = np.concatenate([pixels[0], pixels[-1], pixels[:, 0], pixels[:, -1]])
    return np.median(edge, axis=0)


def _square_crop(image):
    pixels = np.asarray(image, dtype=np.int16)
    distance = np.abs(pixels - _border_colour(pixels)).sum(axis=2)
    ink = distance > INK
    rows = np.flatnonzero(ink.sum(axis=1) > 3)
    cols = np.flatnonzero(ink.sum(axis=0) > 3)
    top, bottom, left, right = rows[0], rows[-1] + 1, cols[0], cols[-1] + 1
    side = round(max(bottom - top, right - left) * (1 + 2 * MARGIN))
    cy, cx = (top + bottom) / 2, (left + right) / 2
    box = (round(cx - side / 2), round(cy - side / 2))
    square = Image.new('RGB', (side, side), tuple(int(c) for c in _border_colour(pixels)))
    square.paste(image, (-box[0], -box[1]))
    return square


def _snap_background(image):
    pixels = np.asarray(image, dtype=np.int16)
    near = np.abs(pixels - _border_colour(pixels)).sum(axis=2) <= BACKGROUND
    labels, _ = ndimage.label(near)
    edge = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    background = np.isin(labels, edge[edge > 0])
    out = pixels.astype(np.uint8)
    out[background] = PLATE
    return Image.fromarray(out)


def make(path):
    image = Image.open(path).convert('RGB')
    image = _square_crop(image).resize((SIZE, SIZE), Image.LANCZOS)
    return _snap_background(image)


def main():
    known = {slug(entry.movement) for entry in LIBRARY} | {slug(entry.name) for entry in LIBRARY}
    os.makedirs(OUT, exist_ok=True)
    written, unknown = [], []
    for name, path in sources().items():
        if name not in known:
            unknown.append(name)
            continue
        make(path).save(os.path.join(OUT, name + '.webp'), 'WEBP', quality=82, method=6)
        written.append(name)
    sizes = [os.path.getsize(os.path.join(OUT, name + '.webp')) for name in written]
    print(f'{len(written)} pictures, {sum(sizes) // 1024} KB, largest {max(sizes, default=0) // 1024} KB')
    if unknown:
        print('no movement or list entry is called:', ', '.join(unknown))


if __name__ == '__main__':
    main()

"""Exercise pictures (round 4): which drawing an exercise shows.

One drawing per movement for now, later one per list entry: an entry's own
drawing wins, else its movement's, else there is none and the page draws its
placeholder. An exercise off the list (no key) has none.
"""
import re

from app import app as flask_app
from features.gym import art
from features.gym.library import BY_KEY, LIBRARY


JSON = {'Accept': 'application/json'}


def test_a_name_becomes_the_file_name_the_drawings_are_saved_under():
    assert art.slug('Bankdrücken (Kurzhantel)') == 'bankdruecken-kurzhantel'
    assert art.slug('Trizepsstrecken über Kopf') == 'trizepsstrecken-ueber-kopf'
    assert art.slug('Rückenstrecker') == 'rueckenstrecker'
    assert art.slug('Face Pulls') == 'face-pulls'
    assert art.slug('Straße  (x)') == 'strasse-x'


def test_an_entry_shows_its_own_drawing_before_its_movements():
    assert BY_KEY['dumbbell_bench_press'].name == 'Bankdrücken (Kurzhantel)'
    both = {'bankdruecken-kurzhantel': 'aaaaaaaa', 'bankdruecken': 'bbbbbbbb'}
    assert art.picture_name('dumbbell_bench_press', both) == 'bankdruecken-kurzhantel'
    assert art.picture_name('dumbbell_bench_press', {'bankdruecken': 'bbbbbbbb'}) == 'bankdruecken'
    assert art.picture_name('dumbbell_bench_press', {'latzug': 'cccccccc'}) is None


def test_an_exercise_off_the_list_has_no_drawing():
    assert art.picture_name(None) is None
    assert art.picture_name('no_such_key') is None


def test_every_drawing_is_named_after_an_entry_or_a_movement():
    """A file named off the rule would never show: the typo fails here."""
    names = {art.slug(e.name) for e in LIBRARY} | {art.slug(e.movement) for e in LIBRARY}
    assert art.PICTURES, 'no drawings under static/gym/art'
    assert sorted(set(art.PICTURES) - names) == []


def test_the_url_names_the_file_and_its_content():
    """The hash changes with the file, so a redrawn picture is fetched anew."""
    with flask_app.test_request_context():
        url = art.picture_url('barbell_bench_press')
    assert re.fullmatch(r'/static/gym/art/bankdruecken\.webp\?v=[0-9a-f]{8}', url)
    assert url.endswith(art.PICTURES['bankdruecken'])


def test_the_hash_follows_the_bytes_not_the_name(tmp_path):
    """Two names, same bytes: one hash. A redrawn file: a new hash. Anything
    but .webp is not a drawing."""
    (tmp_path / 'a.webp').write_bytes(b'one')
    (tmp_path / 'b.webp').write_bytes(b'one')
    (tmp_path / 'c.webp').write_bytes(b'two')
    (tmp_path / 'notes.txt').write_bytes(b'one')
    first = art._scan(str(tmp_path))
    assert sorted(first) == ['a', 'b', 'c']
    assert first['a'] == first['b'] != first['c']
    (tmp_path / 'a.webp').write_bytes(b'redrawn')
    assert art._scan(str(tmp_path))['a'] != first['a']


def test_no_folder_means_no_drawings(tmp_path):
    assert art._scan(str(tmp_path / 'missing')) == {}


def test_a_drawing_asked_for_by_its_hash_is_cached_for_good(client):
    """The ?v= hash names the bytes, as a dist bundle's file name does: a
    redrawn picture is a new URL, so the browser need never ask about this
    one again. Without the hash the file revalidates, like any that changes
    in place (I1b review)."""
    with flask_app.test_request_context():
        url = art.picture_url('barbell_bench_press')
    hashed = client.get(url)
    plain = client.get(url.split('?')[0])
    assert hashed.headers['Cache-Control'] == 'public, max-age=31536000, immutable'
    assert 'immutable' not in (plain.headers.get('Cache-Control') or '')
    hashed.close()
    plain.close()


def test_a_drawing_is_served_as_the_image_it_is(client):
    """Python before 3.13 has no type for .webp (on Windows nothing in the
    registry either): the file went out as application/octet-stream, which
    a browser only shows by sniffing past the nosniff header."""
    with flask_app.test_request_context():
        url = art.picture_url('barbell_bench_press')
    response = client.get(url)
    assert response.status_code == 200
    assert response.mimetype == 'image/webp'
    response.close()


def test_the_live_payload_carries_each_exercises_picture(client, live_session):
    """The list row (Butterfly) shows its movement's drawing; a row off the
    list shows none, and the page draws the placeholder."""
    from extensions import db
    from models import Exercise, SessionExercise

    with flask_app.app_context():
        own = Exercise(name='ZZ pytest art row')
        db.session.add(own)
        db.session.flush()
        row = SessionExercise(session_id=live_session['session'], exercise_id=own.id, position=2)
        db.session.add(row)
        db.session.commit()
        own_id, row_id = own.id, row.id
    try:
        payload = client.get(f"/gym/session/{live_session['session']}/detail.json", headers=JSON).get_json()
        pictures = {r['id']: r['picture'] for r in payload['visible_exercises']}
        assert re.fullmatch(r'/static/gym/art/butterfly\.webp\?v=[0-9a-f]{8}', pictures[live_session['se']])
        assert pictures[row_id] is None
    finally:
        with flask_app.app_context():
            db.session.delete(db.session.get(SessionExercise, row_id))
            db.session.delete(db.session.get(Exercise, own_id))
            db.session.commit()

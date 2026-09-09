"""The opt-in hub shell at /radar/hub/.

Two things matter here and they pull in opposite directions. The hub has to be
reachable and correct; and /radar/ has to be exactly as it was, because this
route exists to be reviewed and the decision to promote it has not been made.
So these tests check the new page AND that the old one still answers.
"""
import json
import re

import pytest

from app import app as flask_app
from extensions import db
from models import AppUser


def _shell(html):
    """The JSON the hub template embeds for its island."""
    match = re.search(
        r'<script type="application/json" id="radar-hub-data">(.*?)</script>',
        html, re.S)
    assert match, 'no embedded shell -- is this the hub page?'
    return json.loads(match.group(1))


@pytest.fixture()
def plain_user():
    """A signed-in account that is not an admin."""
    from werkzeug.security import generate_password_hash

    name = 'pytest radar hub nonadmin'
    with flask_app.app_context():
        AppUser.query.filter_by(username=name).delete(synchronize_session=False)
        db.session.commit()
        user = AppUser(username=name, password_hash=generate_password_hash('x'),
                       is_admin=False)
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    flask_app.config['TESTING'] = True
    try:
        with flask_app.test_client() as test_client:
            with test_client.session_transaction() as flask_session:
                flask_session['user_id'] = user_id
            yield test_client
    finally:
        with flask_app.app_context():
            AppUser.query.filter_by(id=user_id).delete(synchronize_session=False)
            db.session.commit()


def test_the_hub_needs_a_session(anon_client):
    assert anon_client.get('/radar/hub/').status_code == 302


def test_the_hub_embeds_the_board_it_would_otherwise_have_to_fetch(client):
    response = client.get('/radar/hub/')
    assert response.status_code == 200
    shell = _shell(response.get_data(as_text=True))
    assert 'rows' in shell['board']
    assert 'generated_at' in shell['board']
    assert shell['board']['display_timezone'] == 'Europe/Berlin'


def test_the_shell_says_whether_this_reader_administers(client, plain_user):
    assert _shell(client.get('/radar/hub/').get_data(as_text=True))['is_admin'] is True
    assert _shell(plain_user.get('/radar/hub/').get_data(as_text=True))['is_admin'] is False


def test_the_embedded_json_is_escaped(client):
    """`tojson` escapes <, > and &, so a company name containing a tag cannot
    close the script element and become markup."""
    html = client.get('/radar/hub/').get_data(as_text=True)
    embedded = re.search(
        r'<script type="application/json" id="radar-hub-data">(.*?)</script>',
        html, re.S).group(1)
    assert '</script' not in embedded
    assert '<' not in embedded


def test_a_bad_query_falls_back_to_the_default_board(client):
    """A person editing the address bar is not a bug. Same rule as the board
    page: answer with the default rather than an error document."""
    response = client.get('/radar/hub/?market=moon&window=nonsense')
    assert response.status_code == 200
    assert _shell(response.get_data(as_text=True))['board']['market'] in ('us', 'de')


def test_a_valid_query_reaches_the_embedded_board(client):
    shell = _shell(client.get('/radar/hub/?market=de&window=24')
                   .get_data(as_text=True))
    assert shell['board']['market'] == 'de'
    assert shell['board']['window_hours'] == 24


def test_the_old_board_route_still_answers(client):
    """The hub is opt-in. /radar/ is the way back and must not have moved."""
    response = client.get('/radar/')
    assert response.status_code == 200
    assert 'radar-data' in response.get_data(as_text=True)


def test_the_hub_loads_its_own_bundle_and_stylesheet(client):
    """The scoped stylesheet is imported by the entry, so Vite emits it as its
    own hashed file. Linking only the script renders the page unstyled with
    nothing in the console to say why -- which is how this was found."""
    html = client.get('/radar/hub/').get_data(as_text=True)
    assert re.search(r'<script type="module" src="/static/radar/dist/assets/hub-[^"]+\.js"',
                     html), html[-800:]
    assert re.search(r'<link rel="stylesheet" href="/static/radar/dist/assets/hub-[^"]+\.css"',
                     html), html[-800:]
    # radar.css belongs to the old board; the hub's system is scoped to .rh,
    # and loading both would let one restyle the other.
    assert 'radar/radar.css' not in html

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


@pytest.mark.parametrize('path', ('/radar/', '/radar/hub/', '/radar/legacy/'))
def test_every_radar_entry_needs_a_session(anon_client, path):
    response = anon_client.get(path)
    assert response.status_code == 302


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


def test_a_bad_filter_falls_back_to_the_default_board(client):
    """A person editing the address bar is not a bug. Same rule as the board
    page: answer a malformed filter with the default rather than an error."""
    response = client.get('/radar/hub/?window=nonsense')
    assert response.status_code == 200
    assert _shell(response.get_data(as_text=True))['board']['market'] == 'us'


def test_an_explicit_unsupported_market_is_a_visible_400(client):
    """The friendly fallback never applies to an explicit non-US market:
    a German bookmark must not silently open the US board."""
    for path in ('/radar/hub/?market=moon&window=nonsense',
                 '/radar/hub/?market=de', '/radar/?market=de&window=24',
                 '/radar/?t=AAA&market=de&window=24'):
        response = client.get(path)
        assert response.status_code == 400, path
        html = response.get_data(as_text=True)
        assert 'unsupported market' in html, path
        assert 'radar-hub-data' not in html, path


def _legacy_payload(html):
    """The board the legacy page embeds for its island."""
    match = re.search(
        r'<script type="application/json" id="radar-data">(.*?)</script>',
        html, re.S)
    assert match, 'no embedded board -- is this the legacy page?'
    return json.loads(match.group(1))


@pytest.mark.parametrize('route', ('/radar/', '/radar/hub/', '/radar/legacy/'))
@pytest.mark.parametrize('markets', ('market=us&market=de',
                                     'market=de&market=us'))
def test_a_repeated_market_with_any_unsupported_value_is_a_visible_400(
        client, route, markets):
    """Every supplied value is checked before the friendly fallback, in
    either order, and the refusal embeds no board."""
    response = client.get(f'{route}?{markets}&window=24')
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert 'unsupported market' in html
    assert 'radar-hub-data' not in html
    assert 'radar-data' not in html


@pytest.mark.parametrize('route', ('/radar/', '/radar/hub/', '/radar/legacy/'))
def test_a_repeated_supported_market_opens_the_us_board(client, route):
    response = client.get(f'{route}?market=us&market=&market=us&window=24')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    board = (_legacy_payload(html) if route == '/radar/legacy/'
             else _shell(html)['board'])
    assert board['market'] == 'us'
    assert board['window_hours'] == 24


@pytest.mark.parametrize('route', ('/radar/', '/radar/hub/', '/radar/legacy/'))
def test_a_malformed_filter_beside_supported_markets_still_falls_back(
        client, route):
    response = client.get(f'{route}?market=us&market=us&window=nonsense')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    board = (_legacy_payload(html) if route == '/radar/legacy/'
             else _shell(html)['board'])
    assert board['market'] == 'us'


def test_a_valid_query_reaches_the_embedded_board(client):
    for path in ('/radar/hub/?window=24', '/radar/hub/?market=us&window=24'):
        shell = _shell(client.get(path).get_data(as_text=True))
        assert shell['board']['market'] == 'us'
        assert shell['board']['window_hours'] == 24


def test_the_discover_url_embeds_the_existing_warm_default(client):
    """Discover remains the reader-facing spelling, but the hub asks for the
    already-warm backend key instead of creating an equivalent cold key."""
    response = client.get('/radar/hub/?segment=discover')
    shell = _shell(response.get_data(as_text=True))

    assert response.request.query_string == b'segment=discover'
    assert shell['board']['segments'] == ['discover', 'mid', 'micro', 'unknown']


def test_root_and_alias_mount_the_same_hub(client):
    for path in ('/radar/', '/radar/hub/'):
        response = client.get(path)
        assert response.status_code == 200
        assert 'radar-hub-data' in response.get_data(as_text=True)


def test_root_legacy_ticker_keeps_supported_board_filters(client):
    shell = _shell(client.get('/radar/?t=AAA&window=24')
                   .get_data(as_text=True))
    assert shell['board']['market'] == 'us'
    assert shell['board']['window_hours'] == 24


def test_legacy_route_keeps_the_original_board(client):
    response = client.get('/radar/legacy/?t=AAA&window=24')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'radar-data' in html
    assert 'radar-hub-data' not in html
    assert '/radar/?t=AAA&amp;window=24' in html


def test_legacy_route_rejects_an_explicit_unsupported_market(client):
    response = client.get('/radar/legacy/?t=AAA&market=de&window=24')
    assert response.status_code == 400
    html = response.get_data(as_text=True)
    assert 'unsupported market' in html
    assert 'radar-data' not in html


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

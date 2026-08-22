"""The JSON the surface will read.

Login-required and global: mention data is not personal, so all accounts see
identical rows (spec 8.5).
"""
import json


def test_the_board_requires_login(anon_client):
    response = anon_client.get('/radar/api/board')
    assert response.status_code in (302, 401, 403)


def test_the_board_returns_json(client):
    response = client.get('/radar/api/board')
    assert response.status_code == 200
    payload = json.loads(response.data)
    assert 'rows' in payload
    assert 'sources' in payload
    assert isinstance(payload['rows'], list)


def test_the_selected_sources_are_echoed_back(client):
    """The surface needs to know which selection produced these rows, or a
    stale request and a fresh one look identical."""
    payload = json.loads(client.get('/radar/api/board?sources=bluesky').data)
    assert payload['sources'] == ['bluesky']


def test_an_unknown_source_is_rejected(client):
    """Silently ignoring it would return the default board under a selection
    the viewer never made."""
    assert client.get('/radar/api/board?sources=nonsense').status_code == 400


def test_an_unknown_segment_is_rejected(client):
    assert client.get('/radar/api/board?segment=nonsense').status_code == 400


def test_the_window_is_bounded(client):
    """An unbounded window would scan the whole partitioned history on a page
    load."""
    assert client.get('/radar/api/board?window=99999').status_code == 400


def test_defaults_are_every_source_and_no_segment_filter(client):
    payload = json.loads(client.get('/radar/api/board').data)
    from features.radar.config import SOURCES
    assert set(payload['sources']) == set(SOURCES)
    assert payload['segment'] is None


def test_the_payload_carries_what_the_surface_has_to_draw(client):
    """The island renders one payload type -- what is embedded on first paint
    and what this route answers with are the same shape. A missing key here
    shows up as a blank panel, not an error."""
    payload = json.loads(client.get('/radar/api/board').data)

    for key in ('generated_at', 'sources', 'all_sources', 'segment',
                'window_hours', 'segment_counts', 'triplet_hours',
                'series_hours', 'lead_count', 'rows'):
        assert key in payload, key

    if payload['rows']:
        row = payload['rows'][0]
        for key in ('ticker', 'divergence', 'mention_z', 'mentions', 'authors',
                    'marks', 'series', 'triplet', 'tone', 'price_series',
                    'price_status'):
            assert key in row, key
        assert set(row['triplet']) == {'1', '4', '24'}
        assert set(row['tone']) == {'bullish', 'neutral', 'bearish'}
        assert all(set(point) == {'hour', 'count'} for point in row['series'])


def test_segment_counts_label_the_filter_not_the_result(client):
    """Counted after the filter, every button would report the size of the
    selected segment."""
    everything = json.loads(client.get('/radar/api/board').data)
    if not everything['rows']:
        return
    segment = everything['rows'][0]['segment']

    filtered = json.loads(
        client.get(f'/radar/api/board?segment={segment}').data)

    assert filtered['segment_counts'] == everything['segment_counts']


# ------------------------------------------------------------ the page ------
#
# The board page is a shell around the same payload. These pin the seam
# between it and the island: the mount node, the embedded JSON, and the fact
# that a person typing nonsense into the address bar gets a board rather than
# a JSON error page.

def test_the_page_requires_login(anon_client):
    assert anon_client.get('/radar/').status_code in (302, 401, 403)


def test_the_page_embeds_the_board_it_would_otherwise_have_to_fetch(client):
    response = client.get('/radar/')
    assert response.status_code == 200
    html = response.data.decode()

    assert 'id="radar-root"' in html
    assert 'id="radar-data"' in html
    embedded = json.loads(html.split('id="radar-data">')[1].split('</script>')[0]
                          .replace('&lt;', '<').replace('&gt;', '>')
                          .replace('&amp;', '&'))
    assert 'rows' in embedded and 'segment_counts' in embedded


def test_the_page_falls_back_to_the_default_board_on_a_bad_query(client):
    """The API is strict because a client sending nonsense has a bug worth
    surfacing. A person editing the address bar is not a bug."""
    assert client.get('/radar/api/board?window=7').status_code == 400
    assert client.get('/radar/?window=7').status_code == 200

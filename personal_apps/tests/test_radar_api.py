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


def test_defaults_are_every_source_and_the_small_segment(client):
    """Every source, because none is primary. But not every segment: the
    board is for the stuff nobody has heard of, and megacap chatter is not
    news. Changed 2026-08-23; this asserted `segment is None`."""
    payload = json.loads(client.get('/radar/api/board').data)
    from features.radar.config import DEFAULT_SEGMENT, SOURCES
    assert set(payload['sources']) == set(SOURCES)
    assert payload['segment'] == DEFAULT_SEGMENT


def test_an_empty_segment_still_asks_for_everything(client):
    """All has to stay reachable now that the default is not None. The
    surface sends `?segment=` for it, so an empty value cannot fall back to
    the default or the chip would be dead."""
    payload = json.loads(client.get('/radar/api/board?segment=').data)

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
                    'marks', 'series', 'triplet', 'tone', 'clauses',
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


def test_the_row_carries_no_chart_of_its_own(client):
    """The chart moved to the detail panel on 2026-08-23. Three years is ~780
    closes, so a twenty-row board would have shipped sixteen thousand numbers
    to draw twenty sparklines.

    This replaces a test that walked every row's chart and skipped nulls --
    which passed vacuously the moment the board was empty, which is the same
    hole test_the_row_serializer_actually_runs exists to cover.
    """
    payload = json.loads(client.get('/radar/api/board').data)

    for row in payload['rows']:
        assert 'chart' not in row


def test_the_row_serializer_actually_runs(client):
    """The teeth on every other test in this file.

    Each of them iterates payload['rows'] and skips what it cannot check, so
    on an empty board they all pass without executing a line of _row(). That
    happened: `_chart` went missing from the serializer, every test here
    stayed green, and the page 500'd in a browser.

    This test builds a row itself rather than trusting the dev database to
    contain one.
    """
    import datetime as dt
    import decimal
    import json as _json
    from app import app as flask_app
    from extensions import db
    from features.radar import board
    from features.radar.routes.api import serialize
    from features.radar.config import source_config_version
    from models import (RadarBucketSource, RadarDailyClose, RadarMention,
                        RadarPost, TickerUniverse)

    now = dt.datetime(2026, 3, 12, 15, 0, 0)
    tag = 'SERZ'

    def wipe():
        RadarMention.query.filter(RadarMention.ticker == tag).delete(
            synchronize_session=False)
        RadarPost.query.filter(RadarPost.external_id.like(f'{tag}%')).delete(
            synchronize_session=False)
        for model in (RadarBucketSource, RadarDailyClose):
            model.query.filter(model.ticker == tag).delete(
                synchronize_session=False)
        TickerUniverse.query.filter_by(symbol=tag).delete(
            synchronize_session=False)
        db.session.commit()

    with flask_app.app_context():
        wipe()
        db.session.add(TickerUniverse(symbol=tag, name='Serializer Corp',
                                      first_seen=dt.datetime(2020, 1, 1),
                                      daily_sigma=0.02))
        db.session.add(RadarBucketSource(
            ticker=tag, bucket_start=now - dt.timedelta(minutes=30),
            source='bluesky', mention_count=10, high_confidence_count=10,
            low_count=0, distinct_authors=6, distinct_text_ratio=0.9,
            engagement_weighted_count=10.0, status='ok',
            source_config_version=source_config_version(),
            expected=1.0, variance=2.0, mention_z=5.0, baseline_days=30))
        db.session.add(RadarDailyClose(
            ticker=tag, close_date=now.date(),
            close=decimal.Decimal('12.34'), fetched_at=now))
        db.session.commit()

        payload = serialize(board.build(['bluesky'], now))
        wipe()

    rows = [r for r in payload['rows'] if r['ticker'] == tag]
    assert len(rows) == 1, 'the fixture row did not reach the board'
    row = rows[0]
    # `chart` was the field this test was written for. It moved to the detail
    # panel on 2026-08-23; the phrase took its place as the row's one field
    # that is computed rather than copied, so it is the one worth guarding.
    assert row['clauses'], 'the row phrase is missing'
    assert all({'kind', 'text'} == set(c) for c in row['clauses'])
    assert 'chart' not in row
    # Serializable end to end -- the 500 was a NameError inside _row.
    _json.dumps(payload)


def test_an_unsupported_venue_filter_is_rejected(client):
    assert client.get('/radar/api/board?venues=7').status_code == 400
    assert client.get('/radar/api/board?venues=2').status_code == 200


def test_the_payload_carries_the_venue_filter_and_its_counts(client):
    payload = json.loads(client.get('/radar/api/board').data)

    assert payload['min_venues'] == 1
    assert set(payload['venue_counts']) == {'any', 'multi'}


def test_small_is_an_accepted_segment(client):
    assert client.get('/radar/api/board?segment=small').status_code == 200


def test_the_board_opens_on_the_small_stuff(client):
    """It is a discovery radar for penny stocks. Opening on All means reading
    megacaps and micro-caps in one list."""
    payload = json.loads(client.get('/radar/api/board').data)

    assert payload['segment'] == 'small'


def test_the_payload_says_what_the_floor_left_out(client):
    """A two-row board and a stopped ingest are indistinguishable without
    this, and the reader has no way to tell which they are looking at."""
    payload = json.loads(client.get('/radar/api/board').data)

    assert isinstance(payload['excluded'], dict)


def test_the_intraday_spans_are_accepted_by_the_route(client):
    """The route validated against SPAN_DAYS alone, so 1D and 1W would have
    been rejected as unknown while the panel underneath understood them
    perfectly -- a 400 with no way to tell it from a typo."""
    from features.radar import detail

    for span in detail.INTRADAY_SPANS:
        assert detail.known_span(span)


def test_an_invented_span_is_still_rejected():
    """Teeth. known_span widened the gate; it must not have removed it."""
    from features.radar import detail

    assert not detail.known_span('5Y')
    assert not detail.known_span('')

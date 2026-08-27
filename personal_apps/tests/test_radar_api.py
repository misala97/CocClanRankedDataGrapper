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


def test_the_board_payload_surfaces_unpriced_tokens(client, monkeypatch):
    """The spend summary crosses the API boundary without becoming dollars."""
    from features.radar.routes import api

    monkeypatch.setattr(api.spend, 'summary', lambda: {
        'today_usd': 0.0,
        'month_usd': 0.0,
        'unpriced_tokens': 501_000,
    })

    payload = json.loads(client.get('/radar/api/board').data)

    assert payload['spend']['unpriced_tokens'] == 501_000


def test_the_selected_sources_are_echoed_back(client):
    """The surface needs to know which selection produced these rows, or a
    stale request and a fresh one look identical."""
    payload = json.loads(client.get('/radar/api/board?sources=bluesky').data)
    assert payload['sources'] == ['bluesky']


def test_an_unknown_source_is_rejected(client):
    """Silently ignoring it would return the default board under a selection
    the viewer never made."""
    assert client.get('/radar/api/board?sources=nonsense').status_code == 400


def test_a_concrete_reddit_source_is_accepted_but_an_unknown_root_is_not():
    from features.radar.routes.api import BadQuery, parse_query
    import pytest

    assert parse_query({'sources': 'reddit:wallstreetbets'}).sources == [
        'reddit:wallstreetbets']
    with pytest.raises(BadQuery):
        parse_query({'sources': 'notreddit:wallstreetbets'})


def test_the_board_gets_the_selection_and_echoes_the_root(client, monkeypatch):
    """The API hands the SELECTION down, not an expansion, and echoes a root.

    Expanding here would take the choice away from the queries underneath,
    which expand differently: a scored read may not see the pre-split root
    `reddit` rows and a raw-count read must (config.expand_sources vs
    expand_sources_for_history). Once the list is expanded the root is gone
    and neither can tell it was ever asked for.

    What the payload carries back is still the root, because that is what
    lights the chip. The expansion itself is proved where it happens -- see
    test_radar_board / test_radar_detail's historical-root tests.
    """
    from features.radar.routes import api

    seen = {}
    real_build = api.board_mod.build

    def capture(sources, *args, **kwargs):
        seen['sources'] = list(sources)
        return real_build(sources, *args, **kwargs)

    monkeypatch.setattr(api.board_mod, 'build', capture)
    response = client.get('/radar/api/board?sources=reddit')
    payload = json.loads(response.data)

    assert response.status_code == 200
    assert seen['sources'] == ['reddit']
    assert payload['sources'] == ['reddit']


def test_the_detail_panel_gets_the_selection(client, monkeypatch):
    from features.radar.routes import api

    seen = {}

    def capture(ticker, sources, now, **kwargs):
        seen['sources'] = list(sources)
        return object()

    monkeypatch.setattr(api.detail_panel, 'build', capture)
    monkeypatch.setattr(api, 'serialize_detail', lambda built: {'ok': True})

    response = client.get('/radar/api/ticker/ZZG?sources=reddit')

    assert response.status_code == 200
    assert seen['sources'] == ['reddit']


def test_a_concrete_subreddit_link_lights_the_reddit_chip(client, monkeypatch):
    """`?sources=reddit:wallstreetbets` filters to that sub AND lights Reddit.

    The payload's `sources` is compared against `all_sources` -- three roots
    -- to decide which chips are on. A concrete name matched none of them, so
    the control rendered every chip off: a state it otherwise forbids, and
    one whose first click silently discarded the concrete selection.
    """
    from features.radar.routes import api

    seen = {}
    real_build = api.board_mod.build

    def capture(sources, *args, **kwargs):
        seen['sources'] = list(sources)
        return real_build(sources, *args, **kwargs)

    monkeypatch.setattr(api.board_mod, 'build', capture)
    payload = json.loads(
        client.get('/radar/api/board?sources=reddit:wallstreetbets').data)

    assert seen['sources'] == ['reddit:wallstreetbets']
    assert payload['sources'] == ['reddit']
    assert payload['sources'][0] in payload['all_sources']


def test_a_selection_longer_than_every_real_name_is_rejected(client):
    """Rooting the membership check unbounded the list's length.

    `reddit:<anything>` passes validation, and each accepted entry lands in
    six or more IN (...) clauses against a ~300k-row partitioned table. The
    cap is the largest selection that can name something real.
    """
    from features.radar.routes.api import MAX_SOURCES

    ok = ','.join(['reddit:x%d' % i for i in range(MAX_SOURCES)])
    too_many = ok + ',reddit:overflow'

    assert client.get('/radar/api/board?sources=' + ok).status_code == 200
    assert client.get(
        '/radar/api/board?sources=' + too_many).status_code == 400


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
    assert payload['segments'] == [DEFAULT_SEGMENT]


def test_an_empty_segment_still_asks_for_everything(client):
    """All has to stay reachable now that the default is not None. The
    surface sends `?segment=` for it, so an empty value cannot fall back to
    the default or the chip would be dead."""
    payload = json.loads(client.get('/radar/api/board?segment=').data)

    assert payload['segments'] == []


def test_the_payload_carries_what_the_surface_has_to_draw(client):
    """The island renders one payload type -- what is embedded on first paint
    and what this route answers with are the same shape. A missing key here
    shows up as a blank panel, not an error."""
    payload = json.loads(client.get('/radar/api/board').data)

    for key in ('generated_at', 'sources', 'all_sources', 'segments',
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

    assert payload['segments'] == ['small']


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


# --- Multi-segment query parsing, 2026-08-25 --------------------------------

def _parse(**args):
    from features.radar.routes.api import parse_query
    return parse_query(args)


def test_several_segments_arrive_as_a_list():
    assert _parse(segment='small,large').segments == ['small', 'large']


def test_a_single_segment_still_parses():
    """Bookmarked URLs carry `?segment=small`. Widening the parameter must not
    invalidate every link anyone saved."""
    assert _parse(segment='small').segments == ['small']


def test_an_empty_segment_is_still_how_the_surface_asks_for_all():
    assert _parse(segment='').segments == []


def test_the_default_is_still_the_discovery_segment():
    """It is a radar for things nobody has heard of. Opening on everything
    buries them under megacap chatter."""
    from features.radar.config import DEFAULT_SEGMENT

    assert _parse().segments == [DEFAULT_SEGMENT]


def test_one_unknown_name_rejects_the_whole_selection():
    """Silently dropping it would return a board under a selection the viewer
    never made, which is the reason every other parameter here is validated
    rather than coerced."""
    from features.radar.routes.api import BadQuery
    import pytest as _pytest

    with _pytest.raises(BadQuery):
        _parse(segment='small,nonsense')


def test_whitespace_and_empty_entries_are_forgiven():
    """A person editing the address bar is not a bug."""
    assert _parse(segment=' small , large ,').segments == ['small', 'large']


def _stub_detail(breakdown):
    """The minimal detail_panel.build() return serialize_detail reads.

    Built by hand from detail_panel.py's and detail.py's own dataclasses
    rather than through detail_panel.build itself, so tests that use this do
    not depend on which tickers the local database happens to hold.
    """
    import datetime as dt

    from features.radar import detail, detail_panel

    return detail_panel.Detail(
        ticker='ZZSTUB', name='Stub Corp', exchange='Q', segment='micro',
        market_cap=None, ipo_date=None, price=None, price_move=None,
        price_status='ok', session='closed', span='1D',
        chart=detail.Chart(start=dt.date(2026, 3, 12), closes=[], chatter=[],
                           watched_from=None, step_minutes=15),
        breakdown=breakdown, posts=[], post_total=0,
        mentions=breakdown.mentions, expected=0.0, baseline_days=None)


def test_the_detail_payload_carries_the_sarcasm_signal():
    """Two sentiment scores are kept so their DISAGREEMENT can be read. Until
    now nothing compared them, which made the second one decoration.

    Asserted on the serializer rather than through a route, so it does not
    depend on which tickers the local database happens to hold.
    """
    import dataclasses

    from features.radar import detail_panel
    from features.radar.routes import api

    breakdown = detail_panel.Breakdown(
        venues=[], bullish=3, neutral=1, bearish=2, disagreements=2,
        top_author_share=None, top_two_share=None, peak_hour=None,
        peak_count=0, first_seen=None, mentions=6, voices=4)
    built = _stub_detail(breakdown)

    payload = api.serialize_detail(built)
    assert payload['breakdown']['disagreements'] == 2

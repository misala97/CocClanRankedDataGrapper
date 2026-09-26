"""Gym routes, split by domain.

Importing a module here is what registers its routes onto gym_bp, so every
module must be imported below even though the names look unused -- hence the
noqa markers. gym_bp itself lives in _blueprint.py so no domain module has to
import a sibling to reach it, which is what keeps these imports acyclic.

The re-exports at the bottom are not decoration. Test call sites import these
private helpers from `features.gym.routes`, and keeping that path working is
what let the 2912-line routes.py split into this package without touching a
single caller.
"""
import re
from urllib.parse import urlsplit, urlunsplit

from flask import (
    abort, current_app, flash, g, jsonify, make_response, redirect, render_template, request,
    url_for,
)

from extensions import db
from ..scope import current_user_id
from ._blueprint import gym_bp

from . import helpers          # noqa: F401
from . import history          # noqa: F401
from . import workout          # noqa: F401
from . import partners         # noqa: F401
from . import partner_view     # noqa: F401
from . import session_admin    # noqa: F401
from . import reports          # noqa: F401
from . import catalogue        # noqa: F401
from . import exercise_detail  # noqa: F401
from . import push_routes      # noqa: F401

from .helpers import (         # noqa: F401
    _to_float, _to_increment, _to_int, _to_stack_steps,
    _get_active_session, _cancel_pending_push, _username,
)
from .history import (         # noqa: F401
    load_performed, _to_performed, _session_rest_entries,
    performed_from_session,
)
from .workout import (                                                 # noqa: F401
    _live_context, _live_data, _session_payload, _template_exercises_from_session,
)
from .exercise_detail import (                                         # noqa: F401
    _exercise_detail_payload,
)
# Re-exported, not defined in this package: seeding.py owns it because
# sharing.py needs it too and cannot import a module that registers routes.
# Three tests import it from `features.gym.routes`, so the path has to survive.
from ..seeding import _last_full_performance                           # noqa: F401

@gym_bp.before_request
def _exercise_rows_follow_the_list():
    """library.py is the exercise list; its rows catch up once per process,
    so an entry added in code is there on the first request after a deploy."""
    from ..exercises import ensure_library
    ensure_library()


@gym_bp.before_request
def _settle_an_abandoned_workout_first():
    """A page is built from a workout that is what it is now: one nobody
    came back to is ended before anything reads it (helpers.
    _settle_if_abandoned) -- not halfway through the render by the nav's
    context processor, after the page had drawn it as running. JSON reads
    too: the island's refetch learns its workout was ended and reloads.
    Writes settle in their own guards.

    Only under /gym: the phone's hold cookie (helpers._outbox_hold) is
    scoped there, and /sw.js -- the one route outside, fetched by the
    browser on its own -- ended the workout a phone still held sets for."""
    if (request.method == 'GET' and request.path.startswith('/gym')
            and current_user_id() is not None):
        # Kept for the page and the nav (helpers._page_active_session).
        active = helpers._get_active_session()
        # A partner nobody came back to ends the link here as well.
        if active is not None:
            active = helpers._end_stale_partner_links(active)
        g.gym_active_session = active


@gym_bp.before_request
def _require_csrf_on_writes():
    """Second defence layer on every gym write, behind SameSite=Lax.

    The token is auth.py's own per-session one (_get_csrf_token mints it,
    the shell's <meta name="csrf-token"> delivers it): islands send it as
    X-CSRF-Token from src/api.ts, native forms as a hidden csrf_token field
    via <CsrfField/>. One rule at the blueprint gate rather than thirty
    per-route checks, because the route that forgets is the whole exploit.

    Suites run with the gate open -- Flask-WTF's own convention -- so five
    hundred tests do not each mint and thread a token; test_gym_csrf.py sets
    CSRF_STRICT and pins the closed gate explicitly.
    """
    if request.method != 'POST':
        return
    if current_app.config.get('TESTING') and not current_app.config.get('CSRF_STRICT'):
        return
    from auth import _valid_csrf
    submitted = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
    if not _valid_csrf(submitted):
        abort(403)


@gym_bp.after_request
def _pages_are_never_stored(response):
    """A gym page carries its data in its HTML -- the island payload -- so a
    stored copy is the workout as it was: before the delete, the finish, the
    new record (G-141). no-store keeps pages out of the HTTP cache and, in
    Chrome, out of the back-forward cache; a page Safari restores anyway is
    reloaded by its island (static/gym/src/fresh.ts). HTML only: the bundles
    are hashed and immutable (app.py), and the JSON reads carry no validator
    a browser could cache on."""
    if response.mimetype == 'text/html':
        response.headers['Cache-Control'] = 'no-store'
    return response


@gym_bp.errorhandler(helpers.InvalidInput)
def _refuse_invalid_input(error):
    """A typed value the server will not store (helpers.InvalidInput).

    An island gets a 400 with the sentence, which it shows in place of
    "Verbindung fehlgeschlagen". A form post goes back to the page it was sent
    from, with the sentence flashed there -- only this site's own gym pages,
    never wherever a Referer points. Nothing half-written survives either way.
    """
    db.session.rollback()
    if helpers._wants_json():
        return jsonify({'error': error.message}), 400
    flash(error.message, 'error')
    came_from = urlsplit(request.referrer or '')
    if came_from.netloc == request.host and came_from.path.startswith('/gym'):
        return redirect(urlunsplit(('', '', came_from.path, came_from.query, '')))
    return redirect(url_for('gym.gym_heute'))


# What a gym address that leads nowhere was, by where it pointed, and the way
# on from there. Matched from the start of the path, first match wins; the
# last entry is every other /gym address.
_NOT_FOUND = tuple((re.compile(pattern), *said) for pattern, *said in (
    # "Beenden" or "Verwerfen" on a phone that still showed a workout the
    # other one threw away: Start, not Verlauf, where it never shows up. A
    # 404 all the same -- someone else's workout answers exactly so.
    (r'/gym/session/\d+/(finish|discard)$', 'Dieses Workout gibt es nicht mehr.',
     'Es wurde gelöscht oder verworfen.', '/gym', 'Zum Start'),
    (r'/gym/session/', 'Dieses Workout gibt es nicht mehr.',
     'Es wurde gelöscht oder verworfen.', '/gym/verlauf', 'Zum Verlauf'),
    (r'/gym/exercises/', 'Diese Übung gibt es nicht.',
     'Die Adresse führt zu keiner Übung.', '/gym/uebungen', 'Zu den Übungen'),
    # Also an invite answered already: Back from the workout it was accepted
    # into lands on its confirm page again. Or taken back by the leader.
    (r'/gym/shared/', 'Diese Einladung gilt nicht mehr.',
     'Angenommen, abgelehnt, zurückgezogen oder das Workout ist vorbei.', '/gym', 'Zum Start'),
    (r'/gym', 'Diese Seite gibt es nicht.',
     'Die Adresse führt zu keiner Seite des Gym Trackers.', '/gym', 'Zum Start'),
))


@gym_bp.app_errorhandler(404)
def _gym_not_found(error):
    """A gym address that leads nowhere (G-081): a workout deleted since, an
    old tab, the back button. It showed Werkzeug's English "Not Found".

    A page load gets a gym page that says what is gone and the way on; an
    island's read gets {"error": ...} -- api.ts reads any 404 as gone.
    App-wide, not the blueprint's own: an address no gym route matches never
    reaches the blueprint's handlers. Every address outside /gym keeps
    Flask's answer. The live screen's 409 (scope._missing) is not a 404 and
    never comes here.
    """
    if not (request.path == '/gym' or request.path.startswith('/gym/')):
        return error
    db.session.rollback()
    if helpers._wants_json():
        return jsonify({'error': 'Gibt es nicht (mehr).'}), 404
    heading, line, href, label = next(
        entry[1:] for entry in _NOT_FOUND if entry[0].match(request.path))
    # An address no gym route matched has no blueprint: app.py's strict
    # script policy keys on it, and the blueprint's handlers and hooks never
    # run. So the policy is asked for here, no-store set here, and the nav's
    # running workout passed rather than left to the context processors.
    # not_found: the nav keeps its resume strip on a session address too.
    g.strict_scripts = True
    response = make_response(render_template(
        'gym/not_found.html', heading=heading, line=line, way_href=href, way_label=label,
        not_found=True, gym_active_session=helpers._page_active_session(),
        gym_live_exercise_name=workout._live_exercise_name), 404)
    return _pages_are_never_stored(response)


__all__ = ['gym_bp']

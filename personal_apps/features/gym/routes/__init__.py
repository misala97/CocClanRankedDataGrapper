"""Gym routes, split by domain.

Importing a module here is what registers its routes onto gym_bp, so every
module must be imported below even though the names look unused -- hence the
noqa markers. gym_bp itself lives in _blueprint.py so no domain module has to
import a sibling to reach it, which is what keeps these imports acyclic.

The re-exports at the bottom are not decoration. Eleven test call sites and
scripts/make_chart_fixture.py import these private helpers from
`features.gym.routes`, and keeping that path working is what let the 2912-line
routes.py split into this package without touching a single caller.
"""
from flask import abort, current_app, request

from ._blueprint import gym_bp

from . import helpers          # noqa: F401
from . import history          # noqa: F401
from . import workout          # noqa: F401
from . import partners         # noqa: F401
from . import session_admin    # noqa: F401
from . import reports          # noqa: F401
from . import catalogue        # noqa: F401
from . import exercise_detail  # noqa: F401
from . import push_routes      # noqa: F401

from .helpers import (         # noqa: F401
    _to_float, _to_increment, _to_int, _clean_muscle_group,
    _clean_equipment, _to_stack_steps, _clean_secondary_groups,
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
    _exercise_detail_payload, _chart_geometry, _default_position,
)
# Re-exported, not defined in this package: seeding.py owns it because
# sharing.py needs it too and cannot import a module that registers routes.
# Three tests import it from `features.gym.routes`, so the path has to survive.
from ..seeding import _last_full_performance                           # noqa: F401

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


__all__ = ['gym_bp']

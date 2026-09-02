"""The radar blueprint, alone in its own module.

Same pattern as the gym blueprint: every routes/ module imports radar_bp from
here rather than from the package, so importing one never pulls in the others.
That is the whole reason this file exists.
"""
from flask import Blueprint, abort, current_app, request

radar_bp = Blueprint('radar', __name__, url_prefix='/radar')


@radar_bp.before_request
def _require_csrf_on_writes():
    """Second defence layer on every radar write, behind SameSite=Lax --
    the gym blueprint's rule, copied rather than shared, because the two
    features share nothing on purpose.

    The token is auth.py's per-session one: board.html delivers it as
    <meta name="csrf-token">, the island sends it as X-CSRF-Token. Suites
    run with the gate open unless CSRF_STRICT is set, so tests do not each
    mint and thread a token; test_radar_watch_api.py pins the closed gate.
    """
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return
    if current_app.config.get('TESTING') and not current_app.config.get('CSRF_STRICT'):
        return
    from auth import _valid_csrf
    submitted = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
    if not _valid_csrf(submitted):
        abort(403)

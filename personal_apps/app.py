import datetime as dt
import os
import secrets

from dotenv import load_dotenv
from flask import Flask, abort, render_template, request, redirect, url_for
from flask_migrate import Migrate

from extensions import db

load_dotenv(override=True)

DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASS", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("PERSONAL_DB_NAME", "personal_apps")

app = Flask(__name__)

_secret_key = os.getenv("PERSONAL_SECRET_KEY")
if not _secret_key:
    import logging
    logging.getLogger().warning("PERSONAL_SECRET_KEY not set in .env — using random key, sessions reset on restart.")
    _secret_key = secrets.token_hex(32)

app.config['SECRET_KEY'] = _secret_key
app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:3306/{DB_NAME}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 3600,
}
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE']   = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
# Without a lifetime Flask issues a browser-session cookie, which a phone drops as soon as it
# evicts the browser — the gym tracker then asks for a password mid-workout. Login opts into
# this window (see auth.py); Flask re-stamps the cookie per request, so only idle time counts.
app.config['PERMANENT_SESSION_LIFETIME'] = dt.timedelta(days=30)

app.config['VAPID_PUBLIC_KEY']   = os.getenv("VAPID_PUBLIC_KEY")
app.config['VAPID_PRIVATE_KEY']  = os.getenv("VAPID_PRIVATE_KEY")
app.config['VAPID_CLAIMS_EMAIL'] = os.getenv("VAPID_CLAIMS_EMAIL", "mailto:michi7788@googlemail.com")

db.init_app(app)
migrate = Migrate(app, db)

from models import *
db.configure_mappers()

from auth import auth_bp, _is_logged_in, login_required, is_admin
from features.pubquiz.routes import pubquiz_bp
from features.tips.routes import tips_bp
from features.quizbank.routes import quizbank_bp
from features.gym.routes import gym_bp
from features.radar.routes import radar_bp

app.register_blueprint(auth_bp)
app.register_blueprint(pubquiz_bp)
app.register_blueprint(tips_bp)
app.register_blueprint(quizbank_bp)
app.register_blueprint(gym_bp)
app.register_blueprint(radar_bp)

# Gym templates call {{ vite_asset('exercise') }} for the content-hashed bundle
# built by `npm run build`. Raises rather than returning an empty src when the
# build has not run -- see vite_assets.py and DEPLOY_FRONTEND.md.
from vite_assets import resolve_asset
app.jinja_env.globals['vite_asset'] = resolve_asset


@app.after_request
def _immutable_hashed_assets(response):
    # The dist bundles carry their content hash in the filename, so a URL can
    # never mean different bytes -- a rebuild changes the name, not the file.
    # Flask's default (no-cache) made the browser revalidate every bundle on
    # every navigation for nothing. Scoped to dist/assets/: gym.css and sw.js
    # DO change in place and must keep revalidating.
    if request.path.startswith('/static/gym/dist/assets/'):
        # Werkzeug's static handler has already written no-cache; clear it
        # rather than appending after it.
        response.cache_control.no_cache = None
        response.cache_control.public = True
        response.cache_control.max_age = 31536000
        response.cache_control.immutable = True
    return response

# Hostname that should require login for every page (the "full access" domain).
# Other hostnames (e.g. the public pubquiz-only domain) are unaffected and keep
# whatever per-route protection each blueprint already defines.
FULL_ACCESS_HOST = os.getenv("PERSONAL_FULL_ACCESS_HOST", "mgemmel.viewdns.net")


# Blueprints a non-admin may reach. Everything else on the full-access host is
# the author's: the other three apps hold no per-user data and are not
# partitioned (see the multi-user design spec, decision 1).
_MEMBER_BLUEPRINTS = {'gym', 'auth'}


@app.before_request
def _require_login_on_full_access_host():
    if request.host.split(':')[0] != FULL_ACCESS_HOST:
        return
    if request.endpoint in ('auth.login', 'auth.logout', 'static', 'gym.gym_service_worker'):
        return
    if not _is_logged_in():
        return redirect(url_for('auth.login'))
    # `request.blueprint is None` for routes registered on the app itself --
    # which here is only `/`, and that route filters its own contents by
    # permission. Blocking it at the gate would 403 the overview page for the
    # very user it is being filtered for.
    if not is_admin() and request.blueprint is not None and request.blueprint not in _MEMBER_BLUEPRINTS:
        abort(403)


APPS = [
    {
        'name': 'Pub Quiz',
        'description': 'Ergebnisse und Verwaltung der Pub Quiz Abende.',
        'icon': '🍻',
        'url': '/pubquiz',
    },
    {
        'name': 'Trinkgeld Tracker',
        'description': 'Schichten, Trinkgeld und Statistiken für den Lieferjob.',
        'icon': '🛵',
        'url': '/tips',
    },
    {
        'name': 'Quiz Archiv',
        'description': 'Besuchte Pub Quizzes und Fragen erfassen und auswerten.',
        'icon': '🧠',
        'url': '/quizbank',
    },
    {
        'name': 'Gym Tracker',
        'description': 'Workouts, Sätze und Fortschritt verfolgen.',
        'icon': '🏋️',
        'url': '/gym',
    },
]


@app.route('/')
@login_required
def index():
    # A non-admin's landing page lists the one app they can open, rather than
    # four tiles of which three would 403.
    visible = APPS if is_admin() else [a for a in APPS if a['url'] == '/gym']
    return render_template('overview.html', apps=visible)


if __name__ == '__main__':
    # The reloader is on: without it, a Python edit is silently served by the
    # old process, which produces the worst possible symptom -- the browser
    # 500s or renders stale markup while the test suite passes, because the
    # tests import the current module and the server does not.
    #
    # Nothing here starts work at import time (the notifier is its own process,
    # run_gym_notifier.py), so the reloader's double-start is harmless.
    app.run(host='0.0.0.0', debug=True, use_reloader=True, port=5000)

import os
import secrets

from dotenv import load_dotenv
from flask import Flask, redirect, url_for
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

db.init_app(app)
migrate = Migrate(app, db)

from models import *
db.configure_mappers()

from auth import auth_bp
from features.pubquiz.routes import pubquiz_bp

app.register_blueprint(auth_bp)
app.register_blueprint(pubquiz_bp)


@app.route('/')
def index():
    return redirect(url_for('pubquiz.pubquiz'))


if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, port=5001)

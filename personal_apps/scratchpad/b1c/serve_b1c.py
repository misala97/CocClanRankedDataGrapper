"""Loopback-only B1C preview; never seed or alter the database."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app import app
from extensions import db
with app.app_context():
    if db.engine.url.database != 'personal_apps_radar_b1c':
        raise SystemExit('Refusing non-B1C preview database')
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5021, use_reloader=False)

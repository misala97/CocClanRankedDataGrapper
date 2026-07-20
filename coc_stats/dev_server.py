"""Local preview / dev entry point.

Importing `app` runs the module-level setup but NOT app.py's `if __name__ ==
'__main__'` block, so this deliberately skips the live Clash API sync that a
plain `python app.py` performs on startup. Serves on the harness-assigned
$PORT (falls back to 5050) with template hot-reload, so it never collides with
a real `python app.py` instance already holding port 5000.

Standalone dev helper — the production/real run is still `python app.py`.
"""
import os
from app import app

if __name__ == '__main__':
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.jinja_env.auto_reload = True
    app.run(
        host='127.0.0.1',
        port=int(os.environ.get('PORT', 5050)),
        debug=False,
        use_reloader=False,
    )

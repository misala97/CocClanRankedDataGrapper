"""The Jinja side of the Vite build.

The VPS deploy does `git reset --hard origin/main` and then builds, so a
missing manifest means the build did not run -- it must fail loudly at render
time rather than emitting a <script src=""> that 404s silently.

The manifest key format is Vite's own: paths relative to the Vite root, which
vite.config.ts leaves at personal_apps/. Verified against a real build.
"""
import json
import os

import pytest

from vite_assets import ViteManifestError, resolve_asset


def _write_manifest(tmp_path, mapping):
    manifest = tmp_path / '.vite' / 'manifest.json'
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps(mapping), encoding='utf-8')


def test_resolves_hashed_filename(tmp_path):
    _write_manifest(tmp_path, {
        'static/gym/src/entries/exercise.tsx': {'file': 'assets/exercise-a1b2c3d4.js'},
    })

    assert resolve_asset('exercise', dist_dir=tmp_path) == \
        '/static/gym/dist/assets/exercise-a1b2c3d4.js'


def test_missing_manifest_raises(tmp_path):
    with pytest.raises(ViteManifestError, match='npm run build'):
        resolve_asset('exercise', dist_dir=tmp_path)


def test_unknown_entry_raises(tmp_path):
    _write_manifest(tmp_path, {})

    with pytest.raises(ViteManifestError, match='exercise'):
        resolve_asset('exercise', dist_dir=tmp_path)


def test_a_rebuild_invalidates_the_cache(tmp_path):
    """`flask run` carries no reloader unless --debug is passed, and
    .claude/launch.json does not pass it. A cache that ignored the manifest's
    mtime kept serving the previous build's hashed filename after `npm run
    build`; Vite empties outDir, so that file is gone and the page loads a 404
    for its bundle -- blank screen, no error where anyone is looking."""
    manifest = tmp_path / '.vite' / 'manifest.json'
    manifest.parent.mkdir(parents=True)
    key = 'static/gym/src/entries/exercise.tsx'

    manifest.write_text(json.dumps({key: {'file': 'assets/exercise-OLD.js'}}), encoding='utf-8')
    first = resolve_asset('exercise', dist_dir=tmp_path)
    assert first.endswith('exercise-OLD.js')

    manifest.write_text(json.dumps({key: {'file': 'assets/exercise-NEW.js'}}), encoding='utf-8')
    # A same-second rewrite can land on an identical mtime on coarse
    # filesystems, which would make this pass for the wrong reason.
    os.utime(manifest, (0, 0))

    assert resolve_asset('exercise', dist_dir=tmp_path).endswith('exercise-NEW.js')


def test_resolves_against_the_real_build(tmp_path):
    """Guards the key format against a Vite upgrade changing it. Skips rather
    than fails when dist/ is absent, because a fresh checkout has not built
    yet and this suite must stay runnable without Node."""
    from vite_assets import _DIST
    if not (_DIST / '.vite' / 'manifest.json').exists():
        pytest.skip('no build present; run `npm run build` in personal_apps/')

    url = resolve_asset('exercise')
    assert url.startswith('/static/gym/dist/assets/exercise-')
    assert url.endswith('.js')


def _skip_without_build():
    from vite_assets import _DIST
    if not (_DIST / '.vite' / 'manifest.json').exists():
        pytest.skip('no build present; run `npm run build` in personal_apps/')


# The seam between resolve_asset() and the templates that will call it. The
# function above is well covered on its own, but app.py wiring it into
# jinja_env.globals is a separate step that nothing else exercises -- no
# template calls vite_asset() until the exercise page is ported, so without
# these a broken registration would sit undetected until then.

def test_the_jinja_global_is_registered():
    from app import app as flask_app
    from vite_assets import resolve_asset as registered

    assert flask_app.jinja_env.globals.get('vite_asset') is registered


def test_a_template_resolves_a_bundle():
    _skip_without_build()
    from app import app as flask_app

    rendered = flask_app.jinja_env.from_string(
        "<script src=\"{{ vite_asset('exercise') }}\"></script>").render()

    assert 'src="/static/gym/dist/assets/exercise-' in rendered


def test_a_template_typo_fails_loudly():
    """A missing entry must raise, not render an empty src. A <script src="">
    re-requests the page itself and fails silently -- the page would look
    merely broken rather than telling anyone why."""
    _skip_without_build()
    from app import app as flask_app

    with pytest.raises(ViteManifestError, match='nosuchentry'):
        flask_app.jinja_env.from_string("{{ vite_asset('nosuchentry') }}").render()


def test_hashed_bundles_are_served_immutable():
    """The dist assets carry their content hash in the filename, so the same
    URL can never mean different bytes -- revalidating them on every
    navigation buys nothing. Everything else under /static keeps Flask's
    default no-cache, because gym.css and sw.js DO change in place."""
    import glob
    import os
    from app import app as flask_app

    bundle = os.path.basename(glob.glob(
        os.path.join(flask_app.root_path, 'static', 'gym', 'dist', 'assets', '*.js'))[0])
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as client:
        hashed = client.get(f'/static/gym/dist/assets/{bundle}')
        plain = client.get('/static/gym/gym.css')
    assert hashed.status_code == 200
    assert hashed.headers['Cache-Control'] == 'public, max-age=31536000, immutable'
    assert 'immutable' not in (plain.headers.get('Cache-Control') or '')

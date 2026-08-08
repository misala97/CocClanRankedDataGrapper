"""The Jinja side of the Vite build.

The VPS deploy does `git reset --hard origin/main` and then builds, so a
missing manifest means the build did not run -- it must fail loudly at render
time rather than emitting a <script src=""> that 404s silently.

The manifest key format is Vite's own: paths relative to the Vite root, which
vite.config.ts leaves at personal_apps/. Verified against a real build.
"""
import json

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


def test_resolves_against_the_real_build(tmp_path):
    """Guards the key format against a Vite upgrade changing it. Skips rather
    than fails when dist/ is absent, because a fresh checkout has not built
    yet and this suite must stay runnable without Node."""
    from vite_assets import _DIST
    if not (_DIST / '.vite' / 'manifest.json').exists():
        pytest.skip('no build present; run `npm run build` in personal_apps/')

    url = resolve_asset('smoke')
    assert url.startswith('/static/gym/dist/assets/smoke-')
    assert url.endswith('.js')

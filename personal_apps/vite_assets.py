"""Resolve Vite's hashed bundle filenames for Jinja.

Vite content-hashes every entry, so the template cannot name the file. The
build writes `.vite/manifest.json` mapping source paths to output paths; this
reads it.

Manifest keys are paths relative to the Vite root, which every config leaves
at this directory -- so an entry is keyed 'static/<feature>/src/entries/<name>.tsx'.
Root is deliberately not pointed at the src directory, because that would put
build.outDir outside the root and make Vite warn on every build.

There is one build per feature, each with its own config, outDir and manifest
(vite.config.ts for gym, vite.radar.config.ts for radar). One shared bundle
directory was the alternative and was rejected: gym's service worker caches
its own dist by path prefix, and a second feature's chunks landing in there
would be cached for a page that never loads them.

The manifest is cached, keyed on its own mtime. In production it never changes
while the process lives -- the VPS deploy rebuilds and then restarts the
service -- so this is a plain memo there.

In development it matters more than it looks. `flask run` carries no reloader
unless --debug is passed, and .claude/launch.json does not pass it, so a cache
that ignored mtime would keep serving the previous build's hashed filename
after `npm run build`. Vite empties outDir, so that filename is gone: the page
loads a 404 for its bundle, React never mounts, and the screen goes blank with
no error anywhere the developer is looking. Found exactly that way.
"""
import json
from pathlib import Path

_STATIC = Path(__file__).parent / 'static'
_DIST = _STATIC / 'gym' / 'dist'
_cache: dict[tuple[str, float], str] = {}


class ViteManifestError(RuntimeError):
    """The bundle for an entry could not be resolved."""


def _record(entry: str, dist_dir: Path | None, feature: str) -> tuple[dict, Path]:
    dist = dist_dir or (_STATIC / feature / 'dist')
    manifest_path = dist / '.vite' / 'manifest.json'
    if not manifest_path.exists():
        raise ViteManifestError(
            f'No Vite manifest at {manifest_path}. Run `npm run build` in '
            f'personal_apps/ -- on the VPS this runs after `git reset --hard`, '
            f'which deletes the untracked dist/ directory.')

    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    key = f'static/{feature}/src/entries/{entry}.tsx'
    record = manifest.get(key)
    if record is None:
        raise ViteManifestError(
            f'Entry {entry!r} (looked for {key!r}) is not in the Vite '
            f'manifest. Add it to rollupOptions.input in the Vite config '
            f'for feature {feature!r}.')
    return record, manifest_path


def resolve_asset(entry: str, dist_dir: Path | None = None,
                  feature: str = 'gym') -> str:
    """URL path for a built entry, e.g. resolve_asset('exercise').

    `entry` is the basename under static/<feature>/src/entries/, without
    extension. `feature` defaults to gym because it was the only one when this
    was written and every gym template calls it unqualified.
    """
    dist = dist_dir or (_STATIC / feature / 'dist')
    record, manifest_path = _record(entry, dist_dir, feature)
    cache_key = (f'{dist}:{entry}', manifest_path.stat().st_mtime)
    if cache_key in _cache:
        return _cache[cache_key]
    url = f'/static/{feature}/dist/{record["file"]}'
    _cache[cache_key] = url
    return url


def resolve_asset_css(entry: str, dist_dir: Path | None = None,
                      feature: str = 'gym') -> list[str]:
    """URL paths for the stylesheets an entry imports, hashed like its bundle.

    An entry whose module graph imports a `.css` file gets it emitted as a
    separate asset rather than injected at runtime, and the manifest lists it
    under `css`. A template that linked only the script would render the page
    unstyled -- with no error anywhere, because the bundle loads fine.

    Empty for an entry that imports no CSS, which is every gym entry and the
    radar board: their stylesheets are plain <link> tags on unhashed files.
    """
    record, _ = _record(entry, dist_dir, feature)
    return [f'/static/{feature}/dist/{href}' for href in record.get('css', [])]

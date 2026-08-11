"""Resolve Vite's hashed bundle filenames for Jinja.

Vite content-hashes every entry, so the template cannot name the file. The
build writes `.vite/manifest.json` mapping source paths to output paths; this
reads it.

Manifest keys are paths relative to the Vite root, which vite.config.ts leaves
at this directory -- so an entry is keyed 'static/gym/src/entries/<name>.tsx'.
Root is deliberately not pointed at static/gym/src, because that would put
build.outDir outside the root and make Vite warn on every build.

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

_DIST = Path(__file__).parent / 'static' / 'gym' / 'dist'
_cache: dict[tuple[str, float], str] = {}


class ViteManifestError(RuntimeError):
    """The bundle for an entry could not be resolved."""


def resolve_asset(entry: str, dist_dir: Path | None = None) -> str:
    """URL path for a built entry, e.g. resolve_asset('exercise').

    `entry` is the basename under static/gym/src/entries/, without extension.
    """
    dist = dist_dir or _DIST
    manifest_path = dist / '.vite' / 'manifest.json'
    if not manifest_path.exists():
        raise ViteManifestError(
            f'No Vite manifest at {manifest_path}. Run `npm run build` in '
            f'personal_apps/ -- on the VPS this runs after `git reset --hard`, '
            f'which deletes the untracked dist/ directory.')

    cache_key = (f'{dist}:{entry}', manifest_path.stat().st_mtime)
    if cache_key in _cache:
        return _cache[cache_key]

    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    key = f'static/gym/src/entries/{entry}.tsx'
    record = manifest.get(key)
    if record is None:
        raise ViteManifestError(
            f'Entry {entry!r} (looked for {key!r}) is not in the Vite '
            f'manifest. Add it to rollupOptions.input in vite.config.ts.')

    url = f'/static/gym/dist/{record["file"]}'
    _cache[cache_key] = url
    return url

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
_manifests: dict[tuple[str, float], dict] = {}


class ViteManifestError(RuntimeError):
    """The bundle for an entry could not be resolved."""


def _manifest(dist: Path) -> dict:
    """The parsed manifest, memoised on its own mtime.

    The read and the JSON parse happen on a miss and not on every call. That
    is the whole point of the memo: in production the file never changes while
    the process lives, and re-reading it per template tag would put a stat, a
    read and a parse on every page render of both features.
    """
    manifest_path = dist / '.vite' / 'manifest.json'
    if not manifest_path.exists():
        raise ViteManifestError(
            f'No Vite manifest at {manifest_path}. Run `npm run build` in '
            f'personal_apps/ -- on the VPS this runs after `git reset --hard`, '
            f'which deletes the untracked dist/ directory.')
    cache_key = (f'{dist}:manifest', manifest_path.stat().st_mtime)
    cached = _manifests.get(cache_key)
    if cached is None:
        cached = json.loads(manifest_path.read_text(encoding='utf-8'))
        # Only this dist's older entries. Clearing the whole dict evicted the
        # other feature's manifest, so gym and radar pages alternating gave a
        # 100% miss rate -- a stat, a read and a parse per render, which is
        # the cost this memo exists to remove.
        for stale in [key for key in _manifests if key[0] == cache_key[0]]:
            del _manifests[stale]
        _manifests[cache_key] = cached
    return cached


def _record(entry: str, dist_dir: Path | None, feature: str) -> dict:
    dist = dist_dir or (_STATIC / feature / 'dist')
    key = f'static/{feature}/src/entries/{entry}.tsx'
    record = _manifest(dist).get(key)
    if record is None:
        raise ViteManifestError(
            f'Entry {entry!r} (looked for {key!r}) is not in the Vite '
            f'manifest. Add it to rollupOptions.input in the Vite config '
            f'for feature {feature!r}.')
    return record


def resolve_asset(entry: str, dist_dir: Path | None = None,
                  feature: str = 'gym') -> str:
    """URL path for a built entry, e.g. resolve_asset('exercise').

    `entry` is the basename under static/<feature>/src/entries/, without
    extension. `feature` defaults to gym because it was the only one when this
    was written and every gym template calls it unqualified.
    """
    return f'/static/{feature}/dist/{_record(entry, dist_dir, feature)["file"]}'


def resolve_asset_css(entry: str, dist_dir: Path | None = None,
                      feature: str = 'gym') -> list[str]:
    """URL paths for the stylesheets an entry imports, hashed like its bundle.

    An entry whose module graph imports a `.css` file gets it emitted as a
    separate asset rather than injected at runtime, and the manifest lists it
    under `css`. A template that linked only the script would render the page
    unstyled -- with no error anywhere, because the bundle loads fine.

    Empty for an entry that imports no CSS, which is every gym entry and the
    radar board: their stylesheets are plain <link> tags on unhashed files.

    Imported chunks are followed too. Rollup may move a shared stylesheet onto
    a chunk the entry imports rather than onto the entry itself, and reading
    only the entry's own `css` would then return nothing and render the page
    unstyled -- the exact failure this exists to prevent.
    """
    dist = dist_dir or (_STATIC / feature / 'dist')
    manifest = _manifest(dist)
    seen: list[str] = []
    pending = [f'static/{feature}/src/entries/{entry}.tsx']
    visited: set[str] = set()
    # Raises for an unknown entry, with the message that names the config.
    _record(entry, dist_dir, feature)
    while pending:
        key = pending.pop()
        if key in visited:
            continue
        visited.add(key)
        record = manifest.get(key)
        if record is None:
            continue
        for href in record.get('css', []):
            if href not in seen:
                seen.append(href)
        pending.extend(record.get('imports', []))
        pending.extend(record.get('dynamicImports', []))
    return [f'/static/{feature}/dist/{href}' for href in seen]

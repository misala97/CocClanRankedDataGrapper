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


def _record(entry: str, dist_dir: Path | None, feature: str, ext: str = 'tsx') -> dict:
    dist = dist_dir or (_STATIC / feature / 'dist')
    key = f'static/{feature}/src/entries/{entry}.{ext}'
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


_versions: dict[tuple[str, float], str] = {}


def versioned_static(filename: str) -> str:
    """url_for('static') with `?v=` the file's content hash, for a file the
    build does not take through (gym.js: a classic script in <head>, which a
    module bundle could not stand in for). app._immutable_hashed_assets caches
    such a URL for good; the hash is memoised on the file's mtime."""
    from flask import url_for
    path = _STATIC / filename
    key = (filename, path.stat().st_mtime)
    version = _versions.get(key)
    if version is None:
        import hashlib
        version = hashlib.md5(path.read_bytes()).hexdigest()[:8]
        _versions[key] = version
    return url_for('static', filename=filename, v=version)


def resolve_style(entry: str, dist_dir: Path | None = None,
                  feature: str = 'gym') -> str:
    """URL path for a stylesheet built as an entry of its own,
    static/<feature>/src/entries/<entry>.css -- e.g. resolve_style('styles').

    Built rather than linked as written: the build minifies it and hashes its
    name, so it can be cached for good like the bundles (walkthrough G-094,
    G-142)."""
    return f'/static/{feature}/dist/{_record(entry, dist_dir, feature, "css")["file"]}'


def resolve_built(source: str, dist_dir: Path | None = None,
                  feature: str = 'gym') -> str:
    """URL path for a file the build hashed on the way through, by its source
    path -- a font a stylesheet names, e.g.
    resolve_built('static/gym/fonts/figtree-latin.woff2').

    A preload must name the very URL the stylesheet asks for, or the browser
    fetches the file twice."""
    dist = dist_dir or (_STATIC / feature / 'dist')
    record = _manifest(dist).get(source)
    if record is None:
        raise ViteManifestError(
            f'{source!r} is not in the Vite manifest: nothing the build '
            f'processes for feature {feature!r} refers to it.')
    return f'/static/{feature}/dist/{record["file"]}'


def resolve_preloads(entry: str, dist_dir: Path | None = None,
                     feature: str = 'gym') -> list[str]:
    """URL paths of every chunk an entry imports statically, for
    <link rel="modulepreload">.

    Without them the browser learns of an entry's imports only once it has
    fetched and parsed the entry, and then of their imports after those: a
    waterfall of up to a dozen files on the session page (G-142). Dynamic
    imports are left out -- they load on demand by design."""
    dist = dist_dir or (_STATIC / feature / 'dist')
    manifest = _manifest(dist)
    found: list[str] = []
    pending = list(_record(entry, dist_dir, feature).get('imports', []))
    while pending:
        key = pending.pop(0)
        record = manifest.get(key)
        if record is None or record['file'] in found:
            continue
        found.append(record['file'])
        pending.extend(record.get('imports', []))
    return [f'/static/{feature}/dist/{href}' for href in found]

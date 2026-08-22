# Deploying the frontend builds

Two features ship React islands built by Vite: the gym pages and the radar
board. Each has its own config, its own `dist/`, and its own manifest —
`vite.config.ts` writing `static/gym/dist/`, and `vite.radar.config.ts`
writing `static/radar/dist/`. Both are **gitignored** and must be built on the
VPS after every pull.

One `npm run build` covers both (it chains the two configs), so **the deploy
script does not change when a feature is added** — only this repository does.
The same is true of `npm test`.

This file documents a change to the deploy script, which lives on the VPS and
is not in this repository. **Michi runs these steps; they are not automated
from here.**

## One-time setup on the VPS

Install **Node 24 LTS**, then:

```bash
cd /root/coc-stats/personal_apps && npm ci
```

Vite's floor is `^20.19 || >=22.12`, but do not aim for the floor: Node 20
reached end of life in April 2026, so it no longer receives security patches.
24 is the current LTS and matches the development machine.

`npm ci` on npm 11 blocks package install scripts by default and will warn that
esbuild's `postinstall` was skipped. That is fine and needs no action — modern
esbuild ships its platform binary as an optional dependency, and the build was
verified to work with the script blocked. Do not run `npm approve-scripts`
without a reason to.

## The deploy script change

Add one step, **after** `git fetch --all && git reset --hard origin/main` and
after `pip install -r requirements.txt`, and **before** the
`personal_apps_web` restart:

```bash
cd /root/coc-stats/personal_apps && npm ci && npm run build
```

`npm ci` rather than `npm install`: it installs exactly `package-lock.json` and
fails instead of silently resolving a different tree.

### Why the order matters

`git reset --hard` deletes untracked files, and both `dist/` directories are
untracked. Building before the reset would have the output wiped. Building
after the restart would leave the service serving a missing bundle in the
window between.

`npm run build` runs `tsc --noEmit` first, so a type error fails the deploy
rather than shipping.

## Failure mode

If the build does not run, **every gym page** raises `ViteManifestError` with a
message naming the fix. All eight are islands now, so there is no partly-working
state to misread: the gym is either up or entirely down. It fails loudly and
identically on every page — a 500, not a blank screen.

That is deliberate. The alternative, emitting `<script src="">`, makes the
browser re-request the page itself as a script: no error anywhere, just a page
that renders nothing. Verify the build succeeded before restarting the
service.

## Rollback

```bash
cd /root/coc-stats && git reset --hard <previous-sha>
cd personal_apps && npm ci && npm run build
systemctl restart personal_apps_web
```

The build must be re-run after any reset, for the same reason as above.

## Local development

Same build, no server restart needed:

```bash
cd personal_apps && npm run build
```

`vite_assets.resolve_asset` keys its cache on the manifest's mtime, so a
running `flask run` picks up the new hashed filename on the next request.
Without that it would keep serving the previous build's filename, which Vite
has already deleted — a blank page with nothing in the server log.

Template and Python changes still need a restart: `flask run` carries no
reloader unless `--debug` is passed, and `.claude/launch.json` does not pass
it.

## Which pages are built

One Vite entry per ported page, listed in `vite.config.ts` under
`rollupOptions.input`. Today: `exercise` only. Each further page in the port
adds its own entry there and its own `{{ vite_asset('<name>') }}` in the
template — an entry missing from the config raises `ViteManifestError` naming
the entry and the file to add it to.

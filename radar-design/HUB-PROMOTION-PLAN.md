# Hub promotion — binding implementation brief

2026-09-14. Owner approved implementation planning and local implementation; deployment remains a later decision. Baseline: deployed 83bc2bf6282b7772fbee07c1eb27cfe41760f417. Human Chatter ranking is closed; do not reopen it.

## Product decision

Make /radar/ the hub entry, retaining the hub's existing Overview landing for a bare URL. Preserve /radar/hub/ as a working compatibility alias in this increment; serve the same hub without introducing a permanent redirect. Move the original board UI to /radar/legacy/ with its original behavior. Provide a discreet Legacy Radar link and a return-to-hub link. Do not delete legacy UI/backend or redesign any page.

Existing bookmarks retain meaningful context. Inspect the old ?t= selected-company contract and other query/span/filter formats. Map valid legacy company links at /radar/ to the matching hub research/chatter destination, preserving valid selection context. An explicit valid hub destination takes precedence over legacy t; malformed values must recover without blank pages. Bare /radar/ opens existing hub Overview; old board-filter-only bookmarks should open Human Chatter with supported filters. Do not promise legacy divergence ordering on the new Human Chatter surface: retain exact legacy behavior at /radar/legacy/.

## Bounded execution

1. Create a new isolated codex/ worktree from verified deployed/integration HEAD. Carry current uncommitted planning documents explicitly. Preserve integration and B1C worktrees and port 5021.
2. Produce a small parity/URL matrix from actual source and tests: discovery/filtering, research links, watches, explicit sorting, activity/admin access and mobile navigation. Identify important old-only capabilities. Preserve access through Legacy Radar; only a material loss without a usable fallback requires a product ruling. Do not turn this into a feature rewrite or broad audit.
3. Add regression tests for route ownership, authentication and old/new bookmark mapping. Implement root hub, compatibility alias, legacy route and links using shared existing rendering behavior. Preserve query context and valid fragments, login return URLs, admin authorization and BadQuery recovery. Relative API/asset URLs must work from all three routes. No redirect loops or permanent redirect caching.
4. Test actual-app desktop/mobile on an approved isolated preview. Check root landing, Human Chatter chatter sort, company bookmark, explicit hub hashes, Back/Forward, refresh, signed-out login return, legacy default API sort and valid filters, user/admin visibility, assets and missing-data recovery. Use Python Playwright and inspect screenshots. Preserve ranking/cache/producer contracts and legacy backend defaults; no need to repeat a statistical audit.
5. Run focused route/navigation/hub regression suites and build/typecheck. Use only an approved registered disposable DB for any destructive integration tests; reuse documented release-verification provisioning rather than bypassing guards or using B1C's DB. Read prior verification artifacts for methodology, not as proof of this change.
6. Return local candidate with exact branch/HEAD/dirty ownership, capability/URL matrix, commands/results, screenshots, limitations, and rollback description. Update HUB-PROMOTION-LEDGER.md and HANDOFF.md. Owner selects independent final reviewer; stop before deployment.

## Acceptance

/radar/ mounts hub; /radar/hub/ remains functional; /radar/legacy/ mounts original board. Old company/selection bookmarks resolve meaningfully; explicit valid hub destination wins. Root/hub authentication and API permissions remain intact. Human Chatter default remains price-independent sort=chatter; legacy retains its default behavior. No duplicate frontend fork, provider/migration/capture change, deleted functionality, shared-backend rewrite or port-5021 use. Latest ranking release remains production until separately authorized deployment.

## Continuity

Source workspace C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-human-chatter-integration. Post-release docs are intentionally uncommitted; do not commit that source workspace merely to carry them. Keep plan, ledger and root handoff together in the new feature worktree. No push, merge-main, deployment, capture activation or schema migration is authorized by this brief. Old-UI deletion is a separate future task.

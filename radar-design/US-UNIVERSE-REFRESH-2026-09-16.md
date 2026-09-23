# Manual US universe refresh and roadmap update — 2026-09-16

## Current status — 2026-09-18

The exact 146/51/87 cohorts and current database state are now reconstructed and accepted under `B-US-UNIVERSE-EVIDENCE-2-RULING.md`. Workstream B evidence is complete; implementation is not started or authorized. The historical import below remains complete and must not be rerun.

## Executed owner-authorized manual import
Production HEAD f632e5db5dd92e27480cbfccdf7b0638b26533ed, /root/coc-stats. Owner explicitly requested running the existing manual importer; this was a bounded operational exception to the planning-only role, not authorization for implementation/deployment/training.

Fresh official Nasdaq Trader files from https://www.nasdaqtrader.com/dynamic/symdir/:
- nasdaqlisted.txt: creation 0915202618:01, 5,600 usable rows; SHA256 bd5524e05ab8530c482882df7f9eb109b9a9f96cf73dd67872ee911251262ddd.
- otherlisted.txt: creation 0915202618:01, 7,058 usable rows; SHA256 861023735ffebda2ede5059070f622d8ba2fb54175e78e5d73275b2701bd9b96.
- 12,658 unique incoming rows after the existing parser's exclusions (test issues, nonalphabetic or >5-character symbols). This is not every exchange-listed security.

Before changes, all universe rows were backed up as JSON in /root/radar-universe-refresh-20260916/universe-before.json; files/hashes/preflight.json retained in that directory. Backup contains original values but is not an automatically executable rollback script. No secrets printed.

Executed from /root/coc-stats/personal_apps:
/root/coc-stats/venv/bin/python scripts/seed_radar_universe.py /root/radar-universe-refresh-20260916/nasdaqlisted.txt /root/radar-universe-refresh-20260916/otherlisted.txt

Exit 0: 146 added, 51 updated, 0 reassigned, 0 fund flags set. 87 existing rows absent from incoming files retained: importer does not perform delisting reconciliation. Total active universe after: 12,745 (12,599 + 146). Both radar_ingest and personal_apps_web active after import. No restart or code deployment.

## Newly confirmed maintenance gap
Only 12,599 active symbols have mapped US instruments after import. All 146 new ticker identities lack those instrument rows. The manual importer does not create/update price instruments; price polling requires mapped primary instrument rows. Do not claim the new symbols already have usable prices. The 51 name/exchange changes also need consistency checked against instruments. DE-only mapped active tickers remain zero, DE mapped tickers 2,517, DE instrument rows 3,229.

Earlier blanket statement 'all current symbols mapped US' described the pre-import snapshot and is now superseded. None became EU-only; 146 have no price mapping yet.

## Current ordered plan
1. **Radar A is complete.** Active DE/EUR providers, refresh jobs, selectors, displays and fallback/config paths were removed in release `0fdad73`; protected historical rows and schema remain preserved. The 146 new US identities and 51 changed entries were deliberately left to workstream B and must not be redispatched as A.
2. **Workstream B is next but not started.** First reconcile the 146 unmapped identities and 51 changed entries and explicitly assess the 87 absent listings. Then plan automatic US symbol maintenance: daily official directory refresh; validation of both complete inputs before mutation; reconciliation of US primary instruments together with ticker identities; auditable counts/errors; and safe handling of removals, renames/reassignments and temporary or incomplete downloads. Do not mass-delist based on a failed or partial response. Define absent-symbol handling explicitly and retain history.
3. Selected-price C is complete and live with charts ON, Alpaca ON and Yahoo OFF. Do not repeat its implementation, review, provider validation or deployment gates.
4. Encoder improvement remains separate, after the universe work unless the owner reprioritizes. First audit fresh mistakes and label readiness, then prepare a bounded labeling/training proposal; do not automatically retrain.

## Encoder finding
Read complete latest deployment tail of C:/Users/michi/Desktop/CodingStuff/docs/superpowers/specs/2026-09-08-judge-hard-negatives-retrain.md (missing from this worktree; original preserved). It records hard-negative/new-shape retraining and deployment on 2026-09-08 22:35 UTC. Production active.json freshly reads path v3/, backend id radar-encoder-v1. The pointer is verified; model bytes were not rehashed or reevaluated this turn.

The completed retrain targeted false stock mentions/ordinary-word collisions. Do not repeat it as pending work. Remaining Phase 2: combine attitude and expected_move into a direction head with explicit no-direction class, and collect a targeted directional label wave (historical corpus had only 127 flat and 424 mixed examples). It requires new implementation/evaluation, not just pressing train.

Existing labels-*.jsonl in C:/Users/michi/Desktop/radar_labels were last modified Sep 5–8; no newer labeled wave found in that inspected location. More collected posts are not automatically verified training labels. Never use the encoder's own guesses as independent ground truth. Readiness and paid labeling size, GPU memory/time/timing require a concrete scoped proposal and owner choice. No labeling/model calls, GPU job, retrain, artifact swap or model deployment this turn.

## Continuity
Mastermind owns this report, local operational scripts, and current-notice edits only. No application/test changes, worker dispatch, commit, EUR removal, DB deletion, production config edits or provider activation. Local scripts: artifacts/md-selected-price-personal-preview/universe_refresh_preflight.py and count_market_coverage.py. Preserve all prior dirty documents/evidence. User/model picks and self-contained worker-return prompts remain required.

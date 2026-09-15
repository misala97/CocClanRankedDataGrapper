# MD-SELECTED-PRICE-REVIEW-1 — Mastermind ruling

2026-09-15. Independent review COMPLETE and accepted with qualifications. One bounded correction MD-SELECTED-PRICE-CORRECTION-1 is PREPARED, NOT DISPATCHED. No final feature acceptance, activation or release. HA1 stays COMPLETE / DEPLOYED / CLOSED.

## Evidence and ownership

Candidate C:/Users/michi/Desktop/CodingStuff/.worktrees/radar-selected-price-charts; branch codex/radar-selected-price-charts; base/current HEAD daadf3868caedcb5db858378e919cba68b735f8a. Mastermind verified current branch/HEAD/status, read the review and saved D17 probe, inspected implicated code/spec, and rehashed all 48 recorded application/test/generated files: zero mismatches against fingerprint 218c1a53aaef9625dd9ec6f8b2c6125d8431b3c42daad732a9181a8b2f612159. Git ignore-file permission warning limits exhaustive untracked enumeration. Working tree is intentionally dirty; review wording 'Git status/diff clean' means diff check passed, not a clean checkout.

139 backend/180 focused frontend passes, regression 269 pass/1 skip/3 known failures, typecheck and identical scratch build are Reviewer-executed evidence. Saved 57-case/744-check browser run remains Implementer-executed, inspected by Reviewer. Mastermind ran no application tests, provider/DB/production operations. Review is sufficient; do not repeat it wholesale.

## Binding decisions

### F1 + F2: correct together, option b

Use an explicit fresh-interpreter module subprocess with a minimal environment for the production fetch child. This replaces SPEC section 6's multiprocessing-spawn mechanism, while retaining all isolation, deadline, cache, quota and cleanup requirements. Do not re-execute the parent launcher, load dotenv, import Flask/models/DB, inherit parent sessions/credentials or mutate the parent environment. No shell command construction. Preserve one supervisor/one child, no queue, bounded IPC/body/result, 6s startup-inclusive deadline, 1s cleanup/quarantine and request-thread isolation. Test actual production launcher transport with synthetic inputs, not just an injected multiprocessing target.

This is a bounded launcher/IPC correction, not an acquisition-system redesign. Preserve admission/cache/backoff logic and existing Yahoo caller defaults. Platform-required child environment entries must be explicitly allowlisted and documented; no blanket os.environ copy, inherited PYTHONPATH/PYTHONSTARTUP, proxy, provider, database or application secrets. Parent environment must remain unchanged.

Qualification: the review proves file-path re-execution and parent sentinel inheritance. It does not prove every module-named launcher safe: generic python -m is not a universal exemption from multiprocessing preparation. Do not promote the report's broad module-main sentence or inferred gunicorn behavior to tested fact. The corrected explicit child module removes reliance on parent launcher shape.

### F3: correct with a simple failure state

On terminal endpoint/refetch error, render the chart-local retry message even when TanStack retains previous data. Do not display old price/chatter/current-session/now labels while that error remains. Restore the chart on a successful response. Preserve server-returned valid stale/fallback payloads (HTTP 200), normal successful caching and feature-disabled/unsupported legacy fallback.

This chooses SPEC section 8's retryable-message branch without implementing a second client exchange calendar or guessing identity after a failed response. Reviewer suggestion of age <15min alone does not prove same identity/window across rollover/remap; it is insufficient. Adjust comments/tests accordingly. No query-key/calendar redesign.

### F4: correct names and disclose unknown topology

Rename the coordinator timestamp to coordinator_started_at end-to-end; null means coordinator not started. Do not call module import time OS process start. Keep PID and process-scope/reset note. Configured worker count is a positive explicit WEB_CONCURRENCY value when present, otherwise unknown; render Unknown explicitly in Admin and name the configuration source. Do not infer CLI --workers or hard-code 2. Later release verifies actual process count and reconciles configuration. This amends SPEC sections 6/7 to honest coordinator timing and known/unknown configured multiplier; it does not establish topology readiness. Update response types, parser, labels, docs and affected tests together.

### D5 and D14: closed, no fixes

D5: company.first_seen is the conservative chatter identity floor; instrument.mapped_at is the price mapping floor. Ticker-based chatter must not be erased by a pricing remap. This clarifies SPEC section 5's ambiguous company/mapping phrase, not permission to claim unavailable reassignment history.

D14: full long Retry-After governs admission; only response delay is capped at a day. No early provider retry allowed. Preserve passing behavior.

Optional polish (unreachable capped text, partial-session axis tick, standing identity caveat) deferred. No unrelated chart redesign, headline promotion, research, HA1 work or deployment.

## Execution and closure

Owner selects worker/model and pastes CORRECTION-1 prompt. One worker implements the above and returns focused proof. After return, only changed-behavior independent review is appropriate: child isolation/lifecycle, refresh-error rendering and ops contract; carry the unchanged review results. No full research/HA1/browser-suite cycle. Mandatory live Yahoo epoch/closed-session/usage-condition, MariaDB timeout/plans/pool and real topology limitations remain release carries, not new local correction gates.

This assessment owns this ruling, CORRECTION-1-PROMPT and latest candidate continuity notices only. All code, build, worker/reviewer evidence and source/other-worktree dirt preserved; local/uncommitted. Remote Control was separately started at owner's request; that is not worker dispatch or implementation authorization.
# Hub promotion ledger — 2026-09-14

Binding: HUB-PROMOTION-PLAN.md. Baseline deployed 83bc2bf6282b7772fbee07c1eb27cfe41760f417.

| Task | Status | Next evidence |
| --- | --- | --- |
| Product decision and bounded brief | COMPLETE | Root hub, /hub/ alias, /legacy/ fallback; no deletion |
| Isolated workspace and capability/URL matrix | COMPLETE | Root hub/alias; legacy board retains discovery, filters, watches, explicit sorting, research, activity/admin and mobile access |
| Routes, link compatibility and regression tests | COMPLETE | Root/alias/legacy ownership, login protection, `?t=` mapping, hash precedence and preserved valid filters covered |
| Focused validation and actual-app preview | COMPLETE | Fresh route suite 13, navigation/Hub 58, build passed; actual-app desktop/mobile on isolated 5033 passed and screenshots inspected. |
| Owner-selected independent review | COMPLETE WITH CORRECTION | Read-only review found filter-only bookmark issue; owner requested correction. Narrow regression failed before fix, then passed; no broad redispatch. |
| Deployment | AUTHORIZED / PENDING | Owner requested finishing and deploying; exact SHA/outcome follow. |
| Old UI retirement | DEFERRED | Separate cleanup after promotion acceptance |

Historical analysis resumes after this bounded transition. No new implementation agent dispatched by planner.

Preview note: the approved local procedure was started on port 5032 (port 5021 untouched), and the server answered `/login` with 200. The desktop/mobile Playwright invocation completed without producing its expected result or screenshot files, so no screenshot evidence is claimed. The retained script is `radar-design/artifacts/hub-promotion-preview/verify_preview.py`.

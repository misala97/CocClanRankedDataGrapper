# HA1 LOCAL-QA disposable environment — record

Owner: assignment HA1-US-DAILY-EXPLORE-LOCAL-QA (Implementer / local QA operator, Claude Opus 5, no subagents). Created 2026-09-15. Local, loopback-only, synthetic data only. No production copy, provider data, Docker, service, installer or global configuration.

## Tooling inspection (before creation)

- `C:\Program Files\MySQL\MySQL Server 8.0` (MySQL 8.0.46, Windows service `MySQL80`, listening `::`:3306 and 33060). NOT MariaDB; protected default 3306. Not used, not touched.
- No MariaDB service or installer. Docker Desktop CLI and WSL present — not used (no image pulls authorized).
- Existing portable binary tree (read-only source): `C:\Users\michi\AppData\Local\Temp\claude\c--Users-michi-Desktop-CodingStuff\1067a3f3-80ea-40f8-86f1-2098692a7340\scratchpad\mariadb\mariadb-10.11.14-winx64` (bin + share/charsets only, 27.7 MB, no data directory inside). Copied — not executed in place, not modified.

## Instance

| Item | Value |
| --- | --- |
| Root directory (new) | `C:\Users\michi\.radar-ha1-local-qa` |
| Executable | `C:\Users\michi\.radar-ha1-local-qa\mariadb-10.11.14-winx64\bin\mariadbd.exe` — `Ver 10.11.14-MariaDB for Win64 on AMD64 (mariadb.org binary distribution)`; launcher SHA-256 `869C8123B52FAFC587CA658765084B2AAA3D514570654571C72F9AFDB428ACAC` |
| server.dll SHA-256 | `F9E47A4EA2E2EEE39E2BEE95AE0F0D838246FADB8440A49AA3BD59DE0184FFF2` |
| Data directory (new) | `C:\Users\michi\.radar-ha1-local-qa\data` (initialized by `mariadb-install-db.exe --datadir --port=3461`) |
| Logs | `C:\Users\michi\.radar-ha1-local-qa\logs\` (`install-db.log`, `mariadbd.err`, preview server logs) |
| Bind / port | `127.0.0.1:3461` only (`@@bind_address=127.0.0.1`, `--skip-name-resolve`) |
| Database / user | `radar_ha1_localqa` (utf8mb4); user `ha1qa@127.0.0.1` with ALL on that database only |
| Target string | `127.0.0.1:3461/radar_ha1_localqa` |
| Dedicated registry | `C:\Users\michi\.radar-ha1-local-qa\registry.json` = `{"version": 1, "targets": ["127.0.0.1:3461/radar_ha1_localqa"]}` (no BOM) |
| Credentials | generated into `C:\Users\michi\.radar-ha1-local-qa\secrets.json` (root, ha1qa, local app admin, owned non-admin password); never printed or copied into the repository; loaded by `env.ps1` into process environment only |
| Setup / env scripts | `setup.ps1` (init + hidden start + DB/user), `env.ps1` (binds harness variables) |
| Process | `mariadbd.exe` PID recorded in `mariadbd.pid.json` (started hidden via `Start-Process -WindowStyle Hidden`, no service) |
| Schema | candidate migrations only (`flask_migrate.upgrade`, `env_migrate.py`): 47 tables, alembic head `b7e3f9c1a2d4` — local schema, not a production fact |
| Pre-existing rows after migration | `app_user` id 1 `admin` (created by a candidate migration), id 2 `zq-ha1-localqa-admin` (environment-owned local admin, `env_migrate.py`) |

Gate evidence: the first migration attempt was REFUSED by `local_runtime.gate()` with `cannot read the HA1 registry …: JSONDecodeError` (PowerShell 5.1 wrote a UTF-8 BOM); registry rewritten without BOM, then the gate and `destructive_target.require` passed.

Refused/avoided: DB 3306/3399, preview 5021/5033, B1C/promotion databases, existing data directories, other worktrees. Preview port 5061 was tried first and abandoned: Chromium blocks it (`net::ERR_UNSAFE_PORT`); the gated preview then ran on 5041.

## State at return

Stopped 2026-09-15 ~14:12 by `Stop-Process` on the recorded PID after matching the executable path (a hard stop: `mariadbd.err` shows aborted pooled connections; InnoDB crash recovery runs on the next start). No listener on 3461. Data 214.5 MB retained. Owned fixture rows: 0 in the four radar tables; `app_user` keeps migration `admin` (id 1) and environment `zq-ha1-localqa-admin` (id 2).

## FINAL-UI-CHECK use (appended 2026-09-15; history above unchanged)

Restarted with `setup.ps1 -StartOnly` (PID 36868). InnoDB crash recovery after the earlier hard stop completed (checkpoint LSN 71383551 → 115222349, 1112 pages; `ready for connections`); CHECK TABLE OK; 0 radar rows. Owned preview fixtures seeded and cleaned. Stopped GRACEFULLY with SQL `SHUTDOWN` as root (`InnoDB: Shutdown completed … Shutdown complete`). No listener on 3461/5041 afterwards. Logs: `radar-design/artifacts/ha1/final-ui-check/{restart-recovery,shutdown}.mariadbd.err.txt`. Preferred stop from now on: `mariadb.exe --host=127.0.0.1 --port=3461 --user=root -e "SHUTDOWN;"` with the root password from secrets.json in `MYSQL_PWD`.

## Teardown (safe, exact; stop step already executed once, repeat only after a restart)

Run from PowerShell only after confirming the PID in `mariadbd.pid.json` still belongs to `C:\Users\michi\.radar-ha1-local-qa\mariadb-10.11.14-winx64\bin\mariadbd.exe`:

```powershell
$rec = Get-Content 'C:\Users\michi\.radar-ha1-local-qa\mariadbd.pid.json' -Raw | ConvertFrom-Json
$p = Get-CimInstance Win32_Process -Filter "ProcessId=$($rec.pid)"
if ($p -and $p.ExecutablePath -eq $rec.executable) { Stop-Process -Id $rec.pid -Confirm:$false }
# Restart for reproduction later:  & 'C:\Users\michi\.radar-ha1-local-qa\setup.ps1' -StartOnly
# Full removal (owner decision; deletes only this new directory):
# Remove-Item -LiteralPath 'C:\Users\michi\.radar-ha1-local-qa' -Recurse -Force
```

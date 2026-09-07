# Migration verification commands — 2026-09-07

Read-only commands. No secret values stored. Remote bash blocks used a PowerShell
single-quoted here-string piped to `ssh -o BatchMode=yes -i
$env:USERPROFILE/.ssh/id_ed25519 root@194.164.29.97 "tr -d '\r' | bash -s"`.
The initial inventory omitted `tr`, causing the final nginx check to receive CR;
the configuration block reran it successfully.

## NEW inventory

```bash
date -u
timedatectl show -p Timezone -p NTPSynchronized
nproc
sshd -T | awk '$1 ~ /^(permitrootlogin|passwordauthentication|kbdinteractiveauthentication|pubkeyauthentication)$/'
ufw status
dpkg-query -W nginx certbot python3.12 python3.12-venv python3.12-dev libmariadb-dev rclone git build-essential nodejs python3-certbot-nginx
/root/coc-stats/venv/bin/python - <<'PY'
import importlib.metadata as m
print("venv_distribution_count",len(list(m.distributions())))
for x in ("onnxruntime","Flask","PyMySQL"):
 print(x,m.version(x))
from pathlib import Path
for p in ("personal_apps/artifacts/judge","personal_apps/static/gym/dist","personal_apps/static/radar/dist","coc_stats/locks","coc_stats/logs","reports"):
 d=Path("/root/coc-stats")/p
 print("path",p,"exists",d.exists(),"files",sum(1 for x in d.rglob("*") if x.is_file()) if d.is_dir() else 0)
PY
systemctl show coc_web personal_apps_web coc_scheduler personal_apps_gym_notifier radar_ingest radar-encoder-trial.timer mariadb certbot.timer -p Id -p ActiveState -p SubState -p UnitFileState
ps -eo pid,ppid,comm | awk '$3 ~ /^(gzip|gunzip|mariadb)$/ {print}'
mariadb -N -e "SELECT ID,USER,DB,COMMAND,TIME,STATE FROM information_schema.PROCESSLIST WHERE ID <> CONNECTION_ID(); SELECT TABLE_SCHEMA,COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA IN ('coc_stats','personal_apps') GROUP BY TABLE_SCHEMA; SELECT User,Host FROM mysql.user WHERE User IN ('coc_user','mgemmel'); SELECT COUNT(*) FROM mysql.time_zone_name; SHOW GLOBAL VARIABLES WHERE Variable_name IN ('innodb_buffer_pool_size','innodb_flush_log_at_trx_commit','sync_binlog','bind_address','character_set_server','time_zone','max_allowed_packet');"
nginx -t
```

## NEW configuration

```bash
set -e
nginx -t
/root/coc-stats/venv/bin/python - <<'PY'
import importlib.metadata as m
p=sorted((x.metadata["Name"],x.version) for x in m.distributions())
print("dependency_count_excluding_pip",len([x for x in p if x[0].lower()!="pip"]))
print("pip",m.version("pip"))
PY
cat /etc/mysql/mariadb.conf.d/99-tuning.cnf
systemctl show coc_web personal_apps_web coc_scheduler personal_apps_gym_notifier radar_ingest radar-encoder-trial.service -p Id -p ExecStart -p WorkingDirectory -p StandardOutput -p StandardError
python3 - <<'PY'
import subprocess
from pathlib import Path
p=subprocess.run(["crontab","-l"],capture_output=True,text=True)
print("root_crontab_installed",p.returncode==0)
s=Path("/root/stage/crontab.txt")
print("staged_crontab_exists",s.exists())
if s.exists():
 print("staged_cron_active_lines",sum(bool(x.strip()) and not x.lstrip().startswith("#") for x in s.read_text().splitlines()))
for p in Path("/etc/letsencrypt/live").glob("*/cert.pem"):
 print("certificate",p.parent.name)
for p in Path("/etc/nginx/sites-enabled").iterdir(): print("enabled_site",p.name)
PY
```

## Cross-box comparison

```powershell
$migrationCompareScript = @'
import hashlib,json,subprocess
from pathlib import Path
files=["/root/coc-stats/.env","/root/.config/rclone/rclone.conf","/etc/mysql/mariadb.conf.d/50-server.cnf","/etc/nginx/sites-available/coc_stats","/root/backup_db.sh","/root/update_coc.sh","/root/check_logs.sh"]
files += ["/etc/systemd/system/"+n for n in ["coc_web.service","personal_apps_web.service","coc_scheduler.service","personal_apps_gym_notifier.service","radar_ingest.service","radar-encoder-trial.timer","radar-encoder-trial.service"]]
for base in ["/etc/letsencrypt","/root/coc-stats/personal_apps/artifacts/judge"]:
 files += [str(p) for p in Path(base).rglob("*") if p.is_file()]
out={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() if Path(p).is_file() else "MISSING" for p in files}
q="SELECT User,Host,plugin,authentication_string FROM mysql.user WHERE User IN ('coc_user','mgemmel') ORDER BY User,Host;"
r=subprocess.run(["mariadb","-N","-e",q],capture_output=True,check=True)
out["database_user_auth"]=hashlib.sha256(r.stdout).hexdigest()
q="SELECT * FROM information_schema.SCHEMA_PRIVILEGES WHERE GRANTEE IN (CHAR(39,99,111,99,95,117,115,101,114,39,64,39,108,111,99,97,108,104,111,115,116,39),CHAR(39,109,103,101,109,109,101,108,39,64,39,37,39)) ORDER BY GRANTEE,TABLE_SCHEMA,PRIVILEGE_TYPE; SELECT * FROM information_schema.USER_PRIVILEGES WHERE GRANTEE IN (CHAR(39,99,111,99,99,95,117,115,101,114,39,64,39,108,111,99,97,108,104,111,115,116,39),CHAR(39,109,103,101,109,109,101,108,39,64,39,37,39)) ORDER BY GRANTEE,PRIVILEGE_TYPE;"
r=subprocess.run(["mariadb","-N","-e",q],capture_output=True,check=True)
out["database_grants"]=hashlib.sha256(r.stdout).hexdigest()
p=Path("/root/stage/crontab.txt")
r=subprocess.run(["crontab","-l"],capture_output=True)
v=p.read_bytes() if p.exists() else r.stdout
out["cron_staged_vs_installed"]=hashlib.sha256(v).hexdigest()
print(json.dumps(out))
'@
$migrationOld = $migrationCompareScript | ssh -o BatchMode=yes -i $env:USERPROFILE/.ssh/id_ed25519 root@82.165.240.212 python3 -
if ($LASTEXITCODE -ne 0) { throw 'OLD comparison read failed' }
$migrationNew = $migrationCompareScript | ssh -o BatchMode=yes -i $env:USERPROFILE/.ssh/id_ed25519 root@194.164.29.97 python3 -
if ($LASTEXITCODE -ne 0) { throw 'NEW comparison read failed' }
$migrationOldMap = $migrationOld | ConvertFrom-Json -AsHashtable
$migrationNewMap = $migrationNew | ConvertFrom-Json -AsHashtable
foreach ($migrationPath in ($migrationOldMap.Keys + $migrationNewMap.Keys | Sort-Object -Unique)) { [pscustomobject]@{Path=$migrationPath; Equal=($migrationOldMap[$migrationPath] -eq $migrationNewMap[$migrationPath]); PresentBoth=($migrationOldMap.ContainsKey($migrationPath) -and $migrationNewMap.ContainsKey($migrationPath) -and $migrationOldMap[$migrationPath] -ne 'MISSING' -and $migrationNewMap[$migrationPath] -ne 'MISSING')} | ConvertTo-Json -Compress }
```

## Rclone fields

```powershell
$migrationScript = @'
import hashlib,json,subprocess,configparser
from pathlib import Path
c=configparser.ConfigParser(interpolation=None);c.read("/root/.config/rclone/rclone.conf")
out={}
for s in c.sections():
 for k,v in c[s].items():
  if k=="token":
   try:
    for tk,tv in json.loads(v).items():out[s+"."+k+"."+tk]=hashlib.sha256(str(tv).encode()).hexdigest()
   except ValueError:out[s+"."+k]=hashlib.sha256(v.encode()).hexdigest()
  else:out[s+"."+k]=hashlib.sha256(v.encode()).hexdigest()
print(json.dumps(out))
'@
$migrationA = $migrationScript | ssh -o BatchMode=yes -i $env:USERPROFILE/.ssh/id_ed25519 root@82.165.240.212 python3 -
if ($LASTEXITCODE -ne 0) { throw 'OLD read failed' }
$migrationB = $migrationScript | ssh -o BatchMode=yes -i $env:USERPROFILE/.ssh/id_ed25519 root@194.164.29.97 python3 -
if ($LASTEXITCODE -ne 0) { throw 'NEW read failed' }
$migrationAMap=$migrationA|ConvertFrom-Json -AsHashtable
$migrationBMap=$migrationB|ConvertFrom-Json -AsHashtable
foreach ($migrationKey in ($migrationAMap.Keys+$migrationBMap.Keys|Sort-Object -Unique)) { [pscustomobject]@{Field=$migrationKey;Equal=($migrationAMap[$migrationKey] -eq $migrationBMap[$migrationKey])}|ConvertTo-Json -Compress }
```

## Grants on both boxes

```bash
python3 - <<'PY'
import subprocess,re
for u,h in [("coc_user","localhost"),("mgemmel","%")]:
 r=subprocess.run(["mariadb","-N","-e","SHOW GRANTS FOR '"+u+"'@'"+h+"';"],capture_output=True,text=True,check=True)
 print(u+"@"+h)
 for line in r.stdout.splitlines():
  print(re.split(r" IDENTIFIED ",line,maxsplit=1,flags=re.I)[0])
PY
```

## Grant-option confirmation on both boxes

Used the same grants Python block, replacing its output loop with:

```python
 print(u+'@'+h,'grant_option',any('WITH GRANT OPTION' in x for x in r.stdout.splitlines()))
```

The initial digest query contains a typo in the coc_user global-privilege filter.
Direct SHOW GRANTS and the separate flag check independently verified both users;
no conclusion relies on that digest alone.

## Continued rehearsal commands

### Restore progress (run twice)

```bash
date -u
ps -eo pid,ppid,etime,comm | awk '$4 ~ /^(gzip|gunzip|mariadb)$/ {print}'
mariadb -N -e "SELECT ID,USER,DB,COMMAND,TIME,STATE FROM information_schema.PROCESSLIST WHERE ID <> CONNECTION_ID(); SELECT TABLE_SCHEMA,COUNT(*),ROUND(SUM(DATA_LENGTH+INDEX_LENGTH)/1024/1024) FROM information_schema.TABLES WHERE TABLE_SCHEMA IN ('coc_stats','personal_apps') GROUP BY TABLE_SCHEMA;"
python3 - <<'PY'
from pathlib import Path
import os
p=Path("/root/db_backups/db_2026-09-07_0315.sql.gz")
print("dump_bytes",p.stat().st_size)
for proc in Path("/proc").iterdir():
 if not proc.name.isdigit():continue
 try:
  if (proc/"comm").read_text().strip() not in ("gzip","gunzip"):continue
  for fd in (proc/"fd").iterdir():
   target=os.readlink(fd)
   if target==str(p):
    print("restore_pid",proc.name,"input_fd",fd.name)
    print((proc/"fdinfo"/fd.name).read_text())
 except (FileNotFoundError,PermissionError,ProcessLookupError):pass
PY
systemctl is-active coc_web personal_apps_web radar_ingest radar-encoder-trial.timer
```

### Encoder load, TLS, Drive listing and buffer pool

```bash
set -e
cd /root/coc-stats/personal_apps
/root/coc-stats/venv/bin/python - <<'PY'
import time,resource
from features.radar.judge_backends import EncoderBackend
t=time.monotonic()
backend=EncoderBackend(artifact_dir="/root/coc-stats/personal_apps/artifacts/judge")
backend._load()
print("encoder_load_seconds",round(time.monotonic()-t,2))
print("peak_rss_mib",round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024))
print("encoder_load_ok",True)
PY
for host in misala.viewdns.net pubquizmainz.viewdns.net mgemmel.viewdns.net; do
 curl --silent --show-error --max-time 15 --resolve "$host:443:194.164.29.97" -o /dev/null -w "$host tls_verify=%{ssl_verify_result} http=%{http_code}\n" "https://$host/"
done
rclone lsf gdrive:vps-backups/ --max-depth 1 | wc -l
mariadb -N -e "SHOW GLOBAL VARIABLES WHERE Variable_name IN ('innodb_buffer_pool_size','innodb_buffer_pool_chunk_size','innodb_buffer_pool_size_max'); SHOW GLOBAL STATUS WHERE Variable_name IN ('Innodb_buffer_pool_resize_status','Innodb_buffer_pool_reads','Innodb_buffer_pool_read_requests');"
```

### Dump integrity and table boundaries

```bash
python3 - <<'PY'
import gzip,re,json,time
from pathlib import Path
p=Path("/root/db_backups/db_2026-09-07_0315.sql.gz")
db=None;tables=[];current=None;last=0;t=time.monotonic()
with p.open("rb") as raw:
 with gzip.GzipFile(fileobj=raw) as f:
  for line in f:
   if line.startswith(b"USE "):
    m=re.search(rb"`([^`]+)`",line)
    if m:db=m.group(1).decode()
   if line.startswith(b"CREATE TABLE "):
    m=re.search(rb"`([^`]+)`",line)
    if m:
     if current:current["compressed_end_approx"]=raw.tell()
     current={"db":db,"table":m.group(1).decode(),"compressed_start_approx":raw.tell()}
     tables.append(current)
  if current:current["compressed_end_approx"]=raw.tell()
print("gzip_integrity_ok",True,"seconds",round(time.monotonic()-t,1))
print("tables",len(tables))
for x in tables:
 if x["table"]=="radar_bucket_sources" or x["db"]=="personal_apps":
  print(json.dumps(x))
PY
```

### Application DB reads and frontend manifests

```bash
set -e
cd /root/coc-stats
venv/bin/python - <<'PY'
import json,os
from pathlib import Path
from dotenv import dotenv_values
import pymysql
e=dotenv_values("/root/coc-stats/.env")
print("env_expected_db_host",e.get("DB_HOST")=="localhost")
print("env_expected_db_user",e.get("DB_USER")=="coc_user")
print("env_encoder_primary",e.get("RADAR_JUDGE_PRIMARY")=="encoder")
conn=pymysql.connect(host=e.get("DB_HOST","localhost"),user=e.get("DB_USER"),password=e.get("DB_PASS"),read_timeout=15)
with conn.cursor() as c:
 for schema,table in [("coc_stats","alembic_version"),("personal_apps","app_user"),("personal_apps","quiz_rounds"),("personal_apps","gym_exercises")]:
  c.execute("SELECT COUNT(*) FROM "+schema+"."+table)
  print("db_read_ok",schema+"."+table,"count",c.fetchone()[0])
conn.close()
for feature in ("gym","radar"):
 root=Path("/root/coc-stats/personal_apps/static")/feature/"dist"
 manifests=list(root.rglob("manifest.json"))
 if not manifests:
  print("manifest_missing",feature)
  continue
 for p in manifests:
  m=json.loads(p.read_text())
  files=[v[k] for v in m.values() for k in ("file",) if k in v]
  files += [x for v in m.values() for k in ("css","assets") for x in v.get(k,[])]
  print("manifest",feature,"entries",len(m),"referenced_files",len(files),"all_exist",all((root/x).is_file() for x in files))
PY
```

## Approved NEW-only restart (executed)

```bash
set -euo pipefail
test "$(id -u)" = 0
ip -4 -o addr show | grep -q '194[.]164[.]29[.]97/'
for unit in coc_web personal_apps_web coc_scheduler personal_apps_gym_notifier radar_ingest radar-encoder-trial.timer; do
    if systemctl is-active --quiet "$unit"; then
        echo "Refusing: $unit is active" >&2
        exit 1
    fi
done
test -f /root/db_backups/db_2026-09-07_0315.sql.gz
test -f /etc/mysql/mariadb.conf.d/99-tuning.cnf
systemctl stop mariadb
test "$(systemctl show mariadb -p ActiveState --value)" = inactive
systemctl start mariadb
test "$(mariadb -N -e 'SELECT @@GLOBAL.innodb_buffer_pool_size;')" = 1073741824
if pgrep -x gzip >/dev/null || pgrep -x mariadb >/dev/null; then
    echo "Refusing to clear databases: an old import client is still running" >&2
    exit 1
fi
mariadb -e "DROP DATABASE IF EXISTS coc_stats; DROP DATABASE IF EXISTS personal_apps;"
mariadb -e "SET GLOBAL innodb_flush_log_at_trx_commit=2; SET GLOBAL sync_binlog=0;"
install -d -m 700 /root/stage
umask 077
cat > /root/stage/rehearsal-restore.sh <<'RESTORE'
#!/bin/bash
set -euo pipefail
umask 077
finish() {
    result=$?
    trap - EXIT
    mariadb -e "SET GLOBAL innodb_flush_log_at_trx_commit=1; SET GLOBAL sync_binlog=1;" >/dev/null 2>&1 || result=90
    printf '%s\n' "$result" > /root/stage/rehearsal-restore.exit
    date -u +%FT%TZ > /root/stage/rehearsal-restore.finished
    exit "$result"
}
trap finish EXIT
date -u +%FT%TZ > /root/stage/rehearsal-restore.started
gzip -dc /root/db_backups/db_2026-09-07_0315.sql.gz 2>/root/stage/rehearsal-gzip.stderr |
    mariadb > /root/stage/rehearsal-mariadb.stdout 2>/root/stage/rehearsal-mariadb.stderr
RESTORE
chmod 700 /root/stage/rehearsal-restore.sh
systemd-run --unit=vps-rehearsal-restore --property=Type=oneshot /bin/bash /root/stage/rehearsal-restore.sh
systemctl show vps-rehearsal-restore -p ActiveState -p SubState -p ExecMainStatus
mariadb -N -e "SELECT @@GLOBAL.innodb_buffer_pool_size,@@GLOBAL.innodb_buffer_pool_size_max;"
```

MariaDB buffer sizing reference: https://mariadb.com/docs/server/server-usage/storage-engines/innodb/innodb-buffer-pool

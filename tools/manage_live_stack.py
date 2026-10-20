"""Prepare a backup, then apply only the reviewed additive attendance migration."""
import argparse
from datetime import datetime,timezone,timedelta
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/'.pbl4-run/live-update-plan.json'
MIGRATION=ROOT/'DoAn_ChamCong_AI/migration/02_attendance_integrity.sql'


def run(command,**kwargs):
    result=subprocess.run(command,capture_output=True,timeout=90,**kwargs)
    if result.returncode:
        raise RuntimeError('Container operation failed; private diagnostics withheld: '+command[0])
    return result.stdout


def state():
    code=('require "/var/www/html/Model/Database.php"; $p=Database::getConnection(); '
          '$tables=$p->query("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE=\'BASE TABLE\'")->fetchAll(PDO::FETCH_COLUMN); '
          '$counts=[]; foreach($tables as $table){$name="`".str_replace("`","``",$table)."`"; $counts[$table]=(int)$p->query("SELECT COUNT(*) FROM ".$name)->fetchColumn();} '
          'ksort($counts); echo json_encode($counts);')
    return json.loads(run(['docker','exec','pbl4_web','php','-r',code]))


def container_id():
    return json.loads(run(['docker','inspect','pbl4_mariadb']))[0]['Id']


def prepare():
    PLAN.parent.mkdir(parents=True,exist_ok=True)
    folder=PLAN.parent/'backups'
    folder.mkdir(exist_ok=True)
    stamp=datetime.now(timezone(timedelta(hours=7))).strftime('%Y%m%d-%H%M%S')
    path=folder/f'pbl4-before-attendance-migration-{stamp}.sql'
    counts=state()
    command=['docker','exec','pbl4_mariadb','sh','-c',
             'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mariadb-dump -uroot --single-transaction --routines --triggers --no-tablespaces DoAn_ChamCong_AI_MariaDB']
    with path.open('xb') as output:
        result=subprocess.run(command,stdout=output,stderr=subprocess.PIPE,timeout=90)
    if result.returncode or path.stat().st_size<100:
        raise RuntimeError('Backup failed; no migration may be applied')
    if state()!=counts:
        raise RuntimeError('DB row counts changed during backup; prepare again before applying')
    plan=dict(database_container=container_id(),backup=str(path),backup_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
              migration_sha256=hashlib.sha256(MIGRATION.read_bytes()).hexdigest(),row_counts=counts,
              action='Add missing status columns/table; recreate only Web with current .env; never reset data')
    PLAN.write_text(json.dumps(plan,indent=2),encoding='utf-8')
    print('Backup saved:',path)
    print('Backup bytes:',path.stat().st_size)
    print('Existing tables/rows:',len(counts),sum(counts.values()))
    print('Reviewable plan:',PLAN)


def apply():
    plan=json.loads(PLAN.read_text(encoding='utf-8'))
    backup=Path(plan['backup']).resolve()
    if not backup.is_relative_to((PLAN.parent/'backups').resolve()):
        raise RuntimeError('Unexpected backup path')
    if hashlib.sha256(backup.read_bytes()).hexdigest()!=plan['backup_sha256']:
        raise RuntimeError('Backup changed')
    if hashlib.sha256(MIGRATION.read_bytes()).hexdigest()!=plan['migration_sha256']:
        raise RuntimeError('Migration changed; prepare again')
    if container_id()!=plan['database_container'] or state()!=plan['row_counts']:
        raise RuntimeError('Database changed after backup; prepare again')
    code='require "/var/www/html/Model/Database.php"; Database::getConnection()->exec(file_get_contents("/var/www/html/migration/02_attendance_integrity.sql")); echo "ADDITIVE_MIGRATION_OK";'
    run(['docker','exec','pbl4_web','php','-r',code])
    after=state()
    if any(after.get(table)!=count for table,count in plan['row_counts'].items()):
        raise RuntimeError('Unexpected row count change; backup retained, do not reset automatically')
    run(['docker','compose','up','-d','--no-deps','--no-build','web'])
    print('Additive migration applied; all original table row counts unchanged.')
    print('Only Web recreated; MariaDB container/volume preserved.')
    plan['applied']=True
    PLAN.write_text(json.dumps(plan,indent=2),encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['prepare','apply'])
    args=parser.parse_args()
    prepare() if args.operation=='prepare' else apply()

"""Read-only service/schema checks. Never print credentials or employee data."""
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

ROOT=Path(__file__).resolve().parents[1]


def environment():
    values={}
    for line in (ROOT/'.env').read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key,value=line.split('=',1)
            values[key.strip()]=value.strip().strip('"\'')
    return values


def main():
    values=environment()
    inspected=subprocess.run(['docker','inspect','pbl4_web','pbl4_mariadb'],capture_output=True,text=True,timeout=15)
    if inspected.returncode:
        print('Docker inspection unavailable; no configuration mismatch can be inferred.')
        return 1
    containers=json.loads(inspected.stdout)
    for container in containers:
        print(container['Name'].lstrip('/'),'running:',container['State']['Running'],'image:',container['Config']['Image'])
    web=next(container for container in containers if container['Name']=='/pbl4_web')
    config=dict(item.split('=',1) for item in web['Config']['Env'] if '=' in item)
    for key in ('MARIADB_PASSWORD','PBL4_INTERNAL_TOKEN'):
        print('Web matches .env '+key+':',bool(values.get(key)) and config.get(key)==values.get(key))
    code=('require "/var/www/html/Model/Database.php"; $p=Database::getConnection(); '
          '$q=$p->query("SELECT TABLE_NAME,COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() '
          'AND ((TABLE_NAME=\'ChamCong\' AND COLUMN_NAME IN (\'TheTrang\',\'TheTrangVao\',\'TheTrangRa\')) OR TABLE_NAME=\'AttendanceEvent\')"); '
          'echo json_encode($q->fetchAll());')
    result=subprocess.run(['docker','exec','pbl4_web','php','-r',code],capture_output=True,text=True,timeout=15)
    if result.returncode:
        print('Web DB schema read failed; private error details withheld.')
    else:
        rows=json.loads(result.stdout)
        print('AttendanceEvent columns:',sum(row['TABLE_NAME']=='AttendanceEvent' for row in rows))
        print('ChamCong status columns:',[row['COLUMN_NAME'] for row in rows if row['TABLE_NAME']=='ChamCong'])
    for port,path in ((8080,'/?action=login'),(5001,'/health'),(5000,'/')):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}'+path,timeout=3) as response:
                print('HTTP port',port,':',response.status)
        except Exception:
            print('HTTP port',port,': unavailable')
    return 0


if __name__=='__main__':
    raise SystemExit(main())

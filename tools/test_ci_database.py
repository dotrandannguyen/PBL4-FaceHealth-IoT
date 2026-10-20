"""Destructive fixtures against an explicitly isolated CI service, never port 3306."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from test_http_attendance import run_http_tests
from test_http_enrollment import run_enrollment_tests
from test_admin_bootstrap import run_admin_tests


def main():
    env = dict(os.environ)
    if not (env.get('CI') == 'true' and env.get('PBL4_TEST_DATABASE') == 'isolated'
            and env.get('MARIADB_HOST') == '127.0.0.1' and env.get('MARIADB_PORT') == '33307'):
        raise SystemExit('Refusing: requires isolated CI database on 127.0.0.1:33307')
    root = Path(__file__).resolve().parents[1]
    php = Path(shutil.which('php') or 'php')
    subprocess.run([str(php), str(root/'DoAn_ChamCong_AI/tests/integration_attendance.php')],
                   env=env, check=True, timeout=60)
    subprocess.run([str(php), str(root/'DoAn_ChamCong_AI/tests/integration_attendance_read.php')],
                   env=env, check=True, timeout=30)
    with tempfile.TemporaryDirectory(prefix='pbl4-ci-http-') as temporary:
        run_http_tests(php, root, env, Path(temporary))
        run_enrollment_tests(php, root, env, Path(temporary))
    subprocess.run([sys.executable, '-B', str(root/'tools/test_desktop_runtime.py'), '--database', '-v'],
                   env=env, check=True, timeout=60)
    run_admin_tests(php, root, env)


if __name__ == '__main__':
    main()

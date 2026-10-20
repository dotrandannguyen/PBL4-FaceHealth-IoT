"""Run integration tests in a disposable MariaDB instance, never the project DB.

Windows example:
  python -B tools/test_isolated_database.py --mysql-bin C:/xampp/mysql/bin --php C:/xampp/php/php.exe
"""
import argparse
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time

from test_http_attendance import run_http_tests
from test_http_enrollment import run_enrollment_tests
from test_admin_bootstrap import run_admin_tests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mysql-bin", required=True, type=Path)
    parser.add_argument("--php", required=True, type=Path)
    parser.add_argument('--desktop-python', type=Path)
    parser.add_argument('--desktop-site', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with tempfile.TemporaryDirectory(prefix="pbl4-isolated-db-") as temporary:
        directory = Path(temporary).resolve()
        if directory.parent != Path(tempfile.gettempdir()).resolve():
            raise RuntimeError("Unexpected temporary directory")
        data = directory / "data"
        subprocess.run([str(args.mysql_bin / "mysql_install_db.exe"), "--datadir=" + str(data),
                        "--port=" + str(port), "--silent"], check=True, timeout=60,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=flags)
        with (directory / "server.log").open("wb") as log:
            server = subprocess.Popen([str(args.mysql_bin / "mysqld.exe"), "--no-defaults",
                "--basedir=" + str(args.mysql_bin.parent), "--datadir=" + str(data),
                "--bind-address=127.0.0.1", "--port=" + str(port), "--skip-log-bin", "--console"],
                stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
            try:
                deadline = time.monotonic() + 30
                while True:
                    if server.poll() is not None:
                        raise RuntimeError((directory / "server.log").read_text(errors="replace"))
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=.2):
                            break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise RuntimeError("Temporary database did not start")
                        time.sleep(.1)
                env = dict(os.environ, PBL4_TEST_DATABASE="isolated", MARIADB_HOST="127.0.0.1",
                    MARIADB_PORT=str(port), MARIADB_USER="root", MARIADB_PASSWORD="",
                    MARIADB_DATABASE="DoAn_ChamCong_AI_MariaDB")
                result = subprocess.run([str(args.php), str(root / "DoAn_ChamCong_AI/tests/integration_attendance.php")],
                               env=env, check=True, timeout=60, creationflags=flags, capture_output=True)
                output = result.stdout.decode("utf-8", errors="replace")
                print(output.strip())
                if "PASS:" not in output:
                    raise RuntimeError("Integration test did not report success: " + result.stderr.decode(errors="replace"))
                read_result = subprocess.run([str(args.php), str(root / 'DoAn_ChamCong_AI/tests/integration_attendance_read.php')],
                                            env=env, check=True, timeout=30, creationflags=flags, capture_output=True)
                print(read_result.stdout.decode('utf-8', errors='replace').strip())
                run_http_tests(args.php, root, env, directory)
                run_enrollment_tests(args.php, root, env, directory)
                if args.desktop_python:
                    command = [str(args.desktop_python), '-B', str(root / 'tools/test_desktop_runtime.py'), '--database', '-v']
                    if args.desktop_site:
                        command.extend(['--extra-site', str(args.desktop_site.resolve())])
                    desktop = subprocess.run(command, env=env, timeout=60, creationflags=flags, capture_output=True)
                    desktop_output = (desktop.stdout + desktop.stderr).decode('utf-8', errors='replace')
                    print(desktop_output.strip())
                    if desktop.returncode or 'OK' not in desktop_output or 'skipped' in desktop_output:
                        raise RuntimeError('Desktop integration suite did not pass completely')
                run_admin_tests(args.php, root, env)
            finally:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)


if __name__ == "__main__":
    main()

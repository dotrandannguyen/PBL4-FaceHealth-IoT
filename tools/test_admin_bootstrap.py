"""Run only inside the disposable DB runners after their fixtures."""
import subprocess


def run_admin_tests(php, root, env):
    if env.get('PBL4_TEST_DATABASE') != 'isolated' or env.get('MARIADB_PORT') == '3306':
        raise RuntimeError('Disposable DB required')
    script = root/'DoAn_ChamCong_AI/tools/create_admin.php'
    configured = dict(env, PBL4_BOOTSTRAP_ADMIN='bootstrap_test_admin',
                      PBL4_BOOTSTRAP_PASSWORD='isolated-test-password', PBL4_BOOTSTRAP_NAME='Test Admin')
    def run(values):
        return subprocess.run([str(php), str(script)], env=values, capture_output=True, timeout=15)
    assert run(dict(configured, PBL4_BOOTSTRAP_PASSWORD='short')).returncode == 2
    assert run(configured).returncode == 0
    assert run(dict(configured, PBL4_BOOTSTRAP_PASSWORD='changed-test-password')).returncode == 3
    code = ('require "'+str(root/'DoAn_ChamCong_AI/Model/Database.php').replace('\\','/')+'"; '
            '$p=Database::getConnection(); $s=$p->prepare("SELECT t.MatKhau,n.MaVaiTro FROM TaiKhoan t JOIN NhanVien n ON n.MaNV=t.MaNV WHERE t.TenDangNhap=?"); '
            '$s->execute(["bootstrap_test_admin"]); $rows=$s->fetchAll(); '
            'exit(count($rows)===1 && (int)$rows[0]["MaVaiTro"]===1 && password_verify("isolated-test-password",$rows[0]["MatKhau"])?0:1);')
    subprocess.run([str(php), '-r', code], env=env, check=True, timeout=15, capture_output=True)
    print('PASS: admin bootstrap rejects weak passwords, creates hashed account, refuses overwrite')

<?php
declare(strict_types=1);

require_once __DIR__ . '/Database.php';

final class AccountModel
{
    private const WERKZEUG_SCRYPT_VERIFIER = <<<'PYTHON'
import hashlib
import hmac
import json
import sys

try:
    payload = json.load(sys.stdin)
    method, salt, expected_hex = payload["stored"].split("$", 2)
    parts = method.split(":")
    if len(parts) != 4 or parts[0] != "scrypt":
        sys.exit(2)

    n, r, p = (int(value) for value in parts[1:])
    if n < 2 or n > 65536 or n & (n - 1) or r < 1 or r > 8 or p < 1 or p > 4:
        sys.exit(2)

    expected = bytes.fromhex(expected_hex)
    if len(expected) < 16 or len(expected) > 64:
        sys.exit(2)

    actual = hashlib.scrypt(
        payload["password"].encode("utf-8"),
        salt=salt.encode("utf-8"),
        n=n,
        r=r,
        p=p,
        dklen=len(expected),
        maxmem=134217728,
    )
    sys.stdout.write("1" if hmac.compare_digest(actual, expected) else "0")
except Exception:
    sys.exit(2)
PYTHON;

    /** Xác thực credential hiện có và trả thông tin session-safe, không trả mật khẩu. */
    public function authenticate(string $username, string $password): ?array
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            SELECT
                tk.MaTK AS UserId,
                tk.MaNV AS EmployeeId,
                tk.TenDangNhap AS Username,
                tk.MatKhau AS StoredPassword,
                nv.HoTen AS DisplayName,
                nv.MaVaiTro AS RoleId,
                vt.TenVaiTro AS RoleName
            FROM TaiKhoan tk
            INNER JOIN NhanVien nv ON nv.MaNV = tk.MaNV
            INNER JOIN VaiTro vt ON vt.MaVaiTro = nv.MaVaiTro
            WHERE tk.TenDangNhap = :username
            LIMIT 1
            SQL);
        $statement->execute(['username' => $username]);
        $account = $statement->fetch();

        if ($account === false || !$this->passwordMatches($password, (string)$account['StoredPassword'])) {
            return null;
        }

        return [
            'user_id' => (int)$account['UserId'],
            'ma_nv' => (int)$account['EmployeeId'],
            'username' => (string)$account['Username'],
            'display_name' => (string)($account['DisplayName'] ?? ''),
            'ma_vai_tro' => (int)$account['RoleId'],
            'role' => (string)$account['RoleName'],
        ];
    }

    public function usernameExists(string $username, ?int $exceptEmployeeId = null): bool
    {
        $sql = 'SELECT 1 FROM TaiKhoan WHERE TenDangNhap = :username';
        $params = ['username' => $username];
        if ($exceptEmployeeId !== null) {
            $sql .= ' AND MaNV <> :employee_id';
            $params['employee_id'] = $exceptEmployeeId;
        }
        $sql .= ' LIMIT 1';
        $statement = Database::getConnection()->prepare($sql);
        $statement->execute($params);

        return $statement->fetchColumn() !== false;
    }

    /** Lấy username và mã tài khoản liên kết với nhân viên, không đọc password. */
    public function findByEmployeeId(int $employeeId): ?array
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            SELECT MaTK, MaNV, TenDangNhap
            FROM TaiKhoan
            WHERE MaNV = :employee_id
            ORDER BY MaTK
            LIMIT 1
            SQL);
        $statement->execute(['employee_id' => $employeeId]);
        $account = $statement->fetch();

        return $account === false ? null : $account;
    }

    /** Chèn tài khoản đã hash cho nhân viên trong transaction do caller quản lý. */
    public function createForEmployee(int $employeeId, string $username, string $passwordHash): void
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            INSERT INTO TaiKhoan (MaNV, TenDangNhap, MatKhau)
            VALUES (:employee_id, :username, :password)
            SQL);
        $statement->execute([
            'employee_id' => $employeeId,
            'username' => $username,
            'password' => $passwordHash,
        ]);
    }

    /** Cập nhật username và chỉ thay password khi hash mới được truyền vào. */
    public function updateForEmployee(
        int $employeeId,
        string $username,
        ?string $passwordHash
    ): void {
        $sql = 'UPDATE TaiKhoan SET TenDangNhap = :username';
        $params = ['username' => $username, 'employee_id' => $employeeId];
        if ($passwordHash !== null) {
            $sql .= ', MatKhau = :password';
            $params['password'] = $passwordHash;
        }
        $sql .= ' WHERE MaNV = :employee_id ORDER BY MaTK LIMIT 1';
        Database::getConnection()->prepare($sql)->execute($params);
    }

    private function passwordMatches(string $password, string $storedPassword): bool
    {
        $metadata = password_get_info($storedPassword);
        if (($metadata['algoName'] ?? 'unknown') !== 'unknown') {
            return password_verify($password, $storedPassword);
        }

        if (str_starts_with($storedPassword, 'scrypt:')) {
            return $this->verifyWerkzeugScrypt($password, $storedPassword);
        }

        return hash_equals($storedPassword, $password);
    }

    private function verifyWerkzeugScrypt(string $password, string $storedPassword): bool
    {
        if (!function_exists('proc_open')) {
            return false;
        }

        $input = json_encode([
            'stored' => $storedPassword,
            'password' => $password,
        ]);
        if ($input === false) {
            return false;
        }

        $python = getenv('PYTHON_EXECUTABLE') ?: 'python';
        $process = proc_open(
            [$python, '-c', self::WERKZEUG_SCRYPT_VERIFIER],
            [
                0 => ['pipe', 'r'],
                1 => ['pipe', 'w'],
                2 => ['pipe', 'w'],
            ],
            $pipes,
            null,
            null,
            ['bypass_shell' => true]
        );
        if (!is_resource($process)) {
            return false;
        }

        fwrite($pipes[0], $input);
        fclose($pipes[0]);
        $output = trim(stream_get_contents($pipes[1]));
        fclose($pipes[1]);
        fclose($pipes[2]);
        $exitCode = proc_close($process);

        return $exitCode === 0 && hash_equals('1', $output);
    }
}

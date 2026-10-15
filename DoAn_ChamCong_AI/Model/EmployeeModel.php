<?php
declare(strict_types=1);

require_once __DIR__ . '/Database.php';
require_once __DIR__ . '/AccountModel.php';

final class EmployeeModel
{
    /** Lấy danh sách nhân viên kèm tài khoản và số lượng embedding khuôn mặt. */
    public function findAll(): array
    {
        $sql = <<<'SQL'
            SELECT
                nv.MaNV,
                nv.HoTen,
                vt.TenVaiTro,
                (
                    SELECT tk.TenDangNhap
                    FROM TaiKhoan tk
                    WHERE tk.MaNV = nv.MaNV
                    ORDER BY tk.MaTK
                    LIMIT 1
                ) AS TenDangNhap,
                CASE WHEN EXISTS (
                    SELECT 1
                    FROM TaiKhoan tk
                    WHERE tk.MaNV = nv.MaNV
                ) THEN 1 ELSE 0 END AS HasAccount,
                CASE WHEN EXISTS (
                    SELECT 1
                    FROM FaceEmbedding fe
                    WHERE fe.MaNV = nv.MaNV
                ) THEN 1 ELSE 0 END AS FaceRegistered,
                (
                    SELECT COUNT(*)
                    FROM FaceEmbedding fe
                    WHERE fe.MaNV = nv.MaNV
                ) AS FaceEmbeddingCount
            FROM NhanVien nv
            LEFT JOIN VaiTro vt ON vt.MaVaiTro = nv.MaVaiTro
            ORDER BY nv.MaNV
            SQL;

        return Database::getConnection()->query($sql)->fetchAll();
    }

    /** Tìm một nhân viên và tài khoản liên kết; trả null nếu không tồn tại. */
    public function findById(int $employeeId): ?array
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            SELECT
                nv.MaNV,
                nv.HoTen,
                nv.MaVaiTro,
                tk.TenDangNhap,
                CASE WHEN tk.MaTK IS NULL THEN 0 ELSE 1 END AS HasAccount
            FROM NhanVien nv
            LEFT JOIN TaiKhoan tk ON tk.MaTK = (
                SELECT tk2.MaTK
                FROM TaiKhoan tk2
                WHERE tk2.MaNV = nv.MaNV
                ORDER BY tk2.MaTK
                LIMIT 1
            )
            WHERE nv.MaNV = :employee_id
            SQL);
        $statement->execute(['employee_id' => $employeeId]);
        $employee = $statement->fetch();

        return $employee === false ? null : $employee;
    }

    public function findRoles(): array
    {
        return Database::getConnection()
            ->query('SELECT MaVaiTro, TenVaiTro FROM VaiTro ORDER BY MaVaiTro')
            ->fetchAll();
    }

    public function roleExists(int $roleId): bool
    {
        $statement = Database::getConnection()->prepare(
            'SELECT 1 FROM VaiTro WHERE MaVaiTro = :role_id LIMIT 1'
        );
        $statement->execute(['role_id' => $roleId]);

        return $statement->fetchColumn() !== false;
    }

    /** Tạo nhân viên và tài khoản đăng nhập trong cùng transaction PDO. */
    public function createWithAccount(
        string $name,
        int $roleId,
        string $username,
        string $passwordHash
    ): int
    {
        $pdo = Database::getConnection();
        $pdo->beginTransaction();
        try {
            $statement = $pdo->prepare(
                'INSERT INTO NhanVien (HoTen, MaVaiTro) VALUES (:name, :role_id)'
            );
            $statement->execute(['name' => $name, 'role_id' => $roleId]);
            $employeeId = (int)$pdo->lastInsertId();
            (new AccountModel())->createForEmployee($employeeId, $username, $passwordHash);
            $pdo->commit();

            return $employeeId;
        } catch (Throwable $exception) {
            if ($pdo->inTransaction()) {
                $pdo->rollBack();
            }
            throw $exception;
        }
    }

    /** Cập nhật nhân viên/tài khoản nguyên tử; null passwordHash nghĩa là giữ mật khẩu cũ. */
    public function updateWithAccount(
        int $employeeId,
        string $name,
        int $roleId,
        string $username,
        ?string $passwordHash
    ): void
    {
        $pdo = Database::getConnection();
        $pdo->beginTransaction();
        try {
            $statement = $pdo->prepare(<<<'SQL'
                UPDATE NhanVien
                SET HoTen = :name, MaVaiTro = :role_id
                WHERE MaNV = :employee_id
                SQL);
            $statement->execute([
                'name' => $name,
                'role_id' => $roleId,
                'employee_id' => $employeeId,
            ]);

            $accounts = new AccountModel();
            $existingAccount = $accounts->findByEmployeeId($employeeId);
            if ($existingAccount === null) {
                if ($username !== '' || $passwordHash !== null) {
                    if ($username === '' || $passwordHash === null) {
                        throw new DomainException('A username and password are required to create an account.');
                    }
                    $accounts->createForEmployee($employeeId, $username, $passwordHash);
                }
            } else {
                $accounts->updateForEmployee($employeeId, $username, $passwordHash);
            }
            $pdo->commit();
        } catch (Throwable $exception) {
            if ($pdo->inTransaction()) {
                $pdo->rollBack();
            }
            throw $exception;
        }
    }
}

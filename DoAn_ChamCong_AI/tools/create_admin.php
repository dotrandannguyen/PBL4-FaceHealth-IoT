<?php
declare(strict_types=1);

if (PHP_SAPI !== 'cli') {
    http_response_code(403);
    exit;
}
require_once __DIR__ . '/../Model/Database.php';

$username = getenv('PBL4_BOOTSTRAP_ADMIN') ?: '';
$password = getenv('PBL4_BOOTSTRAP_PASSWORD') ?: '';
$name = getenv('PBL4_BOOTSTRAP_NAME') ?: 'Administrator';
if (!preg_match('/^[A-Za-z0-9_.-]{3,50}$/D', $username)
    || strlen($password) < 12 || strlen($password) > 72
    || !preg_match('//u', $name) || mb_strlen($name, 'UTF-8') > 100) {
    fwrite(STDERR, "Set PBL4_BOOTSTRAP_ADMIN (3-50 characters), PBL4_BOOTSTRAP_PASSWORD (12-72 bytes), and optional PBL4_BOOTSTRAP_NAME.\n");
    exit(2);
}

$pdo = null;
try {
    $hash = password_hash($password, PASSWORD_DEFAULT);
    $pdo = Database::getConnection();
    $pdo->beginTransaction();
    $query = $pdo->prepare('SELECT MaTK FROM TaiKhoan WHERE TenDangNhap = ?');
    $query->execute([$username]);
    if ($query->fetchColumn() !== false) {
        $pdo->rollBack();
        fwrite(STDERR, "Account already exists; no account or password was changed.\n");
        exit(3);
    }
    if (!$pdo->query('SELECT MaVaiTro FROM VaiTro WHERE MaVaiTro = 1')->fetchColumn()) {
        throw new RuntimeException('Admin role missing');
    }
    $pdo->prepare('INSERT INTO NhanVien (HoTen, MaVaiTro) VALUES (?, 1)')->execute([$name]);
    $employee = $pdo->lastInsertId();
    $pdo->prepare('INSERT INTO TaiKhoan (MaNV, TenDangNhap, MatKhau) VALUES (?, ?, ?)')
        ->execute([$employee, $username, $hash]);
    $pdo->commit();
    fwrite(STDOUT, "Administrator created.\n");
} catch (Throwable $error) {
    if ($pdo instanceof PDO && $pdo->inTransaction()) {
        $pdo->rollBack();
    }
    fwrite(STDERR, "Administrator creation failed; no partial account was saved.\n");
    exit(1);
}

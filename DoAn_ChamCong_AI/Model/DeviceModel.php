<?php
declare(strict_types=1);

require_once __DIR__ . '/Database.php';

final class DeviceModel
{
    public function findAll(): array
    {
        return Database::getConnection()->query(<<<'SQL'
            SELECT MaTB, LoaiTB, TrangThai
            FROM ThietBi
            ORDER BY MaTB
            SQL)->fetchAll();
    }
}

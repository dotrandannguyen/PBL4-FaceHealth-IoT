<?php
declare(strict_types=1);

require_once __DIR__ . '/Database.php';

final class AlertModel
{
    private const ALERT_JOINS = <<<'SQL'
        FROM CanhBao CB
        INNER JOIN NhanVien NV ON NV.MaNV = CB.MaNV
        LEFT JOIN LoaiCanhBao LCB ON LCB.MaLoaiCB = CB.MaLoaiCB
        LEFT JOIN LichSuTrangThai TT ON TT.MaTT = CB.MaTT
        LEFT JOIN DanhMucBieuHien BH ON BH.MaBieuHien = TT.MaBieuHien
        SQL;

    private const ALERT_TYPE = 'COALESCE(BH.TenBieuHien, LCB.TenLoaiCB)';

    public function findEmployees(): array
    {
        return Database::getConnection()->query(<<<'SQL'
            SELECT MaNV, HoTen
            FROM NhanVien
            ORDER BY MaNV
            SQL)->fetchAll();
    }

    public function findCategories(): array
    {
        $statement = Database::getConnection()->query(
            'SELECT DISTINCT ' . self::ALERT_TYPE . ' AS LoaiCanhBao ' . self::ALERT_JOINS
            . ' WHERE ' . self::ALERT_TYPE . ' IS NOT NULL ORDER BY LoaiCanhBao'
        );

        return $statement->fetchAll();
    }

    /** Lấy cảnh báo cùng thông tin liên quan theo bộ lọc và trang yêu cầu. */
    public function findAlerts(array $filters, int $page, int $pageSize): array
    {
        $where = [];
        $params = [];

        if ($filters['from_date'] !== '') {
            $where[] = 'CB.ThoiGian >= :from_date';
            $params['from_date'] = $filters['from_date'] . ' 00:00:00';
        }
        if ($filters['to_date'] !== '') {
            $where[] = 'CB.ThoiGian < DATE_ADD(:to_date, INTERVAL 1 DAY)';
            $params['to_date'] = $filters['to_date'] . ' 00:00:00';
        }
        if ($filters['employee_id'] !== null) {
            $where[] = 'CB.MaNV = :employee_id';
            $params['employee_id'] = $filters['employee_id'];
        }
        if ($filters['keyword'] !== '') {
            $where[] = "(
                CAST(CB.MaNV AS CHAR) LIKE :employee_code
                OR CONCAT('NV', LPAD(CB.MaNV, 3, '0')) LIKE :formatted_employee_code
                OR NV.HoTen LIKE :employee_name
            )";
            $pattern = '%' . $filters['keyword'] . '%';
            $params['employee_code'] = $pattern;
            $params['formatted_employee_code'] = $pattern;
            $params['employee_name'] = $pattern;
        }
        if ($filters['category'] !== '') {
            $where[] = self::ALERT_TYPE . ' = :category';
            $params['category'] = $filters['category'];
        }

        $whereSql = $where === [] ? '' : ' WHERE ' . implode(' AND ', $where);
        $pdo = Database::getConnection();
        $count = $pdo->prepare('SELECT COUNT(*) ' . self::ALERT_JOINS . $whereSql);
        $count->execute($params);
        $totalRows = (int)$count->fetchColumn();

        $offset = ($page - 1) * $pageSize;
        $alertType = self::ALERT_TYPE;
        $joins = self::ALERT_JOINS;
        $statement = $pdo->prepare(<<<SQL
            SELECT
                CB.MaCB,
                CB.MaNV,
                NV.HoTen,
                {$alertType} AS LoaiCanhBao,
                CB.NoiDung,
                CB.ThoiGian,
                CB.MaTT,
                CB.MaTB
            {$joins}
            {$whereSql}
            ORDER BY CB.ThoiGian DESC, CB.MaCB DESC
            LIMIT :limit OFFSET :offset
            SQL);
        foreach ($params as $name => $value) {
            $statement->bindValue(':' . $name, $value);
        }
        $statement->bindValue(':limit', $pageSize, PDO::PARAM_INT);
        $statement->bindValue(':offset', $offset, PDO::PARAM_INT);
        $statement->execute();

        return ['records' => $statement->fetchAll(), 'total' => $totalRows];
    }
}

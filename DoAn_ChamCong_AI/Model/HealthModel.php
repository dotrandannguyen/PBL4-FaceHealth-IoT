<?php
declare(strict_types=1);

require_once __DIR__ . '/Database.php';

final class HealthModel
{
    public function findEmployees(): array
    {
        return Database::getConnection()->query(<<<'SQL'
            SELECT MaNV, HoTen
            FROM NhanVien
            ORDER BY MaNV
            SQL)->fetchAll();
    }

    /** Lấy thống kê tổng quan trạng thái sức khỏe gần nhất của tất cả nhân viên. */
    public function findOverallStatusStats(): array
    {
        $sql = <<<'SQL'
            SELECT 
                COUNT(*) as total_employees,
                COALESCE(SUM(CASE WHEN latest.TheTrang = 'Bình thường' THEN 1 ELSE 0 END), 0) as count_normal,
                COALESCE(SUM(CASE WHEN latest.TheTrang = 'Mệt mỏi' THEN 1 ELSE 0 END), 0) as count_tired,
                COALESCE(SUM(CASE WHEN latest.TheTrang = 'Kiệt sức' THEN 1 ELSE 0 END), 0) as count_exhausted
            FROM (
                SELECT s1.MaNV, s1.TheTrang
                FROM LichSuSucKhoe s1
                INNER JOIN (
                    SELECT MaNV, MAX(MaSK) as MaxId
                    FROM LichSuSucKhoe
                    GROUP BY MaNV
                ) s2 ON s1.MaSK = s2.MaxId
            ) latest;
            SQL;
        $result = Database::getConnection()->query($sql)->fetch();

        return $result ?: [
            'total_employees' => 0,
            'count_normal' => 0,
            'count_tired' => 0,
            'count_exhausted' => 0,
        ];
    }

    /** Lấy danh sách tóm tắt sức khỏe mới nhất của từng nhân viên (chế độ Tổng quan). */
    public function findOverviewEmployees(array $filters, int $page, int $pageSize): array
    {
        $where = [];
        $params = [];
        if ($filters['keyword'] !== '') {
            $where[] = "(
                CAST(NV.MaNV AS CHAR) LIKE :employee_code
                OR CONCAT('NV', LPAD(NV.MaNV, 3, '0')) LIKE :formatted_employee_code
                OR NV.HoTen LIKE :employee_name
            )";
            $pattern = '%' . $filters['keyword'] . '%';
            $params['employee_code'] = $pattern;
            $params['formatted_employee_code'] = $pattern;
            $params['employee_name'] = $pattern;
        }

        $whereSql = $where === [] ? '' : ' WHERE ' . implode(' AND ', $where);
        $pdo = Database::getConnection();

        $countStmt = $pdo->prepare(<<<SQL
            SELECT COUNT(DISTINCT NV.MaNV)
            FROM NhanVien NV
            INNER JOIN LichSuSucKhoe SK ON NV.MaNV = SK.MaNV
            {$whereSql}
            SQL);
        $countStmt->execute($params);
        $totalRows = (int)$countStmt->fetchColumn();

        $offset = ($page - 1) * $pageSize;
        $statement = $pdo->prepare(<<<SQL
            SELECT 
                NV.MaNV,
                NV.HoTen,
                latest.NhipTim,
                latest.SpO2,
                latest.TheTrang,
                latest.ThoiGian,
                (SELECT COUNT(*) FROM LichSuSucKhoe WHERE MaNV = NV.MaNV) AS TongSoLanDo
            FROM NhanVien NV
            INNER JOIN (
                SELECT s1.MaNV, s1.NhipTim, s1.SpO2, s1.TheTrang, s1.ThoiGian
                FROM LichSuSucKhoe s1
                INNER JOIN (
                    SELECT MaNV, MAX(MaSK) as MaxId
                    FROM LichSuSucKhoe
                    GROUP BY MaNV
                ) s2 ON s1.MaSK = s2.MaxId
            ) latest ON NV.MaNV = latest.MaNV
            {$whereSql}
            ORDER BY latest.ThoiGian DESC, NV.MaNV ASC
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

    /** Lấy hồ sơ tóm tắt chỉ số sức khỏe của 1 nhân viên cụ thể. */
    public function findEmployeeHealthSummary(int $employeeId): ?array
    {
        $statement = Database::getConnection()->prepare(<<<SQL
            SELECT 
                NV.MaNV,
                NV.HoTen,
                latest.NhipTim as LatestNhipTim,
                latest.SpO2 as LatestSpO2,
                latest.TheTrang as LatestTheTrang,
                latest.ThoiGian as LatestThoiGian,
                ROUND(AVG(SK.NhipTim), 1) as AvgNhipTim,
                MIN(SK.NhipTim) as MinNhipTim,
                MAX(SK.NhipTim) as MaxNhipTim,
                ROUND(AVG(SK.SpO2), 1) as AvgSpO2,
                COUNT(SK.MaSK) as TotalRecords,
                COUNT(CASE WHEN SK.TheTrang IN ('Mệt mỏi', 'Kiệt sức') THEN 1 END) as AlertRecords
            FROM NhanVien NV
            LEFT JOIN LichSuSucKhoe SK ON NV.MaNV = SK.MaNV
            LEFT JOIN (
                SELECT MaNV, NhipTim, SpO2, TheTrang, ThoiGian
                FROM LichSuSucKhoe
                WHERE MaNV = :emp_id_latest
                ORDER BY MaSK DESC
                LIMIT 1
            ) latest ON NV.MaNV = latest.MaNV
            WHERE NV.MaNV = :emp_id
            GROUP BY NV.MaNV, NV.HoTen, latest.NhipTim, latest.SpO2, latest.TheTrang, latest.ThoiGian
            SQL);
        $statement->bindValue(':emp_id_latest', $employeeId, PDO::PARAM_INT);
        $statement->bindValue(':emp_id', $employeeId, PDO::PARAM_INT);
        $statement->execute();
        $row = $statement->fetch();

        return $row ?: null;
    }

    /** Truy vấn lịch sử sức khỏe theo filter và phân trang bằng SQL. */
    public function findHistory(array $filters, int $page, int $pageSize): array
    {
        $fromSql = <<<'SQL'
            FROM LichSuSucKhoe SK
            INNER JOIN NhanVien NV ON NV.MaNV = SK.MaNV
            SQL;
        [$whereSql, $params] = $this->historyFilterSql($filters);
        $pdo = Database::getConnection();

        $count = $pdo->prepare('SELECT COUNT(*) ' . $fromSql . $whereSql);
        $count->execute($params);
        $totalRows = (int)$count->fetchColumn();

        $offset = ($page - 1) * $pageSize;
        $statement = $pdo->prepare(<<<SQL
            SELECT SK.MaSK, SK.MaNV, NV.HoTen, SK.NhipTim, SK.SpO2, SK.TheTrang, SK.ThoiGian
            {$fromSql}
            {$whereSql}
            ORDER BY SK.ThoiGian DESC, SK.MaSK DESC
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

    /** Lấy chuỗi dữ liệu sức khỏe để vẽ biểu đồ Monitoring (chỉ khi có filter nhân viên cụ thể). */
    public function findChartData(array $filters, int $limit = 30): array
    {
        // Nếu không chọn nhân viên cụ thể, không trả dữ liệu vẽ biểu đồ để tránh nối điểm vô nghĩa giữa các nhân viên!
        if (empty($filters['employee_id'])) {
            return [];
        }

        [$whereSql, $params] = $this->historyFilterSql($filters);
        $statement = Database::getConnection()->prepare(<<<SQL
            SELECT SK.MaSK, NV.HoTen, SK.NhipTim, SK.SpO2, SK.TheTrang, SK.ThoiGian
            FROM LichSuSucKhoe SK
            INNER JOIN NhanVien NV ON NV.MaNV = SK.MaNV
            {$whereSql}
            ORDER BY SK.ThoiGian DESC, SK.MaSK DESC
            LIMIT :limit
            SQL);
        foreach ($params as $name => $value) {
            $statement->bindValue(':' . $name, $value);
        }
        $statement->bindValue(':limit', $limit, PDO::PARAM_INT);
        $statement->execute();

        return array_reverse($statement->fetchAll());
    }

    public function insertRecord(int $employeeId, ?int $hr, ?float $spo2, string $theTrang = 'Bình thường'): int
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            INSERT INTO LichSuSucKhoe (MaNV, NhipTim, SpO2, TheTrang, ThoiGian)
            VALUES (:employee_id, :hr, :spo2, :the_trang, CURRENT_TIMESTAMP(3))
            SQL);
        $statement->bindValue(':employee_id', $employeeId, PDO::PARAM_INT);
        $statement->bindValue(':hr', $hr, $hr === null ? PDO::PARAM_NULL : PDO::PARAM_INT);
        $statement->bindValue(':spo2', $spo2, $spo2 === null ? PDO::PARAM_NULL : PDO::PARAM_STR);
        $statement->bindValue(':the_trang', $theTrang);
        $statement->execute();

        return (int)Database::getConnection()->lastInsertId();
    }

    private function historyFilterSql(array $filters): array
    {
        $where = [];
        $params = [];
        if ($filters['from_date'] !== '') {
            $where[] = 'SK.ThoiGian >= :from_date';
            $params['from_date'] = $filters['from_date'] . ' 00:00:00';
        }
        if ($filters['to_date'] !== '') {
            $where[] = 'SK.ThoiGian < DATE_ADD(:to_date, INTERVAL 1 DAY)';
            $params['to_date'] = $filters['to_date'] . ' 00:00:00';
        }
        if ($filters['employee_id'] !== null) {
            $where[] = 'SK.MaNV = :employee_id';
            $params['employee_id'] = $filters['employee_id'];
        }
        if ($filters['keyword'] !== '') {
            $where[] = "(
                CAST(SK.MaNV AS CHAR) LIKE :employee_code
                OR CONCAT('NV', LPAD(SK.MaNV, 3, '0')) LIKE :formatted_employee_code
                OR NV.HoTen LIKE :employee_name
            )";
            $pattern = '%' . $filters['keyword'] . '%';
            $params['employee_code'] = $pattern;
            $params['formatted_employee_code'] = $pattern;
            $params['employee_name'] = $pattern;
        }

        return [$where === [] ? '' : ' WHERE ' . implode(' AND ', $where), $params];
    }
}

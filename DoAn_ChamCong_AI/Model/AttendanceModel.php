<?php
declare(strict_types=1);

require_once __DIR__ . '/Database.php';

final class AttendanceModel
{
    public function findEmployees(): array
    {
        return Database::getConnection()->query(<<<'SQL'
            SELECT MaNV, HoTen
            FROM NhanVien
            ORDER BY MaNV
            SQL)->fetchAll();
    }

    /** Lấy trạng thái từng nhân viên trong ngày, gồm ca và cờ có ảnh bằng chứng. */
    public function findDaily(
        string $date,
        ?int $employeeId = null,
        ?string $keyword = null,
        ?int $limit = null,
        int $offset = 0
    ): array {
        [$filter, $params] = $this->employeeFilters($employeeId, $keyword, 'NV');
        $start = $date . ' 00:00:00';
        $end = (new DateTimeImmutable($date))->modify('+1 day')->format('Y-m-d') . ' 00:00:00';
        $sql = <<<SQL
            SELECT
                NV.MaNV,
                NV.HoTen,
                CLV.TenCa,
                CLV.GioBatDau,
                CLV.GioKetThuc,
                CC.MaCC,
                CC.GioVao,
                CC.GioRa,
                CASE WHEN COALESCE(OCTET_LENGTH(CC.AnhVao), 0) > 0 THEN 1 ELSE 0 END AS HasImageIn,
                CASE WHEN COALESCE(OCTET_LENGTH(CC.AnhRa), 0) > 0 THEN 1 ELSE 0 END AS HasImageOut
            FROM NhanVien NV
            LEFT JOIN PhanCaNhanVien PCN
                ON PCN.MaNV = NV.MaNV AND PCN.NgayLamViec = :work_date
            LEFT JOIN CaLamViec CLV ON CLV.MaCa = PCN.MaCa
            LEFT JOIN ChamCong CC ON CC.MaCC = (
                SELECT CC2.MaCC
                FROM ChamCong CC2
                WHERE CC2.MaNV = NV.MaNV
                    AND CC2.GioVao >= :attendance_start
                    AND CC2.GioVao < :attendance_end
                ORDER BY CC2.GioVao ASC, CC2.MaCC ASC
                LIMIT 1
            )
            WHERE 1 = 1 {$filter}
            ORDER BY NV.MaNV
            SQL;
        $params += [
            'work_date' => $date,
            'attendance_start' => $start,
            'attendance_end' => $end,
        ];

        return $this->fetchPage($sql, $params, $limit, $offset);
    }

    public function countDaily(string $date, ?int $employeeId = null, ?string $keyword = null): int
    {
        [$filter, $params] = $this->employeeFilters($employeeId, $keyword, 'NV');
        $statement = Database::getConnection()->prepare(
            "SELECT COUNT(*) FROM NhanVien NV WHERE 1 = 1 {$filter}"
        );
        $statement->execute($params);

        return (int)$statement->fetchColumn();
    }

    /** Tìm lịch sử trong khoảng ngày và phân trang trực tiếp tại MariaDB. */
    public function findHistory(
        string $fromDate,
        string $toDate,
        ?int $employeeId = null,
        ?string $keyword = null,
        ?int $limit = null,
        int $offset = 0
    ): array {
        [$filter, $params] = $this->attendanceFilters($employeeId, $keyword);
        $endExclusive = (new DateTimeImmutable($toDate))->modify('+1 day')->format('Y-m-d') . ' 00:00:00';
        $sql = <<<SQL
            SELECT
                CC.MaCC,
                CC.MaNV,
                NV.HoTen,
                CC.MaCa,
                CLV.TenCa,
                CLV.GioBatDau,
                CLV.GioKetThuc,
                CC.GioVao,
                CC.GioRa,
                DATE_FORMAT(CC.GioVao, '%Y-%m-%d') AS Ngay,
                CASE WHEN COALESCE(OCTET_LENGTH(CC.AnhVao), 0) > 0 THEN 1 ELSE 0 END AS HasImageIn,
                CASE WHEN COALESCE(OCTET_LENGTH(CC.AnhRa), 0) > 0 THEN 1 ELSE 0 END AS HasImageOut
            FROM ChamCong CC
            INNER JOIN NhanVien NV ON NV.MaNV = CC.MaNV
            LEFT JOIN CaLamViec CLV ON CLV.MaCa = CC.MaCa
            WHERE CC.GioVao >= :from_date
                AND CC.GioVao < :to_date
                {$filter}
            ORDER BY CC.GioVao DESC, CC.MaCC DESC
            SQL;
        $params += [
            'from_date' => $fromDate . ' 00:00:00',
            'to_date' => $endExclusive,
        ];

        return $this->fetchPage($sql, $params, $limit, $offset);
    }

    public function countHistory(
        string $fromDate,
        string $toDate,
        ?int $employeeId = null,
        ?string $keyword = null
    ): int {
        [$filter, $params] = $this->attendanceFilters($employeeId, $keyword);
        $endExclusive = (new DateTimeImmutable($toDate))->modify('+1 day')->format('Y-m-d') . ' 00:00:00';
        $params += [
            'from_date' => $fromDate . ' 00:00:00',
            'to_date' => $endExclusive,
        ];
        $statement = Database::getConnection()->prepare(<<<SQL
            SELECT COUNT(*)
            FROM ChamCong CC
            INNER JOIN NhanVien NV ON NV.MaNV = CC.MaNV
            WHERE CC.GioVao >= :from_date
                AND CC.GioVao < :to_date
                {$filter}
            SQL);
        $statement->execute($params);

        return (int)$statement->fetchColumn();
    }

    /** Lấy blob ảnh vào/ra; loại không hợp lệ hoặc ảnh NULL trả null. */
    public function findEvidence(int $attendanceId, string $type): ?string
    {
        $column = match ($type) {
            'in' => 'AnhVao',
            'out' => 'AnhRa',
            default => null,
        };
        if ($column === null) {
            return null;
        }

        $statement = Database::getConnection()->prepare(
            "SELECT {$column} FROM ChamCong WHERE MaCC = :attendance_id"
        );
        $statement->execute(['attendance_id' => $attendanceId]);
        $image = $statement->fetchColumn();

        return is_string($image) && $image !== '' ? $image : null;
    }

    public function employeeExists(int $employeeId): bool
    {
        $statement = Database::getConnection()->prepare(
            'SELECT 1 FROM NhanVien WHERE MaNV = :employee_id LIMIT 1'
        );
        $statement->execute(['employee_id' => $employeeId]);

        return $statement->fetchColumn() !== false;
    }

    public function findEmployeeShift(int $employeeId, string $date): ?array
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            SELECT PCN.MaCa, CLV.TenCa, CLV.GioBatDau, CLV.GioKetThuc
            FROM PhanCaNhanVien PCN
            INNER JOIN CaLamViec CLV ON CLV.MaCa = PCN.MaCa
            WHERE PCN.MaNV = :employee_id AND PCN.NgayLamViec = :work_date
            LIMIT 1
            SQL);
        $statement->execute([
            'employee_id' => $employeeId,
            'work_date' => $date,
        ]);
        $shift = $statement->fetch();

        return $shift === false ? null : $shift;
    }

    public function findTodayRecord(int $employeeId, string $date): ?array
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            SELECT MaCC, GioVao, GioRa, MaCa
            FROM ChamCong
            WHERE MaNV = :employee_id AND DATE(GioVao) = :work_date
            LIMIT 1
            SQL);
        $statement->execute([
            'employee_id' => $employeeId,
            'work_date' => $date,
        ]);
        $record = $statement->fetch();

        return $record === false ? null : $record;
    }

    /** Tạo bản ghi check-in và trả MaCC mới; ảnh JPEG được lưu dạng LOB nếu có. */
    public function insertCheckin(int $employeeId, int $deviceId, int $shiftId, ?string $image): int
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            INSERT INTO ChamCong (MaNV, GioVao, GioRa, MaTB, MaCa, AnhVao)
            VALUES (:employee_id, CURRENT_TIMESTAMP, NULL, :device_id, :shift_id, :image)
            SQL);
        $statement->bindValue(':employee_id', $employeeId, PDO::PARAM_INT);
        $statement->bindValue(':device_id', $deviceId, PDO::PARAM_INT);
        $statement->bindValue(':shift_id', $shiftId, PDO::PARAM_INT);
        $statement->bindValue(':image', $image, $image === null ? PDO::PARAM_NULL : PDO::PARAM_LOB);
        $statement->execute();

        return (int)Database::getConnection()->lastInsertId();
    }

    /** Ghi giờ checkout và ảnh ra cho đúng MaCC. */
    public function updateCheckout(int $attendanceId, ?string $image): void
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            UPDATE ChamCong
            SET GioRa = CURRENT_TIMESTAMP, AnhRa = :image
            WHERE MaCC = :attendance_id
            SQL);
        $statement->bindValue(':image', $image, $image === null ? PDO::PARAM_NULL : PDO::PARAM_LOB);
        $statement->bindValue(':attendance_id', $attendanceId, PDO::PARAM_INT);
        $statement->execute();
    }

    private function employeeFilters(?int $employeeId, ?string $keyword, string $alias): array
    {
        $filters = '';
        $params = [];
        if ($employeeId !== null) {
            $filters .= " AND {$alias}.MaNV = :employee_id";
            $params['employee_id'] = $employeeId;
        }
        if ($keyword !== null && trim($keyword) !== '') {
            $filters .= " AND (CAST({$alias}.MaNV AS CHAR) LIKE :keyword_id OR {$alias}.HoTen LIKE :keyword_name)";
            $term = '%' . trim($keyword) . '%';
            $params['keyword_id'] = $term;
            $params['keyword_name'] = $term;
        }

        return [$filters, $params];
    }

    private function attendanceFilters(?int $employeeId, ?string $keyword): array
    {
        $filters = '';
        $params = [];
        if ($employeeId !== null) {
            $filters .= ' AND CC.MaNV = :employee_id';
            $params['employee_id'] = $employeeId;
        }
        if ($keyword !== null && trim($keyword) !== '') {
            $filters .= ' AND (CAST(CC.MaNV AS CHAR) LIKE :keyword_id OR NV.HoTen LIKE :keyword_name)';
            $term = '%' . trim($keyword) . '%';
            $params['keyword_id'] = $term;
            $params['keyword_name'] = $term;
        }

        return [$filters, $params];
    }

    private function fetchPage(string $sql, array $params, ?int $limit, int $offset): array
    {
        if ($limit !== null) {
            $sql .= ' LIMIT :limit OFFSET :offset';
        }
        $statement = Database::getConnection()->prepare($sql);
        foreach ($params as $key => $value) {
            $statement->bindValue(':' . $key, $value, is_int($value) ? PDO::PARAM_INT : PDO::PARAM_STR);
        }
        if ($limit !== null) {
            $statement->bindValue(':limit', $limit, PDO::PARAM_INT);
            $statement->bindValue(':offset', max(0, $offset), PDO::PARAM_INT);
        }
        $statement->execute();

        return $statement->fetchAll();
    }
}

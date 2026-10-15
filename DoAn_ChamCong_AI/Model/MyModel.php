<?php
declare(strict_types=1);

require_once __DIR__ . '/Database.php';

final class MyModel
{
    /** Đọc hồ sơ chỉ theo MaNV đã lấy từ session ở tầng Controller. */
    public function findProfile(int $employeeId): ?array
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            SELECT NV.MaNV, NV.HoTen, NV.MaVaiTro, VT.TenVaiTro
            FROM NhanVien NV
            LEFT JOIN VaiTro VT ON VT.MaVaiTro = NV.MaVaiTro
            WHERE NV.MaNV = :employee_id
            LIMIT 1
            SQL);
        $statement->execute(['employee_id' => $employeeId]);
        $profile = $statement->fetch();

        return $profile === false ? null : $profile;
    }

    /** Lấy ca và chấm công của chính nhân viên trong session cho ngày hiện tại. */
    public function findToday(int $employeeId, string $date): array
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            SELECT CLV.MaCa, CLV.TenCa, CLV.GioBatDau, CLV.GioKetThuc
            FROM PhanCaNhanVien PCN
            INNER JOIN CaLamViec CLV ON CLV.MaCa = PCN.MaCa
            WHERE PCN.MaNV = :employee_id AND PCN.NgayLamViec = :work_date
            LIMIT 1
            SQL);
        $statement->execute(['employee_id' => $employeeId, 'work_date' => $date]);
        $shift = $statement->fetch();

        $start = $date . ' 00:00:00';
        $end = (new DateTimeImmutable($date))->modify('+1 day')->format('Y-m-d') . ' 00:00:00';
        $statement = Database::getConnection()->prepare(<<<'SQL'
            SELECT
                MaCC, GioVao, GioRa,
                CASE WHEN COALESCE(OCTET_LENGTH(AnhVao), 0) > 0 THEN 1 ELSE 0 END AS HasImageIn,
                CASE WHEN COALESCE(OCTET_LENGTH(AnhRa), 0) > 0 THEN 1 ELSE 0 END AS HasImageOut
            FROM ChamCong
            WHERE MaNV = :employee_id AND GioVao >= :day_start AND GioVao < :day_end
            ORDER BY GioVao ASC, MaCC ASC
            LIMIT 1
            SQL);
        $statement->execute([
            'employee_id' => $employeeId,
            'day_start' => $start,
            'day_end' => $end,
        ]);
        $attendance = $statement->fetch();

        return [
            'shift' => $shift === false ? null : $shift,
            'attendance' => $attendance === false ? null : $attendance,
        ];
    }

    public function countAttendanceHistory(int $employeeId, string $fromDate, string $toDate): int
    {
        $pdo = Database::getConnection();
        if ($fromDate === '' && $toDate === '') {
            $statement = $pdo->prepare(<<<'SQL'
                SELECT COUNT(*) FROM (
                    SELECT MaCC FROM ChamCong
                    WHERE MaNV = :employee_id
                    ORDER BY GioVao DESC, MaCC DESC
                    LIMIT 30
                ) RecentAttendance
                SQL);
            $statement->execute(['employee_id' => $employeeId]);
        } else {
            [$where, $params] = $this->historyFilters($employeeId, $fromDate, $toDate);
            $statement = $pdo->prepare('SELECT COUNT(*) FROM ChamCong CC WHERE ' . $where);
            $statement->execute($params);
        }

        return (int)$statement->fetchColumn();
    }

    /** Truy vấn lịch sử chấm công của một MaNV, lọc ngày và phân trang. */
    public function findAttendanceHistory(
        int $employeeId,
        string $fromDate,
        string $toDate,
        int $limit,
        int $offset
    ): array {
        if ($fromDate === '' && $toDate === '') {
            $where = 'CC.MaNV = :employee_id';
            $params = ['employee_id' => $employeeId];
            $recentLimit = 'LIMIT 30';
        } else {
            [$where, $params] = $this->historyFilters($employeeId, $fromDate, $toDate);
            $recentLimit = '';
        }

        $statement = Database::getConnection()->prepare(<<<SQL
            SELECT
                CC.MaCC, CC.MaNV, CC.GioVao, CC.GioRa,
                CLV.TenCa, CLV.GioBatDau, CLV.GioKetThuc,
                CC.HasImageIn, CC.HasImageOut
            FROM (
                SELECT
                    CC.MaCC, CC.MaNV, CC.MaCa, CC.GioVao, CC.GioRa,
                    CASE WHEN COALESCE(OCTET_LENGTH(CC.AnhVao), 0) > 0 THEN 1 ELSE 0 END AS HasImageIn,
                    CASE WHEN COALESCE(OCTET_LENGTH(CC.AnhRa), 0) > 0 THEN 1 ELSE 0 END AS HasImageOut
                FROM ChamCong CC
                WHERE {$where}
                ORDER BY CC.GioVao DESC, CC.MaCC DESC
                {$recentLimit}
            ) CC
            LEFT JOIN CaLamViec CLV ON CLV.MaCa = CC.MaCa
            ORDER BY CC.GioVao DESC, CC.MaCC DESC
            LIMIT :limit OFFSET :offset
            SQL);
        foreach ($params as $name => $value) {
            $statement->bindValue(':' . $name, $value, is_int($value) ? PDO::PARAM_INT : PDO::PARAM_STR);
        }
        $statement->bindValue(':limit', $limit, PDO::PARAM_INT);
        $statement->bindValue(':offset', $offset, PDO::PARAM_INT);
        $statement->execute();

        return $statement->fetchAll();
    }

    /** Lấy lịch sử sức khỏe thuộc riêng một nhân viên. */
    public function findHealth(int $employeeId): array
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            SELECT NhipTim, SpO2, ThoiGian
            FROM LichSuSucKhoe
            WHERE MaNV = :employee_id
            ORDER BY ThoiGian DESC, MaSK DESC
            LIMIT 30
            SQL);
        $statement->execute(['employee_id' => $employeeId]);

        return $statement->fetchAll();
    }

    /** Lấy cảnh báo thuộc riêng một nhân viên cùng loại/trạng thái liên quan. */
    public function findAlerts(int $employeeId): array
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            SELECT
                COALESCE(BH.TenBieuHien, LCB.TenLoaiCB) AS LoaiCanhBao,
                CB.NoiDung,
                CB.ThoiGian
            FROM CanhBao CB
            LEFT JOIN LoaiCanhBao LCB ON LCB.MaLoaiCB = CB.MaLoaiCB
            LEFT JOIN LichSuTrangThai TT ON TT.MaTT = CB.MaTT
            LEFT JOIN DanhMucBieuHien BH ON BH.MaBieuHien = TT.MaBieuHien
            WHERE CB.MaNV = :employee_id
            ORDER BY CB.ThoiGian DESC, CB.MaCB DESC
            LIMIT 20
            SQL);
        $statement->execute(['employee_id' => $employeeId]);

        return $statement->fetchAll();
    }

    /** Trả ảnh bằng chứng chỉ khi MaCC thuộc đúng MaNV đã xác thực. */
    public function findOwnedEvidence(int $attendanceId, int $employeeId, string $type): ?string
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
            "SELECT {$column} FROM ChamCong WHERE MaCC = :attendance_id AND MaNV = :employee_id LIMIT 1"
        );
        $statement->execute(['attendance_id' => $attendanceId, 'employee_id' => $employeeId]);
        $image = $statement->fetchColumn();

        return is_string($image) && $image !== '' ? $image : null;
    }

    private function historyFilters(int $employeeId, string $fromDate, string $toDate): array
    {
        $where = ['CC.MaNV = :employee_id'];
        $params = ['employee_id' => $employeeId];
        if ($fromDate !== '') {
            $where[] = 'CC.GioVao >= :from_date';
            $params['from_date'] = $fromDate . ' 00:00:00';
        }
        if ($toDate !== '') {
            $where[] = 'CC.GioVao < DATE_ADD(:to_date, INTERVAL 1 DAY)';
            $params['to_date'] = $toDate . ' 00:00:00';
        }

        return [implode(' AND ', $where), $params];
    }
}

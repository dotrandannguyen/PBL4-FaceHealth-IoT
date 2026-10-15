<?php
declare(strict_types=1);

require_once __DIR__ . '/Database.php';
require_once __DIR__ . '/AttendanceModel.php';

final class DashboardModel
{
    /** Đọc các KPI, chấm công, hoạt động tuần và cảnh báo cho ngày đã chọn. */
    public function findOverview(string $date): array
    {
        $pdo = Database::getConnection();
        $totalEmployees = (int)$pdo->query('SELECT COUNT(*) FROM NhanVien')->fetchColumn();
        $registeredEmployees = (int)$pdo->query(
            'SELECT COUNT(DISTINCT MaNV) FROM FaceEmbedding'
        )->fetchColumn();

        $attendanceRows = (new AttendanceModel())->findDaily($date);
        $summary = [
            'total_employees' => $totalEmployees,
            'face_registered' => $registeredEmployees,
            'assigned_today' => 0,
            'checked_in' => 0,
            'working' => 0,
            'late' => 0,
            'early' => 0,
            'not_checked' => 0,
        ];

        foreach ($attendanceRows as &$row) {
            $hasShift = $row['TenCa'] !== null;
            $clockIn = $this->formatClock($row['GioVao'] ?? null);
            $clockOut = $this->formatClock($row['GioRa'] ?? null);
            $shiftStart = $this->formatTime($row['GioBatDau'] ?? null);
            $shiftEnd = $this->formatTime($row['GioKetThuc'] ?? null);

            if ($hasShift) {
                $summary['assigned_today']++;
            }

            if ($clockIn === null) {
                $statusIn = 'Chưa chấm công';
                $statusOut = '--';
                $summary['not_checked']++;
            } else {
                $summary['checked_in']++;
                $isLate = $shiftStart !== null && $clockIn > $shiftStart;
                $statusIn = $isLate ? 'Đi trễ' : 'Đúng giờ';
                if ($isLate) {
                    $summary['late']++;
                }

                if ($clockOut === null) {
                    $statusOut = 'Đang làm việc';
                    $summary['working']++;
                } elseif ($shiftEnd !== null && $clockOut < $shiftEnd) {
                    $statusOut = 'Về sớm';
                    $summary['early']++;
                } else {
                    $statusOut = 'Đúng giờ';
                }

            }

            $row['GioVaoDisplay'] = $clockIn ?? '--';
            $row['GioRaDisplay'] = $clockOut ?? '--';
            $row['TenCaDisplay'] = $row['TenCa'] ?? 'Chưa phân ca';
            $row['ThoiGianCa'] = $shiftStart !== null && $shiftEnd !== null
                ? $shiftStart . '–' . $shiftEnd
                : '--';
            $row['TrangThaiVao'] = $statusIn;
            $row['TrangThaiRa'] = $statusOut;
        }
        unset($row);

        $endOfDay = (new DateTimeImmutable($date, new DateTimeZone('Asia/Ho_Chi_Minh')))
            ->modify('+1 day')
            ->format('Y-m-d') . ' 00:00:00';

        $weekStart = (new DateTimeImmutable($date, new DateTimeZone('Asia/Ho_Chi_Minh')))
            ->modify('-6 days')
            ->format('Y-m-d');
        $weeklyStatement = $pdo->prepare(<<<'SQL'
            SELECT
                DATE(GioVao) AS Ngay,
                COUNT(MaCC) AS SoNguoiVao,
                SUM(CASE WHEN GioRa IS NOT NULL THEN 1 ELSE 0 END) AS SoNguoiRa
            FROM ChamCong
            WHERE GioVao >= :week_start AND GioVao < :day_after
            GROUP BY DATE(GioVao)
            ORDER BY Ngay ASC
            SQL);
        $weeklyStatement->execute([
            'week_start' => $weekStart . ' 00:00:00',
            'day_after' => $endOfDay,
        ]);
        $weeklyByDate = [];
        foreach ($weeklyStatement->fetchAll() as $weeklyRow) {
            $weeklyByDate[(string)$weeklyRow['Ngay']] = [
                'check_in' => (int)$weeklyRow['SoNguoiVao'],
                'check_out' => (int)$weeklyRow['SoNguoiRa'],
            ];
        }
        $weekly = [];
        $weekStartDate = new DateTimeImmutable($weekStart, new DateTimeZone('Asia/Ho_Chi_Minh'));
        for ($offset = 0; $offset < 7; $offset++) {
            $day = $weekStartDate->modify('+' . $offset . ' days');
            $dayKey = $day->format('Y-m-d');
            $weekly[] = [
                'date' => $dayKey,
                'label' => ['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7'][(int)$day->format('w')],
                'check_in' => $weeklyByDate[$dayKey]['check_in'] ?? 0,
                'check_out' => $weeklyByDate[$dayKey]['check_out'] ?? 0,
            ];
        }

        $alerts = $pdo->query(<<<'SQL'
            SELECT
                NV.HoTen,
                COALESCE(BH.TenBieuHien, LCB.TenLoaiCB) AS LoaiCanhBao,
                CB.ThoiGian
            FROM CanhBao CB
            LEFT JOIN NhanVien NV ON NV.MaNV = CB.MaNV
            LEFT JOIN LoaiCanhBao LCB ON LCB.MaLoaiCB = CB.MaLoaiCB
            LEFT JOIN LichSuTrangThai TT ON TT.MaTT = CB.MaTT
            LEFT JOIN DanhMucBieuHien BH ON BH.MaBieuHien = TT.MaBieuHien
            ORDER BY CB.ThoiGian DESC, CB.MaCB DESC
            LIMIT 5
            SQL)->fetchAll();

        return [
            'date' => $date,
            'summary' => $summary,
            'attendance' => $attendanceRows,
            'weekly' => $weekly,
            'alerts' => $alerts,
        ];
    }

    private function formatClock(mixed $value): ?string
    {
        if ($value === null || $value === '') {
            return null;
        }

        return (new DateTimeImmutable((string)$value))->format('H:i:s');
    }

    private function formatTime(mixed $value): ?string
    {
        if ($value === null || $value === '') {
            return null;
        }

        return substr((string)$value, 0, 8);
    }
}

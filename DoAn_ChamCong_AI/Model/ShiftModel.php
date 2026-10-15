<?php
declare(strict_types=1);

require_once __DIR__ . '/Database.php';

final class ShiftModel
{
    /** Lấy toàn bộ danh mục ca cùng trạng thái và số lượt sử dụng. */
    public function findAll(): array
    {
        return Database::getConnection()->query(<<<'SQL'
            SELECT
                CLV.MaCa,
                CLV.TenCa,
                CLV.GioBatDau,
                CLV.GioKetThuc,
                CLV.TrangThai,
                (SELECT COUNT(*) FROM PhanCaNhanVien PCN WHERE PCN.MaCa = CLV.MaCa) AS SoPhanCa,
                (SELECT COUNT(*) FROM ChamCong CC WHERE CC.MaCa = CLV.MaCa) AS SoChamCong
            FROM CaLamViec CLV
            ORDER BY CLV.GioBatDau, CLV.MaCa
            SQL)->fetchAll();
    }

    /** Lấy riêng các ca đang sử dụng để phân ca mới hoặc đổi ca. */
    public function findActive(): array
    {
        return Database::getConnection()->query(<<<'SQL'
            SELECT MaCa, TenCa, GioBatDau, GioKetThuc
            FROM CaLamViec
            WHERE TrangThai = 1
            ORDER BY GioBatDau, MaCa
            SQL)->fetchAll();
    }

    /** Tìm một ca theo mã, không loại ca đã ngừng sử dụng khỏi lịch sử. */
    public function findById(int $shiftId): ?array
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            SELECT MaCa, TenCa, GioBatDau, GioKetThuc, TrangThai
            FROM CaLamViec
            WHERE MaCa = :shift_id
            LIMIT 1
            SQL);
        $statement->execute(['shift_id' => $shiftId]);
        $shift = $statement->fetch();

        return $shift === false ? null : $shift;
    }

    public function findEmployees(): array
    {
        return Database::getConnection()->query(<<<'SQL'
            SELECT MaNV, HoTen
            FROM NhanVien
            ORDER BY MaNV
            SQL)->fetchAll();
    }

    /** Lấy các phân ca trong một ngày, kèm tên nhân viên và thông tin ca. */
    public function findAssignmentsByDate(string $date): array
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            SELECT
                PCN.MaPhanCa,
                PCN.MaNV,
                NV.HoTen,
                PCN.MaCa,
                CLV.TenCa,
                CLV.GioBatDau,
                CLV.GioKetThuc,
                PCN.NgayLamViec
            FROM PhanCaNhanVien PCN
            INNER JOIN NhanVien NV ON NV.MaNV = PCN.MaNV
            INNER JOIN CaLamViec CLV ON CLV.MaCa = PCN.MaCa
            WHERE PCN.NgayLamViec = :work_date
            ORDER BY NV.MaNV
            SQL);
        $statement->execute(['work_date' => $date]);

        return $statement->fetchAll();
    }

    public function findAssignmentById(int $assignmentId): ?array
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            SELECT
                PCN.MaPhanCa,
                PCN.MaNV,
                NV.HoTen,
                PCN.MaCa,
                CLV.TenCa,
                CLV.GioBatDau,
                CLV.GioKetThuc,
                PCN.NgayLamViec
            FROM PhanCaNhanVien PCN
            INNER JOIN NhanVien NV ON NV.MaNV = PCN.MaNV
            INNER JOIN CaLamViec CLV ON CLV.MaCa = PCN.MaCa
            WHERE PCN.MaPhanCa = :assignment_id
            LIMIT 1
            SQL);
        $statement->execute(['assignment_id' => $assignmentId]);
        $assignment = $statement->fetch();

        return $assignment === false ? null : $assignment;
    }

    public function employeeExists(int $employeeId): bool
    {
        return $this->exists('NhanVien', 'MaNV', $employeeId);
    }

    public function shiftExists(int $shiftId): bool
    {
        return $this->exists('CaLamViec', 'MaCa', $shiftId);
    }

    /** Xác nhận ca còn được phép dùng cho phân ca mới. */
    public function isActiveShift(int $shiftId): bool
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            SELECT 1
            FROM CaLamViec
            WHERE MaCa = :shift_id AND TrangThai = 1
            LIMIT 1
            SQL);
        $statement->execute(['shift_id' => $shiftId]);

        return $statement->fetchColumn() !== false;
    }

    /** Kiểm tra tổ hợp tên và giờ đã tồn tại, có thể bỏ qua một mã khi sửa. */
    public function duplicateShiftExists(
        string $name,
        string $startTime,
        string $endTime,
        ?int $excludeShiftId = null
    ): bool {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            SELECT 1
            FROM CaLamViec
            WHERE TenCa = :name
                AND GioBatDau = :start_time
                AND GioKetThuc = :end_time
                AND (:exclude_null IS NULL OR MaCa <> :exclude_id)
            LIMIT 1
            SQL);
        $statement->execute([
            'name' => $name,
            'start_time' => $startTime,
            'end_time' => $endTime,
            'exclude_null' => $excludeShiftId,
            'exclude_id' => $excludeShiftId,
        ]);

        return $statement->fetchColumn() !== false;
    }

    /** Tạo ca mới nếu tổ hợp tên và giờ chưa có trong danh mục. */
    public function createShift(string $name, string $startTime, string $endTime): bool
    {
        if ($this->duplicateShiftExists($name, $startTime, $endTime)) {
            return false;
        }

        $statement = Database::getConnection()->prepare(<<<'SQL'
            INSERT INTO CaLamViec (TenCa, GioBatDau, GioKetThuc, TrangThai)
            VALUES (:name, :start_time, :end_time, 1)
            SQL);
        $statement->execute([
            'name' => $name,
            'start_time' => $startTime,
            'end_time' => $endTime,
        ]);

        return true;
    }

    /**
     * Cập nhật ca; nếu đã có chấm công thì chỉ cho đổi tên, giữ nguyên giờ.
     *
     * @return string updated, duplicate, time_locked, or not_found
     */
    public function updateShift(int $shiftId, string $name, string $startTime, string $endTime): string
    {
        $pdo = Database::getConnection();
        $pdo->beginTransaction();

        try {
            $lock = $pdo->prepare('SELECT GioBatDau, GioKetThuc FROM CaLamViec WHERE MaCa = :id FOR UPDATE');
            $lock->execute(['id' => $shiftId]);
            $current = $lock->fetch();
            if ($current === false) {
                $pdo->rollBack();
                return 'not_found';
            }

            if ($this->duplicateShiftExists($name, $startTime, $endTime, $shiftId)) {
                $pdo->rollBack();
                return 'duplicate';
            }

            $timesChanged = substr((string)$current['GioBatDau'], 0, 8) !== $startTime
                || substr((string)$current['GioKetThuc'], 0, 8) !== $endTime;
            if ($timesChanged && $this->hasAttendance($shiftId)) {
                $pdo->rollBack();
                return 'time_locked';
            }

            $update = $pdo->prepare(<<<'SQL'
                UPDATE CaLamViec
                SET TenCa = :name, GioBatDau = :start_time, GioKetThuc = :end_time
                WHERE MaCa = :shift_id
                SQL);
            $update->execute([
                'name' => $name,
                'start_time' => $startTime,
                'end_time' => $endTime,
                'shift_id' => $shiftId,
            ]);
            $pdo->commit();

            return 'updated';
        } catch (Throwable $exception) {
            if ($pdo->inTransaction()) {
                $pdo->rollBack();
            }
            throw $exception;
        }
    }

    /** Xóa ca chỉ khi không còn phân ca hoặc chấm công tham chiếu đến ca đó. */
    public function deleteShift(int $shiftId): string
    {
        $pdo = Database::getConnection();
        $pdo->beginTransaction();

        try {
            $lock = $pdo->prepare('SELECT MaCa FROM CaLamViec WHERE MaCa = :id FOR UPDATE');
            $lock->execute(['id' => $shiftId]);
            if ($lock->fetchColumn() === false) {
                $pdo->rollBack();
                return 'not_found';
            }

            if ($this->hasAssignments($shiftId) || $this->hasAttendance($shiftId)) {
                $pdo->commit();
                return 'used';
            }

            $delete = $pdo->prepare('DELETE FROM CaLamViec WHERE MaCa = :id');
            $delete->execute(['id' => $shiftId]);
            $pdo->commit();

            return 'deleted';
        } catch (Throwable $exception) {
            if ($pdo->inTransaction()) {
                $pdo->rollBack();
            }
            throw $exception;
        }
    }

    /** Ngừng sử dụng ca mà không xóa các tham chiếu lịch sử. */
    public function disableShift(int $shiftId): bool
    {
        return $this->setShiftStatus($shiftId, 0);
    }

    /** Kích hoạt lại ca hiện có, không tạo bản ghi mới. */
    public function enableShift(int $shiftId): bool
    {
        return $this->setShiftStatus($shiftId, 1);
    }

    /** Kiểm tra ca có phân công lịch sử hay không. */
    public function hasAssignments(int $shiftId): bool
    {
        return $this->countUsage($shiftId)['assignments'] > 0;
    }

    /** Kiểm tra ca có dữ liệu chấm công tham chiếu hay không. */
    public function hasAttendance(int $shiftId): bool
    {
        return $this->countUsage($shiftId)['attendance'] > 0;
    }

    /** Đếm riêng số phân ca và số lượt chấm công đang tham chiếu tới ca. */
    public function countUsage(int $shiftId): array
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            SELECT
                (SELECT COUNT(*) FROM PhanCaNhanVien WHERE MaCa = :assignment_shift_id) AS assignments,
                (SELECT COUNT(*) FROM ChamCong WHERE MaCa = :attendance_shift_id) AS attendance
            SQL);
        $statement->execute([
            'assignment_shift_id' => $shiftId,
            'attendance_shift_id' => $shiftId,
        ]);
        $counts = $statement->fetch();

        return [
            'assignments' => (int)$counts['assignments'],
            'attendance' => (int)$counts['attendance'],
        ];
    }

    /** Tạo phân ca; nếu nhân viên đã có phân ca ngày đó thì cập nhật sang ca mới. */
    public function saveAssignment(int $employeeId, int $shiftId, string $date): void
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            INSERT INTO PhanCaNhanVien (MaNV, MaCa, NgayLamViec)
            SELECT :employee_id, CLV.MaCa, :work_date
            FROM CaLamViec CLV
            WHERE CLV.MaCa = :shift_id AND CLV.TrangThai = 1
            ON DUPLICATE KEY UPDATE MaCa = VALUES(MaCa)
            SQL);
        $statement->execute([
            'employee_id' => $employeeId,
            'shift_id' => $shiftId,
            'work_date' => $date,
        ]);
    }

    /** Đổi ca của bản phân công đã tồn tại mà không thay nhân viên/ngày. */
    public function updateAssignmentShift(int $assignmentId, int $shiftId): void
    {
        $statement = Database::getConnection()->prepare(<<<'SQL'
            UPDATE PhanCaNhanVien
            SET MaCa = :shift_id
            WHERE MaPhanCa = :assignment_id
                AND EXISTS (
                    SELECT 1 FROM CaLamViec
                    WHERE MaCa = :active_shift_id AND TrangThai = 1
                )
            SQL);
        $statement->execute([
            'shift_id' => $shiftId,
            'assignment_id' => $assignmentId,
            'active_shift_id' => $shiftId,
        ]);
    }

    /** Hủy phân ca nguyên tử; giữ phân công nếu đã phát sinh chấm công trong ngày đó. */
    public function unassignAssignment(int $assignmentId): array
    {
        $pdo = Database::getConnection();
        $pdo->beginTransaction();
        try {
            $statement = $pdo->prepare(<<<'SQL'
                SELECT MaNV, NgayLamViec
                FROM PhanCaNhanVien
                WHERE MaPhanCa = :assignment_id
                FOR UPDATE
                SQL);
            $statement->execute(['assignment_id' => $assignmentId]);
            $assignment = $statement->fetch();
            if ($assignment === false) {
                $pdo->rollBack();
                return ['status' => 'not_found', 'date' => null];
            }

            $workDate = (string)$assignment['NgayLamViec'];
            $dayStart = $workDate . ' 00:00:00';
            $dayEnd = (new DateTimeImmutable($workDate))->modify('+1 day')->format('Y-m-d') . ' 00:00:00';
            $attendance = $pdo->prepare(<<<'SQL'
                SELECT 1
                FROM ChamCong
                WHERE MaNV = :employee_id
                    AND GioVao >= :day_start
                    AND GioVao < :day_end
                LIMIT 1
                SQL);
            $attendance->execute([
                'employee_id' => (int)$assignment['MaNV'],
                'day_start' => $dayStart,
                'day_end' => $dayEnd,
            ]);
            if ($attendance->fetchColumn() !== false) {
                $pdo->commit();
                return ['status' => 'attendance_exists', 'date' => $workDate];
            }

            $delete = $pdo->prepare(
                'DELETE FROM PhanCaNhanVien WHERE MaPhanCa = :assignment_id'
            );
            $delete->execute(['assignment_id' => $assignmentId]);
            $pdo->commit();

            return ['status' => 'deleted', 'date' => $workDate];
        } catch (Throwable $exception) {
            if ($pdo->inTransaction()) {
                $pdo->rollBack();
            }
            throw $exception;
        }
    }

    private function exists(string $table, string $column, int $id): bool
    {
        $statement = Database::getConnection()->prepare(
            "SELECT 1 FROM {$table} WHERE {$column} = :id LIMIT 1"
        );
        $statement->execute(['id' => $id]);

        return $statement->fetchColumn() !== false;
    }

    private function setShiftStatus(int $shiftId, int $status): bool
    {
        $statement = Database::getConnection()->prepare(
            'UPDATE CaLamViec SET TrangThai = :status WHERE MaCa = :shift_id'
        );
        $statement->execute(['status' => $status, 'shift_id' => $shiftId]);

        return $statement->rowCount() > 0 || $this->shiftExists($shiftId);
    }
}

<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/AttendanceModel.php';

final class AttendanceService
{
    private AttendanceModel $attendance;

    public function __construct()
    {
        $this->attendance = new AttendanceModel();
    }

    /**
     * Áp dụng nghiệp vụ check-in/check-out cho nhân viên, ca và thiết bị đã xác định.
     * Transaction ngoài (nếu có) được giữ quyền sở hữu; nếu không, service tự quản lý.
     */
    public function process(int $employeeId, int $deviceId, ?string $image, string $theTrang = 'Bình thường'): array
    {
        $pdo = Database::getConnection();
        $ownsTransaction = !$pdo->inTransaction();
        if ($ownsTransaction) {
            $pdo->beginTransaction();
        }

        try {
            if (!$this->attendance->employeeExists($employeeId)) {
                $this->attendance->ensureEmployee($employeeId, "Nhân viên #{$employeeId}");
            }

            $today = (new DateTimeImmutable('now', new DateTimeZone('Asia/Ho_Chi_Minh')))->format('Y-m-d');
            $shift = $this->attendance->findEmployeeShift($employeeId, $today);
            if ($shift === null) {
                $shift = $this->attendance->findDefaultActiveShift();
            }
            if ($shift === null) {
                return $this->finish($pdo, $ownsTransaction, $this->error('Không tìm thấy ca làm việc khả dụng'));
            }

            $todayRecord = $this->attendance->findTodayRecord($employeeId, $today);
            if ($todayRecord === null) {
                try {
                    $this->attendance->insertCheckin($employeeId, $deviceId, (int)$shift['MaCa'], $image, $theTrang);
                } catch (Throwable $exception) {
                    return $this->fail($pdo, $ownsTransaction, 'Lỗi check-in: ' . $exception->getMessage());
                }

                return $this->finish($pdo, $ownsTransaction, [
                    'action' => 'checkin',
                    'status' => 'success',
                    'message' => 'Chấm công vào thành công — Ca: ' . $shift['TenCa'],
                    'MaCa' => (int)$shift['MaCa'],
                    'TenCa' => (string)$shift['TenCa'],
                    'TheTrang' => $theTrang,
                ]);
            }

            if ($todayRecord['GioVao'] !== null && $todayRecord['GioRa'] === null) {
                try {
                    $this->attendance->updateCheckout((int)$todayRecord['MaCC'], $image, $theTrang);
                } catch (Throwable $exception) {
                    return $this->fail($pdo, $ownsTransaction, 'Lỗi check-out: ' . $exception->getMessage());
                }

                return $this->finish($pdo, $ownsTransaction, [
                    'action' => 'checkout',
                    'status' => 'success',
                    'message' => 'Chấm công ra thành công — Ca: ' . $shift['TenCa'],
                    'MaCa' => (int)$shift['MaCa'],
                    'TenCa' => (string)$shift['TenCa'],
                    'TheTrang' => $theTrang,
                ]);
            }

            return $this->finish($pdo, $ownsTransaction, [
                'action' => 'completed',
                'status' => 'completed',
                'message' => 'Hôm nay bạn đã hoàn thành ca làm việc, không cần chấm công nữa!',
                'MaCa' => (int)$shift['MaCa'],
                'TenCa' => (string)$shift['TenCa'],
            ]);
        } catch (Throwable $exception) {
            return $this->fail($pdo, $ownsTransaction, 'Lỗi truy vấn chấm công: ' . $exception->getMessage());
        }
    }

    private function error(string $message): array
    {
        return ['action' => 'error', 'status' => 'error', 'message' => $message];
    }

    private function finish(PDO $pdo, bool $ownsTransaction, array $result): array
    {
        if ($ownsTransaction && $pdo->inTransaction()) {
            $pdo->commit();
        }

        return $result;
    }

    private function fail(PDO $pdo, bool $ownsTransaction, string $message): array
    {
        if ($ownsTransaction && $pdo->inTransaction()) {
            $pdo->rollBack();
        }

        return $this->error($message);
    }
}

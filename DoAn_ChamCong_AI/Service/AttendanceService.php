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
    public function process(int $employeeId, int $deviceId, ?string $image): array
    {
        $pdo = Database::getConnection();
        $ownsTransaction = !$pdo->inTransaction();
        if ($ownsTransaction) {
            $pdo->beginTransaction();
        }

        try {
            if (!$this->attendance->employeeExists($employeeId)) {
                return $this->finish($pdo, $ownsTransaction, $this->error('Không tìm thấy nhân viên'));
            }

            $today = (new DateTimeImmutable('now', new DateTimeZone('Asia/Ho_Chi_Minh')))->format('Y-m-d');
            $shift = $this->attendance->findEmployeeShift($employeeId, $today);
            if ($shift === null) {
                return $this->finish($pdo, $ownsTransaction, $this->error('Nhân viên chưa được phân ca hôm nay'));
            }

            $todayRecord = $this->attendance->findTodayRecord($employeeId, $today);
            if ($todayRecord === null) {
                try {
                    $this->attendance->insertCheckin($employeeId, $deviceId, (int)$shift['MaCa'], $image);
                } catch (Throwable $exception) {
                    return $this->fail($pdo, $ownsTransaction, 'Lỗi check-in: ' . $exception->getMessage());
                }

                return $this->finish($pdo, $ownsTransaction, [
                    'action' => 'checkin',
                    'status' => 'success',
                    'message' => 'Chấm công vào thành công — Ca: ' . $shift['TenCa'],
                    'MaCa' => (int)$shift['MaCa'],
                    'TenCa' => (string)$shift['TenCa'],
                ]);
            }

            if ($todayRecord['GioVao'] !== null && $todayRecord['GioRa'] === null) {
                try {
                    $this->attendance->updateCheckout((int)$todayRecord['MaCC'], $image);
                } catch (Throwable $exception) {
                    return $this->fail($pdo, $ownsTransaction, 'Lỗi check-out: ' . $exception->getMessage());
                }

                return $this->finish($pdo, $ownsTransaction, [
                    'action' => 'checkout',
                    'status' => 'success',
                    'message' => 'Chấm công ra thành công — Ca: ' . $shift['TenCa'],
                    'MaCa' => (int)$shift['MaCa'],
                    'TenCa' => (string)$shift['TenCa'],
                ]);
            }

            return $this->finish($pdo, $ownsTransaction, [
                'action' => 'completed',
                'status' => 'success',
                'message' => 'Đã hoàn tất chấm công hôm nay',
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

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

    /** One transaction covers the event, attendance, health and alerts. */
    public function processEvent(array $event): array
    {
        $pdo = Database::getConnection();
        if ($pdo->inTransaction()) {
            throw new LogicException('AttendanceService requires its own transaction.');
        }
        $pdo->beginTransaction();
        try {
            // Serialize all events for an employee, including an absent daily record.
            $lock = $pdo->prepare('SELECT MaNV FROM NhanVien WHERE MaNV = :id FOR UPDATE');
            $lock->execute(['id' => $event['MaNV']]);
            if ($lock->fetchColumn() === false) {
                throw new DomainException('Nhân viên chưa được đăng ký.');
            }
            $existing = $pdo->prepare('SELECT RequestHash, ResultJson FROM AttendanceEvent WHERE EventId = :id FOR UPDATE');
            $existing->execute(['id' => $event['event_id']]);
            $saved = $existing->fetch();
            if ($saved !== false) {
                if (!hash_equals($saved['RequestHash'], $event['request_hash'])) {
                    throw new DomainException('event_id đã được sử dụng với dữ liệu khác.');
                }
                $result = json_decode($saved['ResultJson'], true, 512, JSON_THROW_ON_ERROR);
                $pdo->commit();
                $result['duplicate'] = true;
                return $result;
            }
            $device = $pdo->prepare('SELECT MaTB FROM ThietBi WHERE MaTB = :id');
            $device->execute(['id' => $event['MaTB']]);
            if ($device->fetchColumn() === false) {
                throw new DomainException('Thiết bị chưa được đăng ký.');
            }
            $pdo->prepare('INSERT INTO AttendanceEvent (EventId, RequestHash, MaNV, MaTB, OccurredAt) VALUES (:event, :hash, :employee, :device, :occurred)')
                ->execute(['event' => $event['event_id'], 'hash' => $event['request_hash'],
                    'employee' => $event['MaNV'], 'device' => $event['MaTB'], 'occurred' => $event['occurred_at']]);

            $record = $this->attendance->findTodayRecord($event['MaNV'], $event['work_date']);
            if ($record !== null && $record['MaCa'] !== null) {
                $shift = $this->attendance->findRecordedShift((int)$record['MaCa']);
            } else {
                $shift = $this->attendance->findEmployeeShift($event['MaNV'], $event['work_date']);
                if ($shift === null) {
                    $shift = $this->attendance->findDefaultActiveShift();
                }
            }
            if ($shift === null) {
                throw new DomainException('Không tìm thấy ca làm việc khả dụng.');
            }
            if ($record !== null && $event['occurred_at'] <= $record['GioVao']) {
                throw new DomainException('Sự kiện đến sai thứ tự thời gian.');
            }
            $result = ['status' => 'success', 'event_id' => $event['event_id'],
                'MaCa' => (int)$shift['MaCa'], 'TenCa' => $shift['TenCa'], 'TheTrang' => $event['status_label']];
            if ($record === null) {
                $attendanceId = $this->attendance->insertCheckin($event['MaNV'], $event['MaTB'],
                    (int)$shift['MaCa'], $event['image'], $event['status_label'], $event['occurred_at']);
                $result += ['action' => 'checkin', 'message' => 'Chấm công vào thành công.'];
            } elseif ($record['GioRa'] === null) {
                $this->attendance->updateCheckout((int)$record['MaCC'], $event['image'],
                    $event['status_label'], $event['occurred_at']);
                $attendanceId = (int)$record['MaCC'];
                $result += ['action' => 'checkout', 'message' => 'Chấm công ra thành công.'];
            } else {
                $attendanceId = (int)$record['MaCC'];
                $result['status'] = 'completed';
                $result += ['action' => 'completed', 'message' => 'Hôm nay bạn đã hoàn thành ca làm việc.'];
            }
            $result['MaCC'] = $attendanceId;
            if ($result['status'] === 'success') {
                $this->recordHealthAndAlerts($pdo, $event);
            }
            $pdo->prepare('UPDATE AttendanceEvent SET ResultJson = :result WHERE EventId = :event')
                ->execute(['result' => json_encode($result, JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE),
                           'event' => $event['event_id']]);
            $pdo->commit();
            return $result;
        } catch (Throwable $exception) {
            if ($pdo->inTransaction()) {
                $pdo->rollBack();
            }
            if ($exception instanceof DomainException) {
                return ['action' => 'error', 'status' => 'error', 'message' => $exception->getMessage(), 'http_status' => 409];
            }
            error_log('Attendance transaction failed: ' . $exception->getMessage());
            return ['action' => 'error', 'status' => 'error', 'message' => 'Không thể lưu chấm công. Vui lòng thử lại cùng event_id.', 'http_status' => 503];
        }
    }

    private function recordHealthAndAlerts(PDO $pdo, array $event): void
    {
        $hr = $event['NhipTim'];
        $spo2 = $event['SpO2'];
        if ($hr !== null || $spo2 !== null) {
            $pdo->prepare('INSERT INTO LichSuSucKhoe (MaNV, NhipTim, SpO2, TheTrang, ThoiGian) VALUES (:employee, :hr, :spo2, :status, :occurred)')
                ->execute(['employee' => $event['MaNV'], 'hr' => $hr, 'spo2' => $spo2,
                    'status' => $event['status_label'], 'occurred' => $event['occurred_at']]);
        }
        $codes = ['Normal' => 1, 'Fatigue' => 2, 'Exhausted' => 3];
        $stateId = null;
        if (isset($codes[$event['raw_status']])) {
            $pdo->prepare('INSERT INTO LichSuTrangThai (MaNV, MaBieuHien, ThoiGian) VALUES (:employee, :state, :occurred)')
                ->execute(['employee' => $event['MaNV'], 'state' => $codes[$event['raw_status']], 'occurred' => $event['occurred_at']]);
            $stateId = (int)$pdo->lastInsertId();
        }
        $alerts = [];
        if ($event['raw_status'] === 'Exhausted') {
            $alerts[] = [2, 'Phát hiện thể trạng kiệt sức khi chấm công.'];
        } elseif ($event['raw_status'] === 'Fatigue') {
            $alerts[] = [2, 'Phát hiện thể trạng mệt mỏi khi chấm công.'];
        }
        // Same warning boundaries as Python fusion; these are software rules.
        if ($spo2 !== null && $spo2 < 96) {
            $alerts[] = [1, 'Chỉ số SpO2 nằm ngoài ngưỡng cấu hình.'];
        }
        if ($hr !== null && ($hr > 100 || $hr < 60)) {
            $alerts[] = [1, 'Nhịp tim nằm ngoài ngưỡng cấu hình.'];
        }
        $insert = $pdo->prepare('INSERT INTO CanhBao (MaNV, MaLoaiCB, NoiDung, ThoiGian, MaTT, MaTB) VALUES (:employee, :category, :message, :occurred, :state, :device)');
        foreach ($alerts as [$category, $message]) {
            $insert->execute(['employee' => $event['MaNV'], 'category' => $category, 'message' => $message,
                'occurred' => $event['occurred_at'], 'state' => $stateId, 'device' => $event['MaTB']]);
        }
    }
}

<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/MyModel.php';
require_once __DIR__ . '/AuthController.php';

final class MyController
{
    private const EMPLOYEE_ROLE_ID = 2;
    private const PAGE_SIZE = 10;

    private MyModel $my;

    public function __construct()
    {
        $this->my = new MyModel();
    }

    /** Tải profile và dữ liệu self-service theo MaNV trong session hiện tại. */
    public function index(): void
    {
        AuthController::requireAuthenticated();
        $roleId = (int)($_SESSION['ma_vai_tro'] ?? 0);
        if ($roleId === 1) {
            header('Location: /?action=dashboard', true, 302);
            exit;
        }
        if ($roleId !== self::EMPLOYEE_ROLE_ID) {
            $this->forbidden();
        }

        $employeeId = filter_var($_SESSION['ma_nv'] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
        if (!is_int($employeeId)) {
            $this->forbidden();
        }

        $fromDate = $this->queryText('from_date');
        $toDate = $this->queryText('to_date');
        $activeTab = $this->queryText('tab');
        if (!in_array($activeTab, ['today', 'history', 'monitoring'], true)) {
            $activeTab = 'today';
        }
        $pageInput = $this->queryText('page') ?: '1';
        $page = filter_var($pageInput, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1, 'max_range' => 1000000]]);
        $page = is_int($page) ? $page : 1;
        $errors = [];
        foreach (['from_date', 'to_date'] as $key) {
            $value = $key === 'from_date' ? $fromDate : $toDate;
            if ($value !== '' && !$this->isValidDate($value)) {
                if ($key === 'from_date') {
                    $fromDate = '';
                } else {
                    $toDate = '';
                }
                $errors[$key] = 'Ngày không hợp lệ.';
            }
        }
        if ($fromDate !== '' && $toDate !== '' && $fromDate > $toDate) {
            $errors['date_range'] = 'Ngày bắt đầu không được sau ngày kết thúc.';
            $fromDate = $toDate = '';
        }

        $profile = null;
        $today = ['shift' => null, 'attendance' => null];
        $attendanceRows = $healthRows = $alertRows = [];
        $totalRows = 0;
        $error = null;
        $todayDate = (new DateTimeImmutable('now', new DateTimeZone('Asia/Ho_Chi_Minh')))->format('Y-m-d');
        try {
            $profile = $this->my->findProfile($employeeId);
            if ($profile === null) {
                $this->forbidden();
            }
            $today = $this->my->findToday($employeeId, $todayDate);
            $totalRows = $this->my->countAttendanceHistory($employeeId, $fromDate, $toDate);
            $totalPages = max(1, (int)ceil($totalRows / self::PAGE_SIZE));
            $page = min($page, $totalPages);
            $attendanceRows = $this->my->findAttendanceHistory(
                $employeeId,
                $fromDate,
                $toDate,
                self::PAGE_SIZE,
                ($page - 1) * self::PAGE_SIZE
            );
            $healthRows = $this->my->findHealth($employeeId);
            $alertRows = $this->my->findAlerts($employeeId);
        } catch (Throwable $exception) {
            error_log('Self-service read failed: ' . $exception->getMessage());
            http_response_code(500);
            $error = 'Không thể tải dữ liệu cá nhân. Vui lòng thử lại sau.';
        }

        foreach ($attendanceRows as &$row) {
            $row['Statuses'] = $this->calculateStatuses(
                $row['GioBatDau'] ?? null,
                $row['GioKetThuc'] ?? null,
                $row['GioVao'] ?? null,
                $row['GioRa'] ?? null
            );
        }
        unset($row);

        $todayStatuses = $this->calculateStatuses(
            $today['shift']['GioBatDau'] ?? null,
            $today['shift']['GioKetThuc'] ?? null,
            $today['attendance']['GioVao'] ?? null,
            $today['attendance']['GioRa'] ?? null
        );
        $today['statuses'] = $todayStatuses;
        $today['summary'] = $this->aggregateStatus($todayStatuses, $today['shift'] !== null, $today['attendance']);
        $totalPages = max(1, (int)ceil($totalRows / self::PAGE_SIZE));
        $pageTitle = 'Trang của tôi';
        require __DIR__ . '/../View/my.php';
    }

    /** Trả ảnh chấm công chỉ sau khi xác nhận bản ghi thuộc MaNV trong session. */
    public function sendEvidence(string $type): void
    {
        AuthController::requireAuthenticated();
        if ((int)($_SESSION['ma_vai_tro'] ?? 0) !== self::EMPLOYEE_ROLE_ID) {
            $this->forbidden();
        }
        $employeeId = filter_var($_SESSION['ma_nv'] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
        $attendanceId = filter_var($_GET['id'] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
        if (!is_int($employeeId) || !is_int($attendanceId) || !in_array($type, ['in', 'out'], true)) {
            $this->notFound();
        }

        try {
            $image = $this->my->findOwnedEvidence($attendanceId, $employeeId, $type);
        } catch (Throwable $exception) {
            error_log('Self-service evidence read failed: ' . $exception->getMessage());
            http_response_code(500);
            exit('Không thể tải ảnh bằng chứng.');
        }
        if ($image === null) {
            $this->notFound();
        }

        $mimeType = (new finfo(FILEINFO_MIME_TYPE))->buffer($image);
        if (!is_string($mimeType) || !str_starts_with($mimeType, 'image/')) {
            $this->notFound();
        }
        header('Content-Type: ' . $mimeType);
        header('Content-Length: ' . strlen($image));
        header('Cache-Control: private, no-store');
        header('X-Content-Type-Options: nosniff');
        echo $image;
    }

    private function calculateStatuses(?string $shiftStart, ?string $shiftEnd, ?string $checkIn, ?string $checkOut): array
    {
        if ($checkIn === null || $checkIn === '') {
            return ['entry' => 'Chưa chấm công', 'exit' => '--', 'overall' => 'Chưa chấm công'];
        }

        $entryTime = (new DateTimeImmutable($checkIn))->format('H:i:s');
        $startTime = $shiftStart === null ? null : substr($shiftStart, 0, 8);
        $entry = $startTime !== null && $entryTime > $startTime ? 'Đi trễ' : 'Đúng giờ';
        if ($checkOut === null || $checkOut === '') {
            $exit = 'Đang làm việc';
        } else {
            $exitTime = (new DateTimeImmutable($checkOut))->format('H:i:s');
            $endTime = $shiftEnd === null ? null : substr($shiftEnd, 0, 8);
            $exit = $endTime !== null && $exitTime < $endTime ? 'Về sớm' : 'Đúng giờ';
        }

        $overall = $exit === 'Đang làm việc'
            ? $entry . ' · Đang làm việc'
            : ($entry === 'Đúng giờ' && $exit === 'Đúng giờ' ? 'Hoàn thành' : $entry . ' · ' . $exit);

        return ['entry' => $entry, 'exit' => $exit, 'overall' => $overall];
    }

    private function aggregateStatus(array $statuses, bool $hasShift, ?array $attendance): string
    {
        if ($attendance === null) {
            return 'Chưa chấm công';
        }
        if ($hasShift) {
            return $statuses['overall'];
        }

        return !empty($attendance['GioRa']) ? 'Đã chấm công ra' : 'Đang làm việc';
    }

    private function queryText(string $key): string
    {
        $value = $_GET[$key] ?? '';

        return is_string($value) || is_numeric($value) ? trim((string)$value) : '';
    }

    private function isValidDate(string $value): bool
    {
        $date = DateTimeImmutable::createFromFormat('!Y-m-d', $value);
        $errors = DateTimeImmutable::getLastErrors();

        return $date !== false
            && $date->format('Y-m-d') === $value
            && ($errors === false || ($errors['warning_count'] === 0 && $errors['error_count'] === 0));
    }

    private function forbidden(): void
    {
        http_response_code(403);
        $authUser = [
            'display_name' => (string)($_SESSION['display_name'] ?? ''),
            'role' => (string)($_SESSION['role'] ?? ''),
        ];
        $pageTitle = 'Không đủ quyền';
        require __DIR__ . '/../View/forbidden.php';
        exit;
    }

    private function notFound(): void
    {
        http_response_code(404);
        exit('Không tìm thấy ảnh bằng chứng.');
    }
}

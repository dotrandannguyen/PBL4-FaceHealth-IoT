<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/ShiftModel.php';
require_once __DIR__ . '/AuthController.php';
require_once __DIR__ . '/../Security/CsrfToken.php';

final class ShiftController
{
    private ShiftModel $shifts;

    public function __construct()
    {
        $this->shifts = new ShiftModel();
    }

    /** Render lịch phân ca, lịch sử ca và form quản lý danh mục ca. */
    public function index(): void
    {
        AuthController::requireAdmin();
        $this->renderPage();
    }

    /** Validate và lưu phân ca mới hoặc đổi ca cho một phân công đã tồn tại. */
    public function assign(): void
    {
        AuthController::requireAdmin();
        $this->requireCsrf();

        $employeeId = filter_var($_POST['MaNV'] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
        $shiftId = filter_var($_POST['MaCa'] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
        $date = trim((string)($_POST['NgayLamViec'] ?? ''));
        $assignmentId = null;
        $errors = [];

        if (isset($_POST['MaPhanCa']) && $_POST['MaPhanCa'] !== '') {
            $assignmentId = filter_var(
                $_POST['MaPhanCa'],
                FILTER_VALIDATE_INT,
                ['options' => ['min_range' => 1]]
            );
            if (!is_int($assignmentId)) {
                $assignmentId = null;
                $errors['MaPhanCa'] = 'Phân ca không hợp lệ.';
            }
        }

        if ($assignmentId !== null) {
            $assignment = $this->shifts->findAssignmentById($assignmentId);
            if ($assignment === null) {
                $errors['MaPhanCa'] = 'Không tìm thấy phân ca cần đổi.';
            } else {
                $employeeId = (int)$assignment['MaNV'];
                $date = (string)$assignment['NgayLamViec'];
            }
        } elseif (!is_int($employeeId) || !$this->shifts->employeeExists($employeeId)) {
            $errors['MaNV'] = 'Vui lòng chọn nhân viên hợp lệ.';
        }

        if (!is_int($shiftId) || !$this->shifts->isActiveShift($shiftId)) {
            $errors['MaCa'] = 'Vui lòng chọn ca đang sử dụng.';
        }
        if (!$this->isValidDate($date)) {
            $errors['NgayLamViec'] = 'Vui lòng chọn ngày hợp lệ.';
        }

        if ($errors !== []) {
            $this->renderPage(
                $this->isValidDate($date) ? $date : null,
                [
                    'MaNV' => is_int($employeeId) ? (string)$employeeId : '',
                    'MaCa' => is_int($shiftId) ? (string)$shiftId : '',
                    'NgayLamViec' => $date,
                ],
                $errors,
                $assignmentId,
                [],
                [],
                null,
                null,
                422
            );
            return;
        }

        try {
            if ($assignmentId !== null) {
                $this->shifts->updateAssignmentShift($assignmentId, $shiftId);
                $_SESSION['shift_success'] = 'Đã đổi ca cho ngày ' . $date . '.';
            } else {
                $this->shifts->saveAssignment($employeeId, $shiftId, $date);
                $_SESSION['shift_success'] = 'Đã lưu phân ca cho ngày ' . $date . '.';
            }
            $this->redirectToShifts($date);
        } catch (Throwable $exception) {
            error_log('Shift assignment failed: ' . $exception->getMessage());
            $this->renderPage(
                $date,
                [
                    'MaNV' => (string)$employeeId,
                    'MaCa' => (string)$shiftId,
                    'NgayLamViec' => $date,
                ],
                [],
                $assignmentId,
                [],
                [],
                null,
                'Không thể lưu phân ca. Vui lòng thử lại.',
                500
            );
        }
    }

    /** Hủy phân ca qua POST/CSRF; không xóa phân công đã có chấm công trong ngày. */
    public function unassign(): void
    {
        AuthController::requireAdmin();
        $this->requireCsrf();

        $assignmentId = filter_var(
            $_POST['MaPhanCa'] ?? null,
            FILTER_VALIDATE_INT,
            ['options' => ['min_range' => 1]]
        );
        if (!is_int($assignmentId)) {
            $_SESSION['shift_error'] = 'Phân ca không hợp lệ.';
            $this->redirectToShifts();
        }

        try {
            $result = $this->shifts->unassignAssignment($assignmentId);
            $date = $result['date'];
            if ($result['status'] === 'deleted') {
                $_SESSION['shift_success'] = 'Đã hủy phân ca.';
            } elseif ($result['status'] === 'attendance_exists') {
                $_SESSION['shift_error'] = 'Không thể hủy phân ca vì đã phát sinh dữ liệu chấm công.';
            } else {
                $_SESSION['shift_error'] = 'Không tìm thấy phân ca cần hủy.';
            }
            $this->redirectToShifts($date);
        } catch (Throwable $exception) {
            error_log('Shift unassignment failed: ' . $exception->getMessage());
            $_SESSION['shift_error'] = 'Không thể hủy phân ca. Vui lòng thử lại.';
            $this->redirectToShifts();
        }
    }

    /** Validate và tạo một ca trong cùng ngày. */
    public function createShift(): void
    {
        AuthController::requireAdmin();
        $this->requireCsrf();

        $values = $this->readShiftForm();
        $errors = $this->validateShiftForm($values);
        if ($errors !== []) {
            $this->renderPage($this->returnDate(), [], [], null, $values, $errors, null, null, 422);
            return;
        }

        try {
            if (!$this->shifts->createShift($values['TenCa'], $values['GioBatDau'], $values['GioKetThuc'])) {
                $this->renderPage(
                    $this->returnDate(), [], [], null, $values, [], null,
                    'Ca làm việc này đã tồn tại.', 422
                );
                return;
            }
            $_SESSION['shift_success'] = 'Đã tạo ca làm việc.';
            $this->redirectToShifts($this->returnDate());
        } catch (Throwable $exception) {
            error_log('Shift creation failed: ' . $exception->getMessage());
            $this->renderPage(
                $this->returnDate(), [], [], null, $values, [], null,
                'Không thể tạo ca làm việc. Vui lòng thử lại.', 500
            );
        }
    }

    /** Cập nhật ca; Model khóa giờ bắt đầu/kết thúc nếu ca có chấm công. */
    public function updateShift(): void
    {
        AuthController::requireAdmin();
        $this->requireCsrf();

        $shiftId = filter_var($_POST['MaCa'] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
        $values = $this->readShiftForm();
        $errors = $this->validateShiftForm($values);
        if (!is_int($shiftId) || $this->shifts->findById((int)$shiftId) === null) {
            $errors['MaCa'] = 'Không tìm thấy ca làm việc.';
        }
        if ($errors !== []) {
            $this->renderPage(
                $this->returnDate(), [], [], null, $values, $errors,
                is_int($shiftId) ? $shiftId : null, null, 422
            );
            return;
        }

        try {
            $result = $this->shifts->updateShift($shiftId, $values['TenCa'], $values['GioBatDau'], $values['GioKetThuc']);
            if ($result === 'duplicate') {
                $this->renderPage(
                    $this->returnDate(), [], [], null, $values, [], $shiftId,
                    'Ca làm việc này đã tồn tại.', 422
                );
                return;
            }
            if ($result === 'time_locked') {
                $this->renderPage(
                    $this->returnDate(), [], [], null, $values, [], $shiftId,
                    'Ca này đã phát sinh dữ liệu chấm công. Không thể thay đổi giờ bắt đầu/kết thúc.', 422
                );
                return;
            }
            if ($result === 'not_found') {
                $this->renderPage(
                    $this->returnDate(), [], [], null, $values, ['MaCa' => 'Không tìm thấy ca làm việc.'], null,
                    null, 404
                );
                return;
            }

            $_SESSION['shift_success'] = 'Đã cập nhật ca làm việc.';
            $this->redirectToShifts($this->returnDate());
        } catch (Throwable $exception) {
            error_log('Shift update failed: ' . $exception->getMessage());
            $this->renderPage(
                $this->returnDate(), [], [], null, $values, [], $shiftId,
                'Không thể cập nhật ca làm việc. Vui lòng thử lại.', 500
            );
        }
    }

    /** Xóa ca chưa từng được dùng; ca đã tham chiếu được giữ nguyên. */
    public function deleteShift(): void
    {
        AuthController::requireAdmin();
        $this->requireCsrf();

        $shiftId = $this->postedShiftId();
        if ($shiftId === null) {
            $_SESSION['shift_error'] = 'Ca làm việc không hợp lệ.';
            $this->redirectToShifts();
        }

        try {
            $result = $this->shifts->deleteShift($shiftId);
            if ($result === 'deleted') {
                $_SESSION['shift_success'] = 'Đã xóa ca làm việc.';
            } elseif ($result === 'used') {
                $_SESSION['shift_error'] = 'Không thể xóa ca vì đã phát sinh dữ liệu. Bạn có thể ngừng sử dụng ca này.';
            } else {
                $_SESSION['shift_error'] = 'Không tìm thấy ca làm việc.';
            }
        } catch (Throwable $exception) {
            error_log('Shift deletion failed: ' . $exception->getMessage());
            $_SESSION['shift_error'] = 'Không thể xóa ca làm việc. Vui lòng thử lại.';
        }
        $this->redirectToShifts();
    }

    /** Đánh dấu ca đã dùng là ngừng sử dụng, không xóa lịch sử. */
    public function disableShift(): void
    {
        AuthController::requireAdmin();
        $this->setShiftStatus(0, 'Đã ngừng sử dụng ca làm việc.', 'Không thể ngừng sử dụng ca làm việc.');
    }

    /** Kích hoạt lại một ca cũ để dùng cho phân ca mới. */
    public function enableShift(): void
    {
        AuthController::requireAdmin();
        $this->setShiftStatus(1, 'Đã kích hoạt lại ca làm việc.', 'Không thể kích hoạt lại ca làm việc.');
    }

    private function setShiftStatus(int $status, string $success, string $failure): void
    {
        $this->requireCsrf();
        $shiftId = $this->postedShiftId();
        if ($shiftId === null) {
            $_SESSION['shift_error'] = 'Ca làm việc không hợp lệ.';
            $this->redirectToShifts();
        }

        try {
            $updated = $status === 1
                ? $this->shifts->enableShift($shiftId)
                : $this->shifts->disableShift($shiftId);
            $_SESSION[$updated ? 'shift_success' : 'shift_error'] = $updated ? $success : $failure;
        } catch (Throwable $exception) {
            error_log('Shift status update failed: ' . $exception->getMessage());
            $_SESSION['shift_error'] = $failure;
        }
        $this->redirectToShifts();
    }

    private function renderPage(
        ?string $date = null,
        array $formValues = [],
        array $errors = [],
        ?int $editingAssignmentId = null,
        array $shiftFormValues = [],
        array $shiftErrors = [],
        ?int $editingShiftId = null,
        ?string $inlineError = null,
        ?int $responseStatus = null
    ): void {
        $today = (new DateTimeImmutable('now', new DateTimeZone('Asia/Ho_Chi_Minh')))->format('Y-m-d');
        $selectedDate = $date ?? trim((string)($_GET['date'] ?? $today));
        $dateError = null;
        if (!$this->isValidDate($selectedDate)) {
            $selectedDate = $today;
            $dateError = 'Ngày không hợp lệ.';
        }

        $formValues += ['MaNV' => '', 'MaCa' => '', 'NgayLamViec' => $selectedDate];
        $shiftFormValues += ['TenCa' => '', 'GioBatDau' => '', 'GioKetThuc' => ''];
        $error = $inlineError;
        if ($error === null) {
            $error = $_SESSION['shift_error'] ?? $dateError;
        }
        unset($_SESSION['shift_error']);
        $successMessage = $_SESSION['shift_success'] ?? null;
        unset($_SESSION['shift_success']);
        $shiftTimeLocked = false;

        if ($editingAssignmentId === null && isset($_GET['edit_assignment'])) {
            $requestedId = filter_var($_GET['edit_assignment'], FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
            if (is_int($requestedId)) {
                $editingAssignmentId = $requestedId;
            } else {
                $error = 'Phân ca không hợp lệ.';
            }
        }
        if ($editingShiftId === null && isset($_GET['edit_shift'])) {
            $requestedId = filter_var($_GET['edit_shift'], FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
            if (is_int($requestedId)) {
                $editingShiftId = $requestedId;
            } else {
                $error = 'Ca làm việc không hợp lệ.';
            }
        }

        try {
            $employees = $this->shifts->findEmployees();
            $availableShifts = $this->shifts->findActive();
            $allShifts = $this->shifts->findAll();

            if ($editingAssignmentId !== null) {
                $assignment = $this->shifts->findAssignmentById($editingAssignmentId);
                if ($assignment === null) {
                    $error = 'Không tìm thấy phân ca cần đổi.';
                    $editingAssignmentId = null;
                } else {
                    $selectedDate = (string)$assignment['NgayLamViec'];
                    $formValues = array_merge($formValues, [
                        'MaNV' => (string)$assignment['MaNV'],
                        'MaCa' => (string)$assignment['MaCa'],
                        'NgayLamViec' => $selectedDate,
                    ]);
                }
            }

            if ($editingShiftId !== null) {
                $shift = $this->shifts->findById($editingShiftId);
                if ($shift === null) {
                    $error = 'Không tìm thấy ca làm việc cần sửa.';
                    $editingShiftId = null;
                } else {
                    if (!array_key_exists('_NormalizedStart', $shiftFormValues)) {
                        $shiftFormValues = [
                            'TenCa' => (string)$shift['TenCa'],
                            'GioBatDau' => substr((string)$shift['GioBatDau'], 0, 5),
                            'GioKetThuc' => substr((string)$shift['GioKetThuc'], 0, 5),
                        ];
                    }
                    $shiftTimeLocked = $this->shifts->hasAttendance($editingShiftId);
                }
            }

            $assignments = $this->shifts->findAssignmentsByDate($selectedDate);
        } catch (Throwable $exception) {
            error_log('Shift page read failed: ' . $exception->getMessage());
            http_response_code(500);
            $employees = $availableShifts = $allShifts = $assignments = [];
            $error = 'Không thể tải dữ liệu ca làm việc. Vui lòng kiểm tra kết nối cơ sở dữ liệu.';
        }

        if ($responseStatus !== null) {
            http_response_code($responseStatus);
        }
        $csrfToken = CsrfToken::token();
        $activeTab = trim((string)($_GET['tab'] ?? $_POST['return_tab'] ?? 'assignments'));
        if (!in_array($activeTab, ['assignments', 'shifts'], true)) {
            $activeTab = 'assignments';
        }
        if ($editingShiftId !== null || isset($_GET['edit_shift'])) {
            $activeTab = 'shifts';
        } elseif ($editingAssignmentId !== null || isset($_GET['edit_assignment'])) {
            $activeTab = 'assignments';
        }
        $pageTitle = 'Phân ca';
        require __DIR__ . '/../View/shifts.php';
    }

    private function readShiftForm(): array
    {
        $name = trim((string)($_POST['TenCa'] ?? ''));
        $start = $this->normalizeTime(trim((string)($_POST['GioBatDau'] ?? '')));
        $end = $this->normalizeTime(trim((string)($_POST['GioKetThuc'] ?? '')));

        return [
            'TenCa' => $name,
            'GioBatDau' => $start ?? trim((string)($_POST['GioBatDau'] ?? '')),
            'GioKetThuc' => $end ?? trim((string)($_POST['GioKetThuc'] ?? '')),
            '_NormalizedStart' => $start,
            '_NormalizedEnd' => $end,
        ];
    }

    private function validateShiftForm(array &$values): array
    {
        $errors = [];
        $nameLength = preg_match_all('/./us', $values['TenCa'], $matches);
        if ($values['TenCa'] === '') {
            $errors['TenCa'] = 'Vui lòng nhập tên ca.';
        } elseif ($nameLength === false || $nameLength > 100) {
            $errors['TenCa'] = 'Tên ca không được vượt quá 100 ký tự.';
        }

        $start = $values['_NormalizedStart'];
        $end = $values['_NormalizedEnd'];
        if ($start === null) {
            $errors['GioBatDau'] = 'Giờ bắt đầu không hợp lệ.';
        }
        if ($end === null) {
            $errors['GioKetThuc'] = 'Giờ kết thúc không hợp lệ.';
        }
        if ($start !== null && $end !== null && $start >= $end) {
            $errors['GioKetThuc'] = $start > $end
                ? 'Hệ thống hiện chưa hỗ trợ ca làm việc qua đêm.'
                : 'Giờ kết thúc phải sau giờ bắt đầu.';
        }

        if ($start !== null) {
            $values['GioBatDau'] = $start;
        }
        if ($end !== null) {
            $values['GioKetThuc'] = $end;
        }

        return $errors;
    }

    private function normalizeTime(string $value): ?string
    {
        if (!preg_match('/\A([01]\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?\z/', $value, $parts)) {
            return null;
        }

        return sprintf('%s:%s:%s', $parts[1], $parts[2], $parts[3] ?? '00');
    }

    private function postedShiftId(): ?int
    {
        $shiftId = filter_var($_POST['MaCa'] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);

        return is_int($shiftId) ? $shiftId : null;
    }

    private function returnDate(): ?string
    {
        $date = trim((string)($_POST['return_date'] ?? ''));

        return $this->isValidDate($date) ? $date : null;
    }

    private function redirectToShifts(?string $date = null): never
    {
        $tab = trim((string)($_POST['return_tab'] ?? 'assignments'));
        if (!in_array($tab, ['assignments', 'shifts'], true)) {
            $tab = 'assignments';
        }
        $date ??= $this->returnDate();
        $url = '/?action=shifts&tab=' . rawurlencode($tab)
            . ($date === null ? '' : '&date=' . rawurlencode($date));
        header('Location: ' . $url, true, 303);
        exit;
    }

    private function requireCsrf(): void
    {
        if (!CsrfToken::isValid()) {
            http_response_code(400);
            exit('Yêu cầu không hợp lệ. Vui lòng tải lại trang và thử lại.');
        }
    }

    private function isValidDate(string $value): bool
    {
        $date = DateTimeImmutable::createFromFormat('!Y-m-d', $value);
        $errors = DateTimeImmutable::getLastErrors();

        return $date !== false
            && $date->format('Y-m-d') === $value
            && ($errors === false || ($errors['warning_count'] === 0 && $errors['error_count'] === 0));
    }
}

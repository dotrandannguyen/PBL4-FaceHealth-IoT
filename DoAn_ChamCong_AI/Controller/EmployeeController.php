<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/EmployeeModel.php';
require_once __DIR__ . '/../Model/FaceEmbeddingModel.php';
require_once __DIR__ . '/../Model/AccountModel.php';
require_once __DIR__ . '/../Controller/AuthController.php';
require_once __DIR__ . '/../Security/CsrfToken.php';

final class EmployeeController
{
    private EmployeeModel $employees;
    private FaceEmbeddingModel $faceEmbeddings;
    private AccountModel $accounts;

    public function __construct()
    {
        $this->employees = new EmployeeModel();
        $this->faceEmbeddings = new FaceEmbeddingModel();
        $this->accounts = new AccountModel();
    }

    /** Đọc danh sách nhân viên và tổng hợp trạng thái tài khoản/khuôn mặt cho trang quản trị. */
    public function index(): void
    {
        AuthController::requireAdmin();

        $employees = [];
        $error = null;
        $successMessage = $_SESSION['employee_success'] ?? null;
        unset($_SESSION['employee_success']);

        try {
            $employees = $this->employees->findAll();
        } catch (Throwable $exception) {
            error_log('Employee page read failed: ' . $exception->getMessage());
            http_response_code(500);
            $error = 'Không thể tải danh sách nhân viên. Vui lòng kiểm tra kết nối cơ sở dữ liệu.';
        }

        require __DIR__ . '/../View/employees.php';
    }

    public function createForm(array $values = [], array $errors = []): void
    {
        AuthController::requireAdmin();

        try {
            $this->renderForm('create', null, $this->employees->findRoles(), $values, $errors);
        } catch (Throwable $exception) {
            $this->handleFailure('Employee create form failed', $exception);
        }
    }

    /**
     * Tạo nhân viên cùng tài khoản đăng nhập sau khi kiểm tra quyền, CSRF và dữ liệu.
     * EmployeeModel thực hiện hai thao tác ghi trong cùng transaction.
     */
    public function store(): void
    {
        AuthController::requireAdmin();

        if (!CsrfToken::isValid()) {
            http_response_code(400);
            exit('Yêu cầu không hợp lệ. Vui lòng tải lại trang và thử lại.');
        }

        $values = $this->submittedValues(false);

        try {
            $errors = $this->validateValues($values, null, false);
            if ($errors !== []) {
                http_response_code(422);
                $this->renderForm('create', null, $this->employees->findRoles(), $values, $errors);
                return;
            }

            $passwordHash = password_hash($values['Password'], PASSWORD_DEFAULT);
            if (!is_string($passwordHash)) {
                throw new RuntimeException('Password hashing failed.');
            }
            $employeeId = $this->employees->createWithAccount(
                $values['HoTen'],
                $values['MaVaiTro'],
                $values['TenDangNhap'],
                $passwordHash
            );
            $_SESSION['employee_success'] = 'Đã thêm nhân viên NV' . str_pad((string)$employeeId, 3, '0', STR_PAD_LEFT) . '.';
            $this->redirectToList();
        } catch (Throwable $exception) {
            if ($this->isUsernameConflict($exception)) {
                http_response_code(422);
                $errors = ['TenDangNhap' => 'Tên đăng nhập đã được sử dụng.'];
                $this->renderForm('create', null, $this->employees->findRoles(), $values, $errors);
                return;
            }
            $this->handleFailure('Employee create failed', $exception);
        }
    }

    public function editForm(int $employeeId): void
    {
        AuthController::requireAdmin();

        try {
            $employee = $this->employees->findById($employeeId);
            if ($employee === null) {
                $this->notFound();
                return;
            }

            $this->renderForm('edit', $employee, $this->employees->findRoles());
        } catch (Throwable $exception) {
            $this->handleFailure('Employee edit form failed', $exception);
        }
    }

    /**
     * Cập nhật thông tin nhân viên và tài khoản; mật khẩu chỉ đổi khi có mật khẩu mới.
     * Model bảo đảm thay đổi nhân viên/tài khoản được commit hoặc rollback cùng nhau.
     */
    public function update(int $employeeId): void
    {
        AuthController::requireAdmin();

        if (!CsrfToken::isValid()) {
            http_response_code(400);
            exit('Yêu cầu không hợp lệ. Vui lòng tải lại trang và thử lại.');
        }

        $values = $this->submittedValues(true);

        try {
            $employee = $this->employees->findById($employeeId);
            if ($employee === null) {
                $this->notFound();
                return;
            }

            $hasAccount = (int)$employee['HasAccount'] === 1;
            $errors = $this->validateValues($values, $employeeId, $hasAccount);
            if ($errors !== []) {
                http_response_code(422);
                $this->renderForm('edit', $employee, $this->employees->findRoles(), $values, $errors);
                return;
            }

            $passwordHash = $values['Password'] === ''
                ? null
                : password_hash($values['Password'], PASSWORD_DEFAULT);
            if ($values['Password'] !== '' && !is_string($passwordHash)) {
                throw new RuntimeException('Password hashing failed.');
            }
            $this->employees->updateWithAccount(
                $employeeId,
                $values['HoTen'],
                $values['MaVaiTro'],
                $values['TenDangNhap'],
                $passwordHash
            );
            $_SESSION['employee_success'] = 'Đã cập nhật nhân viên NV' . str_pad((string)$employeeId, 3, '0', STR_PAD_LEFT) . '.';
            $this->redirectToList();
        } catch (Throwable $exception) {
            if ($this->isUsernameConflict($exception)) {
                http_response_code(422);
                $employee = $this->employees->findById($employeeId);
                $errors = ['TenDangNhap' => 'Tên đăng nhập đã được sử dụng.'];
                $this->renderForm('edit', $employee, $this->employees->findRoles(), $values, $errors);
                return;
            }
            $this->handleFailure('Employee update failed', $exception);
        }
    }

    public function requestedEmployeeId(): int
    {
        AuthController::requireAdmin();

        $employeeId = filter_var(
            $_GET['id'] ?? null,
            FILTER_VALIDATE_INT,
            ['options' => ['min_range' => 1]]
        );

        if ($employeeId === false) {
            $this->notFound();
        }

        return (int)$employeeId;
    }

    private function submittedValues(bool $isEdit): array
    {
        return [
            'HoTen' => trim($this->postString('HoTen')),
            'TenDangNhap' => trim($this->postString('TenDangNhap')),
            'Password' => $this->postString($isEdit ? 'NewPassword' : 'MatKhau'),
            'ConfirmPassword' => $this->postString('ConfirmPassword'),
            'MaVaiTro' => filter_var(
                $this->postString('MaVaiTro'),
                FILTER_VALIDATE_INT,
                ['options' => ['min_range' => 1]]
            ),
        ];
    }

    private function postString(string $key): string
    {
        return is_string($_POST[$key] ?? null) ? $_POST[$key] : '';
    }

    private function validateValues(array $values, ?int $employeeId, bool $hasAccount): array
    {
        $errors = [];
        $name = $values['HoTen'];
        $nameLength = preg_match_all('/./us', $name, $matches);

        if ($name === '') {
            $errors['HoTen'] = 'Vui lòng nhập họ tên.';
        } elseif ($nameLength === false) {
            $errors['HoTen'] = 'Họ tên chứa ký tự không hợp lệ.';
        } elseif ($nameLength > 100) {
            $errors['HoTen'] = 'Họ tên không được vượt quá 100 ký tự.';
        }

        $roleId = $values['MaVaiTro'];
        if (!is_int($roleId) || !$this->employees->roleExists($roleId)) {
            $errors['MaVaiTro'] = 'Vui lòng chọn vai trò hợp lệ.';
        }

        $username = $values['TenDangNhap'];
        $usernameLength = preg_match_all('/./us', $username, $matches);
        $password = $values['Password'];
        $confirmation = $values['ConfirmPassword'];
        $accountTouched = $username !== '' || $password !== '' || $confirmation !== '';
        $accountRequired = $employeeId === null || $hasAccount || $accountTouched;

        if ($accountRequired && $username === '') {
            $errors['TenDangNhap'] = 'Vui lòng nhập tên đăng nhập.';
        } elseif ($username !== '' && ($usernameLength === false || $usernameLength > 50)) {
            $errors['TenDangNhap'] = 'Tên đăng nhập không được vượt quá 50 ký tự.';
        } elseif ($username !== '' && !preg_match('/^[A-Za-z0-9._]+$/', $username)) {
            $errors['TenDangNhap'] = 'Chỉ dùng chữ cái không dấu, số, dấu chấm và gạch dưới.';
        } elseif ($username !== '' && $this->accounts->usernameExists($username, $employeeId)) {
            $errors['TenDangNhap'] = 'Tên đăng nhập đã được sử dụng.';
        }

        if ($accountRequired && !$hasAccount && $password === '') {
            $errors['Password'] = 'Vui lòng tạo mật khẩu cho tài khoản.';
        } elseif ($password !== '' && $this->characterLength($password) < 6) {
            $errors['Password'] = 'Mật khẩu phải có ít nhất 6 ký tự.';
        }
        if ($password !== $confirmation) {
            $errors['ConfirmPassword'] = 'Xác nhận mật khẩu không khớp.';
        }

        return $errors;
    }

    private function isUsernameConflict(Throwable $exception): bool
    {
        return $exception instanceof PDOException
            && (int)($exception->errorInfo[1] ?? 0) === 1062;
    }

    private function characterLength(string $value): int
    {
        $length = preg_match_all('/./us', $value, $matches);

        return $length === false ? 0 : $length;
    }

    private function renderForm(
        string $mode,
        ?array $employee,
        array $roles,
        array $values = [],
        array $errors = []
    ): void {
        $csrfToken = CsrfToken::token();
        $faceSamples = $mode === 'edit' && $employee !== null
            ? $this->faceEmbeddings->findByEmployee((int)$employee['MaNV'])
            : [];
        require __DIR__ . '/../View/employee_form.php';
    }

    private function redirectToList(): void
    {
        header('Location: /', true, 303);
        exit;
    }

    private function notFound(): void
    {
        http_response_code(404);
        echo 'Không tìm thấy nhân viên.';
        exit;
    }

    private function handleFailure(string $context, Throwable $exception): void
    {
        error_log($context . ': ' . $exception->getMessage());
        http_response_code(500);
        echo 'Không thể xử lý yêu cầu lúc này. Vui lòng kiểm tra kết nối cơ sở dữ liệu.';
    }
}

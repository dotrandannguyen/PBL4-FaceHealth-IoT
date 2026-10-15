<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/AccountModel.php';
require_once __DIR__ . '/../Security/CsrfToken.php';

final class AuthController
{
    private const ADMIN_ROLE_ID = 1;

    private AccountModel $accounts;

    public function __construct()
    {
        $this->accounts = new AccountModel();
    }

    public function showLogin(): void
    {
        $this->renderLogin();
    }

    /**
     * Xác thực thông tin đăng nhập, tạo session mới và điều hướng theo vai trò.
     * CSRF được kiểm tra trước khi truy vấn tài khoản; mật khẩu không lưu trong session.
     */
    public function login(): void
    {
        if (!CsrfToken::isValid()) {
            http_response_code(400);
            $this->renderLogin('Phiên gửi biểu mẫu không hợp lệ. Vui lòng tải lại trang.');
            return;
        }

        $username = trim((string)($_POST['username'] ?? ''));
        $password = is_string($_POST['password'] ?? null) ? $_POST['password'] : '';

        if ($username === '' || strlen($username) > 50 || $password === '') {
            http_response_code(401);
            $this->renderLogin('Tên đăng nhập hoặc mật khẩu không đúng.', $username);
            return;
        }

        try {
            $user = $this->accounts->authenticate($username, $password);
        } catch (Throwable $exception) {
            error_log('Authentication lookup failed: ' . $exception->getMessage());
            http_response_code(500);
            $this->renderLogin('Không thể đăng nhập lúc này. Vui lòng thử lại sau.', $username);
            return;
        }

        if ($user === null) {
            http_response_code(401);
            $this->renderLogin('Tên đăng nhập hoặc mật khẩu không đúng.', $username);
            return;
        }

        if (!session_regenerate_id(true)) {
            http_response_code(500);
            $this->renderLogin('Không thể tạo phiên đăng nhập. Vui lòng thử lại.', $username);
            return;
        }

        $_SESSION['user_id'] = $user['user_id'];
        $_SESSION['ma_nv'] = $user['ma_nv'];
        $_SESSION['username'] = $user['username'];
        $_SESSION['ma_vai_tro'] = $user['ma_vai_tro'];
        $_SESSION['role'] = $user['role'];
        $_SESSION['display_name'] = $user['display_name'];
        CsrfToken::rotate();

        $destination = (int)$user['ma_vai_tro'] === 2
            ? '/?action=my'
            : '/?action=dashboard';
        header('Location: ' . $destination, true, 302);
        exit;
    }

    /** Hủy session/cookie sau khi xác minh CSRF và đưa người dùng về trang đăng nhập. */
    public function logout(): void
    {
        if (!CsrfToken::isValid()) {
            http_response_code(400);
            exit('Yêu cầu không hợp lệ.');
        }

        $_SESSION = [];
        $cookie = session_get_cookie_params();
        session_destroy();

        if (ini_get('session.use_cookies')) {
            setcookie(session_name(), '', [
                'expires' => time() - 42000,
                'path' => $cookie['path'] ?: '/',
                'domain' => $cookie['domain'],
                'secure' => $cookie['secure'],
                'httponly' => $cookie['httponly'],
                'samesite' => $cookie['samesite'] ?? 'Lax',
            ]);
        }

        header('Location: /?action=login', true, 303);
        exit;
    }

    /** Chặn request chưa đăng nhập hoặc không có MaVaiTro admin bằng kiểm tra phía server. */
    public static function requireAdmin(): void
    {
        if (!isset($_SESSION['user_id'])) {
            header('Location: /?action=login', true, 302);
            exit;
        }

        if ((int)($_SESSION['ma_vai_tro'] ?? 0) !== self::ADMIN_ROLE_ID) {
            http_response_code(403);
            $authUser = [
                'display_name' => (string)($_SESSION['display_name'] ?? ''),
                'role' => (string)($_SESSION['role'] ?? ''),
            ];
            $pageTitle = 'Không đủ quyền';
            require __DIR__ . '/../View/forbidden.php';
            exit;
        }
    }

    /** Yêu cầu session đã xác thực; nếu chưa có thì chuyển về form đăng nhập. */
    public static function requireAuthenticated(): void
    {
        if (!isset($_SESSION['user_id'])) {
            header('Location: /?action=login', true, 302);
            exit;
        }
    }

    private function renderLogin(?string $loginError = null, string $loginUsername = ''): void
    {
        $csrfToken = CsrfToken::token();
        $authUser = isset($_SESSION['user_id']) ? [
            'display_name' => (string)($_SESSION['display_name'] ?? ''),
            'role' => (string)($_SESSION['role'] ?? ''),
        ] : null;
        $pageTitle = 'Đăng nhập';
        require __DIR__ . '/../View/login.php';
    }
}

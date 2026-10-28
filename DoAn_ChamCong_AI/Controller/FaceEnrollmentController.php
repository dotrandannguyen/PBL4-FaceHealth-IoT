<?php
declare(strict_types=1);

require_once __DIR__ . '/AuthController.php';
require_once __DIR__ . '/../Model/Database.php';
require_once __DIR__ . '/../Model/EmployeeModel.php';
require_once __DIR__ . '/../Model/FaceEmbeddingModel.php';
require_once __DIR__ . '/../Security/CsrfToken.php';
require_once __DIR__ . '/../Service/AiClient.php';
require_once __DIR__ . '/../Service/FaceSample.php';
require_once __DIR__ . '/../Service/CameraFrameClient.php';

final class FaceEnrollmentController
{
    private const POSES = ['frontal', 'left', 'right', 'up', 'down'];
    private const SESSION_KEY = 'face_enrollment_batches';
    private const SESSION_TTL = 600;
    private const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

    private EmployeeModel $employees;
    private FaceEmbeddingModel $faceEmbeddings;
    private AiClient $ai;
    private CameraFrameClient $camera;

    public function __construct()
    {
        $this->employees = new EmployeeModel();
        $this->faceEmbeddings = new FaceEmbeddingModel();
        $this->ai = new AiClient();
        $this->camera = new CameraFrameClient();
    }

    /** Hiển thị trang chuyên mục Đăng ký nhận diện khuôn mặt độc lập trên Web. */
    public function registrationView(): void
    {
        AuthController::requireAdmin();
        $pageTitle = 'Đăng ký nhận diện khuôn mặt';
        $csrfToken = CsrfToken::token();
        $employees = $this->employees->findAll();

        $selectedEmployeeId = filter_var($_GET['id'] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
        if ($selectedEmployeeId === false) {
            $selectedEmployeeId = null;
        }

        if ($selectedEmployeeId === null && !empty($employees)) {
            $selectedEmployeeId = (int)$employees[0]['MaNV'];
        }

        $selectedEmployee = null;
        $faceSamples = [];
        if ($selectedEmployeeId !== null) {
            $selectedEmployee = $this->employees->findById($selectedEmployeeId);
            if ($selectedEmployee !== null) {
                $faceSamples = $this->faceEmbeddings->findByEmployee($selectedEmployeeId);
            }
        }

        $aiHealth = null;
        try {
            $aiHealth = $this->ai->health();
        } catch (Throwable $e) {
            $aiHealth = ['success' => false, 'model_ready' => false];
        }

        require __DIR__ . '/../View/face_registration.php';
    }

    /** Chuyển tiếp frame JPEG từ camera singleton hiện có cho giao diện enrollment. */
    public function frame(): void
    {
        AuthController::requireAdmin();
        session_write_close();
        $jpeg = $this->camera->captureJpeg();
        if (!is_string($jpeg) || strlen($jpeg) > self::MAX_IMAGE_BYTES) {
            http_response_code(503);
            header('Cache-Control: private, no-store');
            exit;
        }

        header('Content-Type: image/jpeg');
        header('Content-Length: ' . strlen($jpeg));
        header('Cache-Control: private, no-store');
        header('X-Content-Type-Options: nosniff');
        echo $jpeg;
    }

    /** Tạo batch enrollment 5 pose trong session; chưa ghi dữ liệu xuống MariaDB. */
    public function start(): void
    {
        $employeeId = $this->requestEmployeeId();
        if (!$this->requirePostCsrf()) {
            return;
        }

        try {
            if ($this->employees->findById($employeeId) === null) {
                $this->jsonResponse(['success' => false, 'message' => 'Không tìm thấy nhân viên.'], 404);
                return;
            }
            $health = $this->ai->health();
            if (empty($health['model_ready'])) {
                $this->jsonResponse(['success' => false, 'message' => 'AI enrollment chưa sẵn sàng.'], 503);
                return;
            }

            $existingCount = $this->faceEmbeddings->countByEmployee($employeeId);
            $_SESSION[self::SESSION_KEY][$employeeId] = [
                'started_at' => time(),
                'replace_existing' => $existingCount > 0,
                'samples' => [],
            ];
            $this->jsonResponse([
                'success' => true,
                'captured' => 0,
                'total' => count(self::POSES),
                'replace_existing' => $existingCount > 0,
            ]);
        } catch (Throwable $exception) {
            $this->jsonResponse(['success' => false, 'message' => 'Không thể bắt đầu đăng ký khuôn mặt.'], 503);
        }
    }

    /** Gửi frame hiện tại tới AI service để kiểm tra số mặt và pose mong đợi. */
    public function inspectPose(): void
    {
        $employeeId = $this->requestEmployeeId();
        if (!$this->requirePostCsrf()) {
            return;
        }
        $state = $this->activeBatch($employeeId);
        if ($state === null) {
            return;
        }

        $pose = isset($state['saved_result']) ? null : (self::POSES[count($state['samples'])] ?? null);
        if ($pose === null) {
            $this->jsonResponse(['success' => false, 'message' => 'Đã đủ 5 mẫu.'], 409);
            return;
        }

        session_write_close();
        $jpeg = $this->cameraFrame();
        if ($jpeg === null) {
            $this->jsonResponse(['success' => false, 'message' => 'Camera chưa sẵn sàng.'], 503);
            return;
        }

        try {
            $result = $this->ai->inspectEnrollmentImage($jpeg, $pose);
            $result['captured'] = count($state['samples']);
            $this->jsonResponse($result, !empty($result['success']) ? 200 : 503);
        } catch (Throwable $exception) {
            $this->jsonResponse(['success' => false, 'message' => 'Không thể kiểm tra hướng khuôn mặt.'], 503);
        }
    }

    /** Thu một mẫu đã được AI xác nhận, giữ ảnh và vector theo cặp trong batch session. */
    public function capture(): void
    {
        $employeeId = $this->requestEmployeeId();
        if (!$this->requirePostCsrf()) {
            return;
        }
        $state = $this->activeBatch($employeeId);
        if ($state === null) {
            return;
        }

        $pose = isset($state['saved_result']) ? null : (self::POSES[count($state['samples'])] ?? null);
        if ($pose === null) {
            $this->jsonResponse(['success' => false, 'message' => 'Đã đủ 5 mẫu.'], 409);
            return;
        }
        $jpeg = $this->cameraFrame();
        if ($jpeg === null) {
            $this->jsonResponse(['success' => false, 'message' => 'Camera chưa sẵn sàng.'], 503);
            return;
        }

        try {
            $result = $this->ai->captureEnrollmentSample($jpeg, $pose);
            if (empty($result['success']) || empty($result['pose_ok'])) {
                $this->jsonResponse($result, 409);
                return;
            }

            if (($result['pose'] ?? null) !== $pose || !is_string($result['vector'] ?? null)
                || !is_string($result['image_jpeg'] ?? null) || !is_string($result['image_sha256'] ?? null)) {
                $this->jsonResponse(['success' => false, 'message' => 'Mẫu AI trả về không hợp lệ.'], 502);
            }
            $vector = base64_decode($result['vector'], true);
            $image = base64_decode($result['image_jpeg'], true);
            if (!is_string($vector) || strlen($vector) !== 2048 || !is_string($image)
                || $image === '' || strlen($image) > self::MAX_IMAGE_BYTES
                || !hash_equals((string)($result['image_sha256'] ?? ''), hash('sha256', $image))
                || !$this->isValidImage($image)) {
                $this->jsonResponse(['success' => false, 'message' => 'Mẫu AI trả về không hợp lệ.'], 502);
                return;
            }

            FaceSample::vector($vector);
            if (!empty($state['samples'])) {
                FaceSample::requireSameIdentity($state['samples'][0]['vector'], $vector);
            }
            $state['samples'][] = ['vector' => $vector, 'image' => $image, 'pose' => $pose];
            $_SESSION[self::SESSION_KEY][$employeeId] = $state;
            $this->jsonResponse([
                'success' => true,
                'captured' => count($state['samples']),
                'total' => count(self::POSES),
                'pose' => $pose,
                'complete' => count($state['samples']) === count(self::POSES),
            ]);
        } catch (InvalidArgumentException $exception) {
            $this->jsonResponse(['success' => false, 'message' => $exception->getMessage()], 409);
        } catch (Throwable $exception) {
            $this->jsonResponse(['success' => false, 'message' => 'Không thể ghi nhận mẫu khuôn mặt.'], 503);
        }
    }

    /** Xác thực batch đủ 5 pose rồi thay toàn bộ embedding cũ trong một transaction. */
    public function complete(): void
    {
        $employeeId = $this->requestEmployeeId();
        if (!$this->requirePostCsrf()) {
            return;
        }
        $state = $this->activeBatch($employeeId);
        if ($state === null) {
            return;
        }
        if (isset($state['saved_result'])) {
            $this->jsonResponse($state['saved_result']);
        }
        if (count($state['samples']) !== count(self::POSES)) {
            $this->jsonResponse(['success' => false, 'message' => 'Cần xác nhận đủ 5 góc trước khi lưu.'], 409);
            return;
        }

        try {
            $ids = $this->faceEmbeddings->replaceByEmployee($employeeId, $state['samples']);
            $galleryUpdated = false;
            try {
                $galleryUpdated = !empty($this->ai->refreshGallery()['success']);
            } catch (Throwable $exception) {
                $galleryUpdated = false;
            }
            $result = [
                'success' => true,
                'saved' => count($ids),
                'gallery_updated' => $galleryUpdated,
                'message' => 'Đã lưu đủ 5 mẫu khuôn mặt.',
            ];
            // A lost response must not turn a successful save into an expired batch.
            $_SESSION[self::SESSION_KEY][$employeeId] = ['started_at' => time(), 'samples' => [], 'saved_result' => $result];
            $this->jsonResponse($result);
        } catch (Throwable $exception) {
            error_log('Face enrollment batch save failed: ' . $exception->getMessage());
            $this->jsonResponse(['success' => false, 'message' => 'Không thể lưu batch. Dữ liệu khuôn mặt cũ vẫn được giữ nguyên.'], 500);
        }
    }

    /** Retry gallery synchronization without collecting or saving another batch. */
    public function refreshGallery(): void
    {
        $this->requestEmployeeId();
        if (!$this->requirePostCsrf()) {
            return;
        }
        session_write_close();
        try {
            $updated = ($this->ai->refreshGallery()['success'] ?? false) === true;
        } catch (Throwable $exception) {
            $updated = false;
        }
        $this->jsonResponse(['success' => $updated, 'gallery_updated' => $updated,
            'message' => $updated ? 'Đã cập nhật dữ liệu nhận diện.' : 'Chưa cập nhật được AI. Dữ liệu DB đã lưu; hãy thử lại.'], $updated ? 200 : 503);
    }

    /** Hủy batch chưa hoàn tất mà không tác động tới các embedding đang lưu. */
    public function cancel(): void
    {
        $employeeId = $this->requestEmployeeId();
        if (!$this->requirePostCsrf()) {
            return;
        }
        unset($_SESSION[self::SESSION_KEY][$employeeId]);
        $this->jsonResponse(['success' => true]);
    }

    /** Xóa toàn bộ embedding của nhân viên sau khi xác minh Admin và CSRF. */
    public function deleteRegistration(): void
    {
        $employeeId = $this->requestEmployeeId();
        if (!$this->requirePostCsrf()) {
            return;
        }
        try {
            if ($this->employees->findById($employeeId) === null) {
                $this->jsonResponse(['success' => false, 'message' => 'Không tìm thấy nhân viên.'], 404);
                return;
            }
            $deleted = $this->faceEmbeddings->deleteByEmployee($employeeId);
            unset($_SESSION[self::SESSION_KEY][$employeeId]);
            $galleryUpdated = false;
            try {
                $galleryUpdated = !empty($this->ai->refreshGallery()['success']);
            } catch (Throwable $exception) {
                $galleryUpdated = false;
            }
            $this->jsonResponse([
                'success' => true,
                'deleted' => $deleted,
                'gallery_updated' => $galleryUpdated,
                'message' => 'Đã xóa toàn bộ mẫu khuôn mặt của nhân viên.',
            ]);
        } catch (Throwable $exception) {
            error_log('Face registration delete failed: ' . $exception->getMessage());
            $this->jsonResponse(['success' => false, 'message' => 'Không thể xóa đăng ký khuôn mặt.'], 500);
        }
    }

    /** Trả ảnh mẫu khuôn mặt qua route bảo vệ, không nhúng binary/base64 vào HTML. */
    public function image(): void
    {
        AuthController::requireAdmin();
        $embeddingId = filter_var($_GET['id'] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
        if ($embeddingId === false) {
            http_response_code(404);
            exit;
        }

        try {
            $row = $this->faceEmbeddings->findImageById((int)$embeddingId);
            $image = is_array($row) ? $row['AnhKhuonMat'] : null;
            if (is_resource($image)) {
                $image = stream_get_contents($image);
            }
            if (!is_string($image) || $image === '' || !$this->isValidImage($image)) {
                http_response_code(404);
                exit;
            }
            $mime = (new finfo(FILEINFO_MIME_TYPE))->buffer($image);
            header('Content-Type: ' . $mime);
            header('Content-Length: ' . strlen($image));
            header('Cache-Control: private, no-store');
            header('X-Content-Type-Options: nosniff');
            echo $image;
        } catch (Throwable $exception) {
            http_response_code(404);
        }
    }

    private function activeBatch(int $employeeId): ?array
    {
        $state = $_SESSION[self::SESSION_KEY][$employeeId] ?? null;
        if (!is_array($state) || time() - (int)($state['started_at'] ?? 0) > self::SESSION_TTL) {
            unset($_SESSION[self::SESSION_KEY][$employeeId]);
            $this->jsonResponse(['success' => false, 'message' => 'Phiên đăng ký đã hết hạn. Hãy bắt đầu lại.'], 410);
            return null;
        }

        return $state;
    }

    private function cameraFrame(): ?string
    {
        $jpeg = $this->camera->captureJpeg();
        if (!is_string($jpeg) || strlen($jpeg) > self::MAX_IMAGE_BYTES || !$this->isValidImage($jpeg)) {
            return null;
        }

        return $jpeg;
    }

    private function isValidImage(string $image): bool
    {
        $mime = (new finfo(FILEINFO_MIME_TYPE))->buffer($image);

        $size = @getimagesizefromstring($image);
        return in_array($mime, ['image/jpeg', 'image/png'], true)
            && $size !== false && $size[0] * $size[1] <= 16000000;
    }

    private function requestEmployeeId(): int
    {
        AuthController::requireAdmin();
        $employeeId = filter_var($_GET['id'] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
        if ($employeeId === false) {
            $this->jsonResponse(['success' => false, 'message' => 'Mã nhân viên không hợp lệ.'], 404);
        }

        return (int)$employeeId;
    }

    private function requirePostCsrf(): bool
    {
        if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
            header('Allow: POST');
            $this->jsonResponse(['success' => false, 'message' => 'Method Not Allowed'], 405);
            return false;
        }
        if (!CsrfToken::isValid()) {
            $this->jsonResponse(['success' => false, 'message' => 'Phiên biểu mẫu hết hạn. Tải lại trang và thử lại.'], 400);
            return false;
        }

        return true;
    }

    private function jsonResponse(array $payload, int $status = 200): void
    {
        http_response_code($status);
        header('Content-Type: application/json; charset=utf-8');
        header('Cache-Control: private, no-store');
        echo json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_INVALID_UTF8_SUBSTITUTE);
        exit;
    }
}

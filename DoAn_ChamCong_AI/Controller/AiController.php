<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/FaceEmbeddingModel.php';

final class AiController
{
    private FaceEmbeddingModel $embeddings;

    public function __construct()
    {
        $this->embeddings = new FaceEmbeddingModel();
    }

    /** Phục vụ gallery cho Python AI qua request loopback; không lộ credential DB. */
    public function internalFaceGallery(): void
    {
        if (!$this->isLoopbackRequest()) {
            $this->jsonResponse(['success' => false, 'message' => 'Local requests only.'], 403);
            return;
        }

        try {
            $this->jsonResponse([
                'success' => true,
                'embeddings' => $this->embeddings->findAllForInternalGallery(),
            ]);
        } catch (Throwable $exception) {
            error_log('Internal face gallery read failed.');
            $this->jsonResponse(['success' => false, 'message' => 'Không thể tải gallery khuôn mặt.'], 503);
        }
    }

    private function isLoopbackRequest(): bool
    {
        $ip = $_SERVER['REMOTE_ADDR'] ?? '';
        if (in_array($ip, ['127.0.0.1', '::1', '::ffff:127.0.0.1'], true)) {
            return true;
        }
        // Cho phep moi IP private (Docker bridge 172.x, LAN 192.168.x, 10.x)
        return filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_NO_PRIV_RANGE | FILTER_FLAG_NO_RES_RANGE) === false;
    }

    private function jsonResponse(array $payload, int $status = 200): void
    {
        http_response_code($status);
        header('Content-Type: application/json; charset=utf-8');
        header('Cache-Control: private, no-store');
        echo json_encode($payload, JSON_UNESCAPED_UNICODE);
        exit;
    }
}

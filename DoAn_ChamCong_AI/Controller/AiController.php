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
        return in_array($_SERVER['REMOTE_ADDR'] ?? '', ['127.0.0.1', '::1', '::ffff:127.0.0.1'], true);
    }

}

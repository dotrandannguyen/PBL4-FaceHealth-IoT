<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/FaceEmbeddingModel.php';
require_once __DIR__ . '/../Security/InternalApi.php';

final class AiController
{
    private FaceEmbeddingModel $embeddings;

    public function __construct()
    {
        $this->embeddings = new FaceEmbeddingModel();
    }

    /** Serve the gallery to authenticated internal AI requests without DB credentials. */
    public function internalFaceGallery(): void
    {
        if (!InternalApi::requireAuthorized()) {
            return;
        }
        if (session_status() === PHP_SESSION_ACTIVE) {
            session_write_close();
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

    private function jsonResponse(array $payload, int $status = 200): void
    {
        http_response_code($status);
        header('Content-Type: application/json; charset=utf-8');
        header('Cache-Control: private, no-store');
        echo json_encode($payload, JSON_UNESCAPED_UNICODE);
        exit;
    }
}

<?php
declare(strict_types=1);

final class CameraFrameClient
{
    private string $frameUrl;

    public function __construct(?string $frameUrl = null)
    {
        $this->frameUrl = $frameUrl ?? (
            getenv('CAMERA_FRAME_URL') ?: (
                (getenv('AI_SERVICE_URL') ?: 'http://127.0.0.1:5001') . '/internal/camera/frame'
            )
        );
    }

    public function captureJpeg(): ?string
    {
        $context = stream_context_create([
            'http' => [
                'method' => 'GET',
                'timeout' => 1.5,
                'ignore_errors' => true,
            ],
        ]);
        $image = @file_get_contents($this->frameUrl, false, $context);

        return is_string($image) && str_starts_with($image, "\xFF\xD8") ? $image : null;
    }
}

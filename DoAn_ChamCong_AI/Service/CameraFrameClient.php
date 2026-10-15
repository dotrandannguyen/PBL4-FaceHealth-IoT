<?php
declare(strict_types=1);

final class CameraFrameClient
{
    private const FRAME_URL = 'http://127.0.0.1:5000/internal/camera/frame';

    public function captureJpeg(): ?string
    {
        $context = stream_context_create([
            'http' => [
                'method' => 'GET',
                'timeout' => 1.5,
                'ignore_errors' => true,
            ],
        ]);
        $image = @file_get_contents(self::FRAME_URL, false, $context);

        return is_string($image) && str_starts_with($image, "\xFF\xD8") ? $image : null;
    }
}

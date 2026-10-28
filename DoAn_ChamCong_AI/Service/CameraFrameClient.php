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

    public function captureJpeg(?string $source = null): ?string
    {
        $url = $this->frameUrl;
        if ($source !== null && $source !== '') {
            $separator = strpos($url, '?') === false ? '?' : '&';
            $url .= $separator . 'source=' . urlencode($source);
        }

        $context = stream_context_create([
            'http' => [
                'method' => 'GET',
                'header' => 'Authorization: Bearer ' . (getenv('PBL4_INTERNAL_TOKEN') ?: '') . "\r\n",
                'timeout' => 2.0,
                'ignore_errors' => true,
                'follow_location' => 0,
            ],
        ]);
        $image = @file_get_contents($url, false, $context, 0, 5 * 1024 * 1024 + 1);
        $status = 0;
        foreach ($http_response_header ?? [] as $header) {
            if (preg_match('/^HTTP\/\S+\s+(\d{3})\b/', $header, $matches)) {
                $status = (int)$matches[1];
            }
        }
        if ($status !== 200 || !is_string($image) || strlen($image) > 5 * 1024 * 1024) {
            return null;
        }
        $size = @getimagesizefromstring($image);

        return $size !== false && $size[2] === IMAGETYPE_JPEG && $size[0] * $size[1] <= 16000000 ? $image : null;
    }
}

<?php
declare(strict_types=1);

final class AiClient
{
    private string $baseUrl;

    public function __construct(?string $baseUrl = null)
    {
        $this->baseUrl = rtrim($baseUrl ?? (getenv('AI_SERVICE_URL') ?: 'http://127.0.0.1:5001'), '/');
    }

    /** Đọc trạng thái AI service nội bộ, không khởi chạy process Python mới. */
    public function health(): array
    {
        return $this->requestJson('GET', '/health');
    }

    /** Yêu cầu AI service tải lại gallery từ endpoint nội bộ PHP. */
    public function refreshGallery(): array
    {
        return $this->requestJson('POST', '/api/ai/gallery/refresh');
    }

    /** Gửi JPEG enrollment tới AI để kiểm tra pose mà chưa nhận sample lưu trữ. */
    public function inspectEnrollmentImage(string $jpeg, string $expectedPose): array
    {
        return $this->requestEnrollmentJson('/api/ai/enrollment/inspect', $jpeg, $expectedPose);
    }

    /** Yêu cầu AI trả embedding và đúng JPEG đã dùng cho capture enrollment. */
    public function captureEnrollmentSample(string $jpeg, string $expectedPose): array
    {
        return $this->requestEnrollmentJson('/api/ai/enrollment/capture', $jpeg, $expectedPose);
    }

    private function requestJson(string $method, string $path): array
    {
        return $this->send($method, $path, $method === 'POST' ? '{}' : '', $method === 'POST' ? 30 : 4);
    }

    private function requestEnrollmentJson(string $path, string $jpeg, string $expectedPose): array
    {
        $content = json_encode([
            'image' => base64_encode($jpeg),
            'expected_pose' => $expectedPose,
        ], JSON_THROW_ON_ERROR);
        return $this->send('POST', $path, $content, 20, true);
    }

    private function send(string $method, string $path, string $content, int $timeout, bool $allowRejection = false): array
    {
        $context = stream_context_create([
            'http' => [
                'method' => $method,
                'header' => "Accept: application/json\r\nContent-Type: application/json\r\nAuthorization: Bearer " . (getenv('PBL4_INTERNAL_TOKEN') ?: '') . "\r\n",
                'content' => $content,
                'timeout' => $timeout,
                'ignore_errors' => true,
                'follow_location' => 0,
            ],
        ]);
        $body = @file_get_contents($this->baseUrl . $path, false, $context, 0, 8 * 1024 * 1024 + 1);
        if (!is_string($body) || strlen($body) > 8 * 1024 * 1024) {
            throw new RuntimeException('AI service is unavailable.');
        }
        $status = 0;
        foreach ($http_response_header ?? [] as $header) {
            if (preg_match('/^HTTP\/\S+\s+(\d{3})\b/', $header, $matches)) {
                $status = (int)$matches[1];
            }
        }
        $response = json_decode($body, true);
        if (!is_array($response) || !is_bool($response['success'] ?? null)
            || ($status !== 200 && !($allowRejection && $status === 409 && $response['success'] === false))) {
            throw new RuntimeException('AI service returned an invalid response.');
        }

        return $response;
    }
}

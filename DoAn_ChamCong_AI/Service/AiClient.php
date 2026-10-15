<?php
declare(strict_types=1);

final class AiClient
{
    private const BASE_URL = 'http://127.0.0.1:5001';

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
        $context = stream_context_create([
            'http' => [
                'method' => $method,
                'header' => "Accept: application/json\r\nContent-Type: application/json\r\n",
                'content' => $method === 'POST' ? '{}' : '',
                'timeout' => $method === 'POST' ? 30 : 4,
                'ignore_errors' => true,
            ],
        ]);
        $body = @file_get_contents(self::BASE_URL . $path, false, $context);
        if (!is_string($body)) {
            throw new RuntimeException('AI service is unavailable.');
        }

        $response = json_decode($body, true);
        if (!is_array($response)) {
            throw new RuntimeException('AI service returned an invalid response.');
        }

        return $response;
    }

    private function requestEnrollmentJson(string $path, string $jpeg, string $expectedPose): array
    {
        $content = json_encode([
            'image' => base64_encode($jpeg),
            'expected_pose' => $expectedPose,
        ], JSON_THROW_ON_ERROR);
        $context = stream_context_create([
            'http' => [
                'method' => 'POST',
                'header' => "Accept: application/json\r\nContent-Type: application/json\r\n",
                'content' => $content,
                'timeout' => 20,
                'ignore_errors' => true,
            ],
        ]);
        $body = @file_get_contents(self::BASE_URL . $path, false, $context);
        if (!is_string($body)) {
            throw new RuntimeException('AI service is unavailable.');
        }

        $response = json_decode($body, true);
        if (!is_array($response)) {
            throw new RuntimeException('AI service returned an invalid enrollment response.');
        }

        return $response;
    }
}

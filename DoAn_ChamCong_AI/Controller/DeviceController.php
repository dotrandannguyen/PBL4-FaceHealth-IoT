<?php
declare(strict_types=1);

require_once __DIR__ . '/../Model/DeviceModel.php';
require_once __DIR__ . '/AuthController.php';

final class DeviceController
{
    /** Hiển thị danh sách thiết bị; không kích hoạt camera hoặc nhận diện khuôn mặt. */
    public function index(): void
    {
        AuthController::requireAdmin();

        $devices = [];
        $deviceError = null;
        try {
            $devices = (new DeviceModel())->findAll();
        } catch (Throwable $exception) {
            error_log('Device list read failed: ' . $exception->getMessage());
            http_response_code(500);
            $deviceError = 'Không thể tải thông tin thiết bị.';
        }

        $pageTitle = 'Thiết bị';
        require __DIR__ . '/../View/devices.php';
    }
}

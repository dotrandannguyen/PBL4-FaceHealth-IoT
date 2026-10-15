<?php
declare(strict_types=1);

require_once __DIR__ . '/Security/CsrfToken.php';

if (session_status() !== PHP_SESSION_ACTIVE) {
    ini_set('session.use_strict_mode', '1');
    ini_set('session.use_only_cookies', '1');
    $isHttps = isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== '' && $_SERVER['HTTPS'] !== 'off';
    session_set_cookie_params([
        'lifetime' => 0,
        'path' => '/',
        'secure' => $isHttps,
        'httponly' => true,
        'samesite' => 'Lax',
    ]);
    session_start();
}

CsrfToken::token();

require_once __DIR__ . '/Controller/AuthController.php';
require_once __DIR__ . '/Controller/EmployeeController.php';
require_once __DIR__ . '/Controller/DashboardController.php';
require_once __DIR__ . '/Controller/ShiftController.php';
require_once __DIR__ . '/Controller/AttendanceController.php';
require_once __DIR__ . '/Controller/AiController.php';
require_once __DIR__ . '/Controller/MonitoringController.php';
require_once __DIR__ . '/Controller/MyController.php';
require_once __DIR__ . '/Controller/DeviceController.php';
require_once __DIR__ . '/Controller/FaceEnrollmentController.php';

$authController = new AuthController();
$controller = new EmployeeController();
$dashboardController = new DashboardController();
$shiftController = new ShiftController();
$attendanceController = new AttendanceController();
$aiController = new AiController();
$monitoringController = new MonitoringController();
$myController = new MyController();
$deviceController = new DeviceController();
$faceEnrollmentController = new FaceEnrollmentController();
$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
$action = $_GET['action'] ?? 'index';
$requestPath = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';

if ($requestPath === '/api/chamcong') {
    if ($method !== 'POST') {
        header('Allow: POST');
        http_response_code(405);
        exit('Method Not Allowed');
    }
    $attendanceController->recordApi();
    return;
}

if ($action === 'internal_face_gallery' && $method === 'GET') {
    $aiController->internalFaceGallery();
    return;
}

if ($action === 'face_image' && $method === 'GET') {
    $faceEnrollmentController->image();
    return;
}

if ($action === 'face_camera_frame' && $method === 'GET') {
    $faceEnrollmentController->frame();
    return;
}

if ($action === 'face_enrollment_start' && $method === 'POST') {
    $faceEnrollmentController->start();
    return;
}

if ($action === 'face_enrollment_pose' && $method === 'POST') {
    $faceEnrollmentController->inspectPose();
    return;
}

if ($action === 'face_enrollment_capture' && $method === 'POST') {
    $faceEnrollmentController->capture();
    return;
}

if ($action === 'face_enrollment_complete' && $method === 'POST') {
    $faceEnrollmentController->complete();
    return;
}

if ($action === 'face_enrollment_cancel' && $method === 'POST') {
    $faceEnrollmentController->cancel();
    return;
}

if ($action === 'face_registration_delete' && $method === 'POST') {
    $faceEnrollmentController->deleteRegistration();
    return;
}

$faceEnrollmentActions = [
    'face_enrollment_start' => 'start',
    'face_enrollment_pose' => 'inspectPose',
    'face_enrollment_capture' => 'capture',
    'face_enrollment_complete' => 'complete',
    'face_enrollment_cancel' => 'cancel',
    'face_registration_delete' => 'deleteRegistration',
];
if (isset($faceEnrollmentActions[$action]) && $method === 'POST') {
    $faceEnrollmentController->{$faceEnrollmentActions[$action]}();
    return;
}

if ($action === 'devices' && $method === 'GET') {
    $deviceController->index();
    return;
}

if ($action === 'ai_camera' && $method === 'GET') {
    header('Location: /?action=devices', true, 302);
    return;
}

if ($action === 'login' && $method === 'GET') {
    $authController->showLogin();
    return;
}

if ($action === 'login' && $method === 'POST') {
    $authController->login();
    return;
}

if ($action === 'logout' && $method === 'POST') {
    $authController->logout();
    return;
}

if ($action === 'index' && $method === 'GET') {
    $controller->index();
    return;
}

if ($action === 'dashboard' && $method === 'GET') {
    $dashboardController->index();
    return;
}

if ($action === 'create' && $method === 'GET') {
    $controller->createForm();
    return;
}

if ($action === 'store' && $method === 'POST') {
    $controller->store();
    return;
}

if ($action === 'edit' && $method === 'GET') {
    $controller->editForm($controller->requestedEmployeeId());
    return;
}

if ($action === 'update' && $method === 'POST') {
    $controller->update($controller->requestedEmployeeId());
    return;
}

if ($action === 'shifts' && $method === 'GET') {
    $shiftController->index();
    return;
}

if ($action === 'assign_shift' && $method === 'POST') {
    $shiftController->assign();
    return;
}

if ($action === 'unassign_shift' && $method === 'POST') {
    $shiftController->unassign();
    return;
}

if ($action === 'create_shift' && $method === 'POST') {
    $shiftController->createShift();
    return;
}

if ($action === 'update_shift' && $method === 'POST') {
    $shiftController->updateShift();
    return;
}

if ($action === 'delete_shift' && $method === 'POST') {
    $shiftController->deleteShift();
    return;
}

if ($action === 'disable_shift' && $method === 'POST') {
    $shiftController->disableShift();
    return;
}

if ($action === 'enable_shift' && $method === 'POST') {
    $shiftController->enableShift();
    return;
}

if ($action === 'attendance' && $method === 'GET') {
    $attendanceController->index();
    return;
}

if ($action === 'monitoring' && $method === 'GET') {
    $monitoringController->index();
    return;
}

if (in_array($action, ['health', 'alerts'], true) && $method === 'GET') {
    $query = $_GET;
    $query['action'] = 'monitoring';
    if ($action === 'health' && isset($query['page'])) {
        $query['health_page'] = $query['page'];
    }
    if ($action === 'alerts' && isset($query['page'])) {
        $query['alert_page'] = $query['page'];
    }
    unset($query['page']);
    header('Location: /?' . http_build_query($query), true, 302);
    return;
}

if ($action === 'my' && $method === 'GET') {
    $myController->index();
    return;
}

if (in_array($action, ['my_attendance_image_in', 'my_attendance_image_out'], true) && $method === 'GET') {
    $myController->sendEvidence($action === 'my_attendance_image_in' ? 'in' : 'out');
    return;
}

if ($action === 'attendance_image_in' && $method === 'GET') {
    $attendanceController->sendEvidence('in');
    return;
}

if ($action === 'attendance_image_out' && $method === 'GET') {
    $attendanceController->sendEvidence('out');
    return;
}

if (in_array($action, ['index', 'dashboard', 'create', 'store', 'edit', 'update', 'login', 'logout', 'shifts', 'assign_shift', 'unassign_shift', 'create_shift', 'update_shift', 'delete_shift', 'disable_shift', 'enable_shift', 'attendance', 'health', 'alerts', 'monitoring', 'attendance_image_in', 'attendance_image_out', 'my', 'my_attendance_image_in', 'my_attendance_image_out', 'internal_face_gallery', 'ai_camera', 'devices', 'face_image', 'face_camera_frame', ...array_keys($faceEnrollmentActions)], true)) {
    $allowedMethods = match ($action) {
        'login' => 'GET, POST',
        'store', 'update', 'logout', 'assign_shift', 'unassign_shift', 'create_shift', 'update_shift', 'delete_shift', 'disable_shift', 'enable_shift' => 'POST',
        'internal_face_gallery', 'ai_camera', 'devices', 'face_image', 'face_camera_frame', 'attendance_image_in', 'attendance_image_out', 'my', 'my_attendance_image_in', 'my_attendance_image_out', 'health', 'alerts', 'monitoring' => 'GET',
        default => isset($faceEnrollmentActions[$action]) ? 'POST' : 'GET',
    };
    header('Allow: ' . $allowedMethods);
    http_response_code(405);
    exit('Method Not Allowed');
}

http_response_code(404);
echo 'Không tìm thấy trang được yêu cầu.';

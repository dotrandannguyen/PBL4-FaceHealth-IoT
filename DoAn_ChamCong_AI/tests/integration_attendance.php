<?php
declare(strict_types=1);

require_once __DIR__ . '/../Service/AttendancePayload.php';
require_once __DIR__ . '/../Service/AttendanceService.php';
require_once __DIR__ . '/../Service/FaceSample.php';

date_default_timezone_set('Asia/Ho_Chi_Minh');

if (getenv('PBL4_TEST_DATABASE') !== 'isolated' || getenv('MARIADB_HOST') !== '127.0.0.1'
    || (int)getenv('MARIADB_PORT') === 3306) {
    throw new RuntimeException('Run only through the isolated database test runner.');
}

function check(bool $condition, string $message): void {
    if (!$condition) { throw new RuntimeException($message); }
}

function event(string $id, int $employee = 1, string $status = 'Normal', int $offset = -3600): array {
    return ['event_id' => $id, 'MaNV' => $employee, 'MaTB' => 1,
        'occurred_at' => date('c', strtotime('yesterday 12:00:00') + $offset), 'TrangThai' => $status,
        'NhipTim' => 80, 'SpO2' => 98, 'image' => null];
}

/** Each request uses a fresh PHP process/connection, like independent devices. */
function processEventsIndependently(array $events): array {
    $processes = [];
    foreach ($events as $payload) {
        $proc = proc_open([PHP_BINARY, __FILE__, 'worker', base64_encode(json_encode($payload, JSON_THROW_ON_ERROR))],
            [0=>['pipe','r'],1=>['pipe','w'],2=>['pipe','w']], $pipes, null, null, ['bypass_shell'=>true]);
        check(is_resource($proc), 'Could not start isolated attendance worker');
        fclose($pipes[0]);
        $processes[] = [$proc, $pipes];
    }
    $results = [];
    foreach ($processes as [$proc, $pipes]) {
        $out = stream_get_contents($pipes[1]);
        $err = stream_get_contents($pipes[2]);
        fclose($pipes[1]);
        fclose($pipes[2]);
        check(proc_close($proc) === 0, 'Independent attendance worker: ' . $err);
        $results[] = json_decode($out, true, 512, JSON_THROW_ON_ERROR);
    }
    return $results;
}

if (($argv[1] ?? '') === 'worker') {
    $payload = json_decode(base64_decode($argv[2]), true, 512, JSON_THROW_ON_ERROR);
    echo json_encode((new AttendanceService())->processEvent(AttendancePayload::fromArray($payload)), JSON_THROW_ON_ERROR);
    exit;
}

if (($argv[1] ?? '') === 'http_inspect') {
    $connection = Database::getConnection();
    $state = [];
    foreach (['ChamCong','AttendanceEvent','LichSuSucKhoe','LichSuTrangThai','CanhBao'] as $table) {
        $state[$table] = (int)$connection->query("SELECT COUNT(*) FROM $table WHERE MaNV IN (10,11,12)")->fetchColumn();
    }
    $state['attendance'] = $connection->query('SELECT MaNV, GioVao, GioRa, MaCa, SHA2(AnhVao,256) AS ImageHash, TheTrangVao, TheTrangRa FROM ChamCong WHERE MaNV IN (10,11,12) ORDER BY MaNV')->fetchAll();
    echo json_encode($state, JSON_THROW_ON_ERROR);
    exit;
}

if (($argv[1] ?? '') === 'http_seed') {
    Database::getConnection()->exec("INSERT INTO NhanVien (MaNV,HoTen,MaVaiTro) VALUES (10,'HTTP One',2),(11,'HTTP Two',2),(12,'HTTP Three',2)");
    echo "SEEDED\n";
    exit;
}

if (($argv[1] ?? '') === 'http_fail_health') {
    Database::getConnection()->exec("CREATE TRIGGER fail_http_health BEFORE INSERT ON LichSuSucKhoe FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Injected private database failure'");
    echo "FAILURE_ENABLED\n";
    exit;
}

if (($argv[1] ?? '') === 'http_clear_health_failure') {
    Database::getConnection()->exec('DROP TRIGGER fail_http_health');
    echo "FAILURE_CLEARED\n";
    exit;
}

$pdo = new PDO('mysql:host=127.0.0.1;port=' . getenv('MARIADB_PORT') . ';charset=utf8mb4', 'root', getenv('MARIADB_PASSWORD') ?: '',
    [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
$schema = file_get_contents(__DIR__ . '/../migration/mariadb_schema.sql');
$oldSchema = preg_replace('/^\s*`TheTrang(?:Vao|Ra)?` VARCHAR\(100\) NULL,\R/m', '', $schema);
$oldSchema = substr($oldSchema, 0, strpos($oldSchema, 'CREATE TABLE IF NOT EXISTS AttendanceEvent'));
$pdo->exec($oldSchema);
$upgrade = file_get_contents(__DIR__ . '/../migration/02_attendance_integrity.sql');
$pdo->exec($upgrade);
$pdo->exec($upgrade);
check((int)$pdo->query("SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = 'DoAn_ChamCong_AI_MariaDB' AND TABLE_NAME = 'ChamCong' AND COLUMN_NAME IN ('TheTrang','TheTrangVao','TheTrangRa')")->fetchColumn() === 3, 'Upgrade columns');
// Also execute the complete fresh-install schema in a second disposable database.
$pdo->exec(str_replace('DoAn_ChamCong_AI_MariaDB', 'PBL4_Fresh_Test', $schema));
$pdo->exec('USE DoAn_ChamCong_AI_MariaDB');
$pdo->exec("INSERT INTO VaiTro VALUES (1,'Admin'),(2,'Employee'); INSERT INTO ThietBi VALUES (1,'Test','Online');
    INSERT INTO CaLamViec (MaCa,TenCa,GioBatDau,GioKetThuc) VALUES (1,'Test','08:00','17:00');
    INSERT INTO NhanVien (MaNV,HoTen,MaVaiTro) VALUES (1,'Test One',2),(2,'Test Two',2),(3,'Test Three',2);
    INSERT INTO DanhMucBieuHien (MaBieuHien,TenBieuHien) VALUES (1,'Normal'),(2,'Fatigue'),(3,'Exhausted');
    INSERT INTO LoaiCanhBao VALUES (1,'Sensor'),(2,'Face');");
$service = new AttendanceService();
$one = event('11111111-1111-4111-8111-111111111111');
$result = $service->processEvent(AttendancePayload::fromArray($one));
check($result['action'] === 'checkin', 'Check-in');
$replayed = $service->processEvent(AttendancePayload::fromArray($one));
check($replayed['action'] === 'checkin' && $replayed['duplicate'] === true, 'Replay must not check out');
check((int)$pdo->query('SELECT COUNT(*) FROM LichSuSucKhoe')->fetchColumn() === 1, 'Replay duplicated health');
$changed = $one; $changed['NhipTim'] = 90;
check($service->processEvent(AttendancePayload::fromArray($changed))['status'] === 'error', 'Event conflict');
$two = event('22222222-2222-4222-8222-222222222222', 1, 'Unknown', -1800);
check($service->processEvent(AttendancePayload::fromArray($two))['action'] === 'checkout', 'Check-out');
check((int)$pdo->query('SELECT COUNT(*) FROM LichSuTrangThai')->fetchColumn() === 1, 'Unknown must not be Normal');
check($pdo->query('SELECT TheTrangRa FROM ChamCong WHERE MaNV=1')->fetchColumn() === 'Chưa đánh giá', 'Unknown stored label');
$missing = event('33333333-3333-4333-8333-333333333333', 99);
check($service->processEvent(AttendancePayload::fromArray($missing))['status'] === 'error', 'Unknown employee');
check((int)$pdo->query('SELECT COUNT(*) FROM NhanVien WHERE MaNV=99')->fetchColumn() === 0, 'Implicit employee creation');

$pdo->exec("CREATE TRIGGER fail_alert BEFORE INSERT ON CanhBao FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Injected test failure'");
$failure = event('44444444-4444-4444-8444-444444444444', 2, 'Fatigue');
check($service->processEvent(AttendancePayload::fromArray($failure))['status'] === 'error', 'Injected failure');
foreach (['ChamCong','LichSuSucKhoe','LichSuTrangThai','AttendanceEvent'] as $table) {
    check((int)$pdo->query("SELECT COUNT(*) FROM $table WHERE MaNV=2")->fetchColumn() === 0, 'Rollback failed: ' . $table);
}
$pdo->exec('DROP TRIGGER fail_alert');
check($service->processEvent(AttendancePayload::fromArray($failure))['status'] === 'success', 'Retry after rollback');

$concurrent = event('55555555-5555-4555-8555-555555555555', 3);
$processes = [];
for ($i=0; $i<6; $i++) {
    $proc = proc_open([PHP_BINARY, __FILE__, 'worker', base64_encode(json_encode($concurrent))],
        [0=>['pipe','r'],1=>['pipe','w'],2=>['pipe','w']], $pipes, null, null, ['bypass_shell'=>true]);
    fclose($pipes[0]);
    $processes[] = [$proc,$pipes];
}
foreach ($processes as [$proc,$pipes]) {
    $out = stream_get_contents($pipes[1]); $err = stream_get_contents($pipes[2]);
    fclose($pipes[1]); fclose($pipes[2]);
    check(proc_close($proc) === 0, 'Concurrent worker: ' . $err);
    check(json_decode($out,true)['action'] === 'checkin', 'Concurrent replay changed action');
}
check((int)$pdo->query('SELECT COUNT(*) FROM ChamCong WHERE MaNV=3')->fetchColumn() === 1, 'Concurrent duplicate row');
check($pdo->query('SELECT GioRa FROM ChamCong WHERE MaNV=3')->fetchColumn() === null, 'Concurrent false checkout');

// A disabled/changed assignment must not replace the shift attached at check-in.
$pdo->exec("INSERT INTO CaLamViec (MaCa,TenCa,GioBatDau,GioKetThuc) VALUES (2,'Replacement','09:00','18:00'); UPDATE CaLamViec SET TrangThai=0 WHERE MaCa=1");
$originalShift = $service->processEvent(AttendancePayload::fromArray(event('66666666-6666-4666-8666-666666666666', 3, 'Normal', -1800)));
check($originalShift['action'] === 'checkout' && $originalShift['MaCa'] === 1, 'Checkout changed historical shift');
$pdo->exec('UPDATE CaLamViec SET TrangThai=0');
$complete = $service->processEvent(AttendancePayload::fromArray(event('77777777-7777-4777-8777-777777777777', 3, 'Normal', -900)));
check($complete['action'] === 'completed' && $complete['MaCa'] === 1, 'Completed attendance needs an active shift');
$pdo->exec('UPDATE CaLamViec SET TrangThai=1 WHERE MaCa=1');

$early = event('88888888-8888-4888-8888-888888888888', 2, 'Normal', -4000);
check($service->processEvent(AttendancePayload::fromArray($early))['http_status'] === 409, 'Out-of-order event');
$missingDevice = event('99999999-9999-4999-8999-999999999999', 2, 'Normal', -900);
$missingDevice['MaTB'] = 999;
check($service->processEvent(AttendancePayload::fromArray($missingDevice))['http_status'] === 409, 'Unregistered device');

foreach (['TrangThai'=>'Unexpected','SpO2'=>101,'NhipTim'=>-1,'image'=>'not-base64','occurred_at'=>'2026-02-31T08:00:00+07:00','MaNV'=>true] as $key=>$value) {
    $invalid = $one; $invalid[$key] = $value;
    try { AttendancePayload::fromArray($invalid); throw new RuntimeException('Accepted invalid ' . $key); }
    catch (InvalidArgumentException $expected) {}
}
$vector = pack('g*', ...array_fill(0,512,1.0));
FaceSample::requireSameIdentity($vector,$vector);
try { FaceSample::vector(pack('g*', ...array_fill(0,512,NAN))); throw new RuntimeException('Accepted NaN'); }
catch (InvalidArgumentException $expected) {}
// The daily quota is authoritative in MariaDB, across restarts and devices.
$pdo->exec("INSERT INTO ThietBi VALUES (2,'Second test device','Online');
    INSERT INTO NhanVien (MaNV,HoTen,MaVaiTro) VALUES
    (4,'Daily quota restart',2),(5,'Concurrent checkout quota',2),(6,'Concurrent checkin quota',2)");
$dailyIn = event('a0000000-0000-4000-8000-000000000001', 4);
$dailyOut = event('a0000000-0000-4000-8000-000000000002', 4, 'Fatigue', -1800);
$dailyOut['MaTB'] = 2;
$dailyAgain = event('a0000000-0000-4000-8000-000000000003', 4, 'Exhausted', -900);
check(processEventsIndependently([$dailyIn])[0]['action'] === 'checkin', 'Restarted process check-in');
check(processEventsIndependently([$dailyOut])[0]['action'] === 'checkout', 'Second device check-out');
$beforeCompleted = $pdo->query('SELECT * FROM ChamCong WHERE MaNV=4')->fetchAll();
$healthBeforeCompleted = (int)$pdo->query('SELECT COUNT(*) FROM LichSuSucKhoe WHERE MaNV=4')->fetchColumn();
$stateBeforeCompleted = (int)$pdo->query('SELECT COUNT(*) FROM LichSuTrangThai WHERE MaNV=4')->fetchColumn();
$alertBeforeCompleted = (int)$pdo->query('SELECT COUNT(*) FROM CanhBao WHERE MaNV=4')->fetchColumn();
$completed = processEventsIndependently([$dailyAgain])[0];
check($completed['status'] === 'completed' && $completed['action'] === 'completed', 'Check-in reopened a checked-out day');
$completedReplay = processEventsIndependently([$dailyAgain])[0];
check($completedReplay['action'] === 'completed' && $completedReplay['duplicate'] === true, 'Completed event replay changed the quota');
check($pdo->query('SELECT * FROM ChamCong WHERE MaNV=4')->fetchAll() === $beforeCompleted, 'Completed event changed check-in/out data');
check((int)$pdo->query('SELECT COUNT(*) FROM LichSuSucKhoe WHERE MaNV=4')->fetchColumn() === $healthBeforeCompleted, 'Completed event added health');
check((int)$pdo->query('SELECT COUNT(*) FROM LichSuTrangThai WHERE MaNV=4')->fetchColumn() === $stateBeforeCompleted, 'Completed event added state');
check((int)$pdo->query('SELECT COUNT(*) FROM CanhBao WHERE MaNV=4')->fetchColumn() === $alertBeforeCompleted, 'Completed event added alerts');
$newDay = $dailyIn;
$newDay['event_id'] = 'a0000000-0000-4000-8000-000000000004';
$newDay['occurred_at'] = date('Y-m-d\T00:00:00P');
check(processEventsIndependently([$newDay])[0]['action'] === 'checkin', 'Daily quota did not reset at Vietnam midnight');
check((int)$pdo->query('SELECT COUNT(*) FROM ChamCong WHERE MaNV=4')->fetchColumn() === 2, 'Expected exactly one record per date');

// Six distinct checkout events race from two devices: only one may update GioRa.
$primeCheckout = event('b0000000-0000-4000-8000-000000000001', 5);
check(processEventsIndependently([$primeCheckout])[0]['action'] === 'checkin', 'Concurrent checkout setup');
$checkoutRace = [];
for ($i=0; $i<6; $i++) {
    $payload = event(sprintf('b0000000-0000-4000-8000-%012d', $i+2), 5, 'Normal', -1800+$i*60);
    $payload['MaTB'] = 1 + $i % 2;
    $checkoutRace[] = $payload;
}
$checkoutActions = array_count_values(array_column(processEventsIndependently($checkoutRace), 'action'));
check(($checkoutActions['checkout'] ?? 0) === 1 && ($checkoutActions['completed'] ?? 0) === 5,
    'Concurrent distinct requests exceeded one daily checkout');
check((int)$pdo->query('SELECT COUNT(*) FROM ChamCong WHERE MaNV=5')->fetchColumn() === 1, 'Concurrent checkout inserted another daily row');
check((int)$pdo->query('SELECT COUNT(*) FROM LichSuSucKhoe WHERE MaNV=5')->fetchColumn() === 2, 'Completed races added health writes');

// An absent daily row also needs serialization, not just event_id deduplication.
$checkinRace = [];
for ($i=0; $i<6; $i++) {
    $payload = event(sprintf('c0000000-0000-4000-8000-%012d', $i+1), 6);
    $payload['MaTB'] = 1 + $i % 2;
    $checkinRace[] = $payload;
}
$checkinActions = array_count_values(array_column(processEventsIndependently($checkinRace), 'action'));
check(($checkinActions['checkin'] ?? 0) === 1 && ($checkinActions['error'] ?? 0) === 5,
    'Concurrent same-time requests exceeded one daily check-in');
check((int)$pdo->query('SELECT COUNT(*) FROM ChamCong WHERE MaNV=6')->fetchColumn() === 1, 'Concurrent check-in inserted duplicate daily rows');
check($pdo->query('SELECT GioRa FROM ChamCong WHERE MaNV=6')->fetchColumn() === null, 'Same-time race fabricated checkout');

echo "PASS: fresh schema, repeatable migration, check-in/out, replay, conflict, Unknown, rollback, concurrent replay, historical shift, ordering, device validation, embeddings, daily one-in/one-out quota across devices/restarts, distinct-event races and next-day reset\n";

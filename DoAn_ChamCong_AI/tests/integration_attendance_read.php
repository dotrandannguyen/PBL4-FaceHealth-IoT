<?php
declare(strict_types=1);
require_once __DIR__ . '/../Model/AttendanceModel.php';

if (getenv('PBL4_TEST_DATABASE') !== 'isolated' || getenv('MARIADB_HOST') !== '127.0.0.1'
    || (int)getenv('MARIADB_PORT') === 3306) {
    throw new RuntimeException('Only run through the disposable database runner.');
}
function verifyRead(bool $condition, string $message): void {
    if (!$condition) { throw new RuntimeException($message); }
}
$pdo = Database::getConnection();
$pdo->beginTransaction();
try {
    $pdo->exec("INSERT INTO CaLamViec (MaCa,TenCa,GioBatDau,GioKetThuc,TrangThai)
        VALUES (90,'Read active','08:00','17:00',1),(91,'Read inactive','09:00','18:00',0);
        INSERT INTO NhanVien (MaNV,HoTen,MaVaiTro) VALUES
        (31,'Read Fixture Active',2),(32,'Read Fixture Inactive',2),(33,'Read Fixture Unassigned',2),
        (34,'Read Fixture Recorded',2),(35,'Read Fixture Boundary',2);
        INSERT INTO PhanCaNhanVien (MaNV,MaCa,NgayLamViec) VALUES
        (31,90,'2001-01-02'),(32,91,'2001-01-02'),(34,90,'2001-01-02');
        INSERT INTO ChamCong (MaNV,MaTB,MaCa,GioVao,TheTrangVao) VALUES
        (34,1,90,'2001-01-01 23:59:59','Normal'),
        (34,1,90,'2001-01-02 08:00:00','Normal'),
        (34,1,90,'2001-01-02 12:00:00','Normal');");
    $pdo->exec("INSERT INTO ChamCong (MaNV,MaTB,MaCa,GioVao,TheTrangVao)
        VALUES (34,1,91,'2001-01-02 12:00:00','Chưa đánh giá')");
    $latest = (int)$pdo->lastInsertId();
    $pdo->exec("INSERT INTO ChamCong (MaNV,MaTB,MaCa,GioVao) VALUES
        (34,1,90,'2001-01-04 00:00:00'),(35,1,90,'2001-01-03 00:00:00')");
    $model = new AttendanceModel();
    $rows = $model->findDaily('2001-01-02', null, 'Read Fixture', 20, 0);
    verifyRead(count($rows) === 5 && $model->countDaily('2001-01-02', null, 'Read Fixture') === 5,
        'Daily page must include employees with no records or active shift');
    $byId = array_column($rows, null, 'MaNV');
    verifyRead($byId[31]['TenCa'] === 'Read active' && $byId[31]['MaCC'] === null, 'Active assignment');
    verifyRead($byId[32]['TenCa'] === null && $byId[32]['MaCC'] === null, 'Inactive assignment is not a current shift');
    verifyRead($byId[33]['TenCa'] === null && $byId[33]['MaCC'] === null, 'Unassigned employee retained');
    verifyRead((int)$byId[34]['MaCC'] === $latest && $byId[34]['TenCa'] === 'Read inactive',
        'Latest record keeps its recorded shift after reassignment/deactivation');
    verifyRead($byId[34]['TheTrangVao'] === 'Chưa đánh giá' && (int)$byId[34]['HasImageIn'] === 0,
        'Recorded status and missing evidence retained');
    verifyRead($byId[35]['MaCC'] === null, 'Next-day midnight excluded from daily page');
    verifyRead(array_map('intval', array_column($model->findDaily('2001-01-02', null, 'Read Fixture', 2, 2), 'MaNV')) === [33,34],
        'Daily pagination');
    verifyRead(count($model->findDaily('2001-01-02', 34, 'Recorded', 20)) === 1
        && $model->countDaily('2001-01-02', 34, 'Recorded') === 1
        && $model->findDaily('2001-01-02', 34, 'not-found') === [], 'Daily combined filters');
    $history = $model->findHistory('2001-01-02', '2001-01-03', 34, 'Read Fixture', 20);
    verifyRead(count($history) === 3 && $model->countHistory('2001-01-02', '2001-01-03', 34, 'Read Fixture') === 3,
        'History date bounds and filters');
    verifyRead((int)$history[0]['MaCC'] === $latest && $history[0]['TenCa'] === 'Read inactive',
        'History and daily agree on latest record and historical shift');
    verifyRead(count($model->findHistory('2001-01-02', '2001-01-03', null, 'Read Fixture')) === 4,
        'History includes end-date midnight');
    verifyRead((int)$model->findHistory('2001-01-02', '2001-01-03', 34, null, 1, 1)[0]['MaCC'] === (int)$history[1]['MaCC'],
        'History pagination');
    echo "PASS: attendance daily/history reads, shift joins, missing records, latest record, bounds, filters and pagination\n";
} finally {
    $pdo->rollBack();
}

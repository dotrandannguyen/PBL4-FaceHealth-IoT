<?php
declare(strict_types=1);
require_once __DIR__ . '/../Model/FaceEmbeddingModel.php';

if (getenv('PBL4_TEST_DATABASE') !== 'isolated' || getenv('MARIADB_HOST') !== '127.0.0.1'
    || (int)getenv('MARIADB_PORT') === 3306) {
    throw new RuntimeException('Only use the isolated database runner.');
}
function ensure(bool $condition, string $message): void {
    if (!$condition) { throw new RuntimeException($message); }
}
function samples(int $axis = 0): array {
    $vector = array_fill(0, 512, 0.0);
    $vector[$axis] = 1.0;
    $png = base64_decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC', true);
    return array_map(static fn(string $pose): array => ['pose' => $pose, 'vector' => pack('g*', ...$vector), 'image' => $png],
        ['frontal','left','right','up','down']);
}
$pdo = Database::getConnection();
$model = new FaceEmbeddingModel();
$mode = $argv[1] ?? '';
if ($mode === 'worker') {
    echo json_encode($model->replaceByEmployee(20, samples((int)$argv[2])), JSON_THROW_ON_ERROR);
    exit;
}
if ($mode === 'inspect') {
    $rows = $pdo->query('SELECT MaEmbedding, SHA2(VectorData,256) AS vector_hash, SHA2(AnhKhuonMat,256) AS image_hash FROM FaceEmbedding WHERE MaNV=21 ORDER BY MaEmbedding')->fetchAll();
    echo json_encode(['samples' => $rows, 'avatar' => $pdo->query('SELECT AnhKhuonMat FROM NhanVien WHERE MaNV=21')->fetchColumn()], JSON_THROW_ON_ERROR);
    exit;
}
if ($mode === 'fail_avatar' || $mode === 'clear_failure') {
    $pdo->exec('DROP TRIGGER IF EXISTS fail_enrollment_avatar');
    if ($mode === 'fail_avatar') {
        $pdo->exec("CREATE TRIGGER fail_enrollment_avatar BEFORE UPDATE ON NhanVien FOR EACH ROW BEGIN IF NEW.MaNV IN (20,21) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Injected avatar failure'; END IF; END");
    }
    echo 'OK';
    exit;
}
$pdo->exec("INSERT INTO NhanVien (MaNV,HoTen,MaVaiTro) VALUES (20,'Enrollment model',2),(21,'Enrollment HTTP',2),(22,'Enrollment admin',1)");
$account = $pdo->prepare("INSERT INTO TaiKhoan (MaNV,TenDangNhap,MatKhau) VALUES (22,'enrollment-test-admin',:password)");
$account->execute(['password' => password_hash('isolated-test-password', PASSWORD_DEFAULT)]);
$batch = samples();
$ids = $model->replaceByEmployee(20, $batch);
ensure(count($ids) === 5 && $model->countByEmployee(20) === 5, 'Initial five samples');
$avatar = $pdo->query('SELECT AnhKhuonMat FROM NhanVien WHERE MaNV=20')->fetchColumn();
ensure($avatar === 'data:image/png;base64,' . base64_encode($batch[0]['image']), 'Avatar must match first sample and MIME');
$before = $model->findByEmployee(20);
$invalid = [];
$invalid[] = array_slice($batch, 0, 4);
$bad = $batch; $bad[1]['pose'] = 'right'; $invalid[] = $bad;
$bad = $batch; $bad[1]['vector'] = samples(1)[1]['vector']; $invalid[] = $bad;
$bad = $batch; $bad[0]['vector'] = pack('g*', ...array_fill(0, 512, NAN)); $invalid[] = $bad;
$bad = $batch; $bad[0]['vector'] = str_repeat("\0", 2048); $invalid[] = $bad;
$bad = $batch; $bad[0]['image'] = 'invalid image'; $invalid[] = $bad;
foreach ($invalid as $case) {
    try { $model->replaceByEmployee(20, $case); throw new RuntimeException('Invalid batch accepted'); }
    catch (InvalidArgumentException $expected) {}
    ensure($model->findByEmployee(20) === $before, 'Invalid batch changed old samples');
}
$pdo->exec("CREATE TRIGGER fail_enrollment_avatar BEFORE UPDATE ON NhanVien FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Injected avatar failure'");
foreach (['replace','delete'] as $operation) {
    try {
        if ($operation === 'replace') { $model->replaceByEmployee(20, samples(1)); }
        else { $model->deleteByEmployee(20); }
        throw new RuntimeException('Expected rollback failure');
    } catch (PDOException $expected) {}
    ensure($model->findByEmployee(20) === $before, 'Avatar failure did not roll back samples');
    ensure($pdo->query('SELECT AnhKhuonMat FROM NhanVien WHERE MaNV=20')->fetchColumn() === $avatar, 'Avatar changed on failure');
}
$pdo->exec('DROP TRIGGER fail_enrollment_avatar');
$processes = [];
for ($i=0; $i<4; $i++) {
    $process = proc_open([PHP_BINARY, __FILE__, 'worker', (string)$i],
        [0=>['pipe','r'],1=>['pipe','w'],2=>['pipe','w']], $pipes, null, null, ['bypass_shell'=>true]);
    fclose($pipes[0]);
    $processes[] = [$process,$pipes];
}
foreach ($processes as [$process,$pipes]) {
    $output = stream_get_contents($pipes[1]); fclose($pipes[1]);
    $error = stream_get_contents($pipes[2]); fclose($pipes[2]);
    ensure(proc_close($process) === 0, 'Concurrent replacement failed: ' . $error);
    ensure(count(json_decode($output, true, 512, JSON_THROW_ON_ERROR)) === 5, 'Concurrent batch result');
}
ensure($model->countByEmployee(20) === 5, 'Concurrent batches merged or lost');
ensure((int)$pdo->query('SELECT COUNT(DISTINCT SHA2(VectorData,256)) FROM FaceEmbedding WHERE MaNV=20')->fetchColumn() === 1, 'Concurrent batches mixed identities');
ensure($model->deleteByEmployee(20) === 5 && $model->countByEmployee(20) === 0, 'Delete all samples');
ensure($pdo->query('SELECT AnhKhuonMat FROM NhanVien WHERE MaNV=20')->fetchColumn() === null, 'Delete must clear avatar');
echo "PASS: Enrollment validation, avatar/sample rollback, four concurrent replacements, deletion\n";

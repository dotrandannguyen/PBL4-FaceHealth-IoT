<?php require __DIR__ . '/layout/header.php'; ?>
<?php $h = static fn(mixed $value): string => htmlspecialchars((string)($value ?? ''), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); ?>
<main class="page-container device-page">
    <?php if ($deviceError !== null): ?><div class="notice notice--error" role="alert"><?= $h($deviceError) ?></div><?php endif; ?>
    <section class="workspace" aria-label="Thiết bị chấm công">
        <?php if ($devices === []): ?><div class="empty-state">Chưa có thiết bị được khai báo.</div><?php else: ?>
            <div class="table-scroll"><table class="employee-table data-table">
                <caption class="visually-hidden">Danh sách thiết bị chấm công</caption>
                <thead><tr><th>Mã thiết bị</th><th>Loại thiết bị</th><th>Trạng thái</th></tr></thead>
                <tbody><?php foreach ($devices as $device): ?><tr><td><span class="employee-code">TB<?= str_pad((string)(int)$device['MaTB'], 3, '0', STR_PAD_LEFT) ?></span></td><td><?= $h($device['LoaiTB'] ?? '--') ?></td><td><?= $h($device['TrangThai'] ?? '--') ?></td></tr><?php endforeach; ?></tbody>
            </table></div>
        <?php endif; ?>
        <section class="device-camera-placeholder" aria-labelledby="device-camera-title">
            <h2 id="device-camera-title">Chưa kết nối camera từ máy chấm công</h2>
            <p>Hình ảnh trực tiếp sẽ hiển thị tại đây sau khi thiết bị ESP/camera được tích hợp.</p>
        </section>
    </section>
</main>
<?php require __DIR__ . '/layout/footer.php'; ?>

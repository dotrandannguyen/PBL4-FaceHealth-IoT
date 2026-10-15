<?php
require __DIR__ . '/layout/header.php';
$h = static fn(mixed $value): string => htmlspecialchars((string)($value ?? ''), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
$baseQuery = [
    'action' => 'monitoring',
    'tab' => $activeTab,
    'from_date' => $filters['from_date'],
    'to_date' => $filters['to_date'],
    'employee_id' => $filters['employee_id'] ?? '',
    'keyword' => $filters['keyword'],
    'category' => $filters['category'],
    'per_page' => $pageSize,
    'health_page' => $healthPage,
    'alert_page' => $alertPage,
];
$healthPageUrl = static function (int $targetPage) use ($baseQuery): string {
    $query = $baseQuery;
    $query['health_page'] = $targetPage;
    return '/?' . http_build_query($query);
};
$alertPageUrl = static function (int $targetPage) use ($baseQuery): string {
    $query = $baseQuery;
    $query['alert_page'] = $targetPage;
    return '/?' . http_build_query($query);
};
$chartJson = json_encode($chartData, JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT);
$tabQuery = $baseQuery;
$tabQuery['health_page'] = 1;
$tabQuery['tab'] = 'health';
$healthTabUrl = '/?' . http_build_query($tabQuery);
$tabQuery['alert_page'] = 1;
$tabQuery['tab'] = 'alerts';
$alertsTabUrl = '/?' . http_build_query($tabQuery);
?>
<main class="page-container">
    <section class="workspace" aria-label="Sức khỏe và cảnh báo">
        <?php if ($error !== null): ?><div class="notice notice--error" role="alert"><?= $h($error) ?></div><?php endif; ?>
        <form class="workspace-filters" method="get" action="/">
            <input type="hidden" name="action" value="monitoring">
            <input type="hidden" name="tab" value="<?= $h($activeTab) ?>">
            <div class="filter-grid monitoring-filter-grid">
                <div class="form-field"><label for="monitoring-from">Từ ngày</label><input id="monitoring-from" type="date" name="from_date" value="<?= $h($filters['from_date']) ?>"><?php if (isset($errors['from_date'])): ?><p class="field-error"><?= $h($errors['from_date']) ?></p><?php endif; ?></div>
                <div class="form-field"><label for="monitoring-to">Đến ngày</label><input id="monitoring-to" type="date" name="to_date" value="<?= $h($filters['to_date']) ?>"><?php if (isset($errors['to_date'])): ?><p class="field-error"><?= $h($errors['to_date']) ?></p><?php endif; ?></div>
                <div class="form-field">
                    <label for="monitoring-employee">Nhân viên</label>
                    <select id="monitoring-employee" name="employee_id">
                        <option value="">Tất cả nhân viên</option>
                        <?php foreach ($employees as $employee): $id = (int)$employee['MaNV']; ?>
                            <option value="<?= $id ?>" <?= (int)($filters['employee_id'] ?? 0) === $id ? 'selected' : '' ?>>NV<?= str_pad((string)$id, 3, '0', STR_PAD_LEFT) ?> · <?= $h($employee['HoTen']) ?></option>
                        <?php endforeach; ?>
                    </select>
                    <?php if (isset($errors['employee_id'])): ?><p class="field-error"><?= $h($errors['employee_id']) ?></p><?php endif; ?>
                </div>
                <div class="form-field"><label for="monitoring-keyword">Mã hoặc họ tên</label><input id="monitoring-keyword" type="search" name="keyword" maxlength="100" value="<?= $h($filters['keyword']) ?>" placeholder="Tìm mã hoặc họ tên"><?php if (isset($errors['keyword'])): ?><p class="field-error"><?= $h($errors['keyword']) ?></p><?php endif; ?></div>
                <?php if ($activeTab === 'alerts'): ?>
                    <div class="form-field">
                        <label for="monitoring-category">Loại cảnh báo</label>
                        <select id="monitoring-category" name="category">
                            <option value="">Tất cả loại</option>
                            <?php foreach ($categories as $item): $category = (string)$item['LoaiCanhBao']; ?>
                                <option value="<?= $h($category) ?>" <?= $filters['category'] === $category ? 'selected' : '' ?>><?= $h($category) ?></option>
                            <?php endforeach; ?>
                        </select>
                        <?php if (isset($errors['category'])): ?><p class="field-error"><?= $h($errors['category']) ?></p><?php endif; ?>
                    </div>
                <?php endif; ?>
            </div>
            <?php if (isset($errors['date_range'])): ?><p class="field-error" role="alert"><?= $h($errors['date_range']) ?></p><?php endif; ?>
            <div class="workspace-filter-actions">
                <label for="monitoring-page-size">Số dòng<select id="monitoring-page-size" name="per_page"><?php foreach ([5, 10, 20, 50] as $size): ?><option value="<?= $size ?>" <?= $size === $pageSize ? 'selected' : '' ?>><?= $size ?></option><?php endforeach; ?></select></label>
                <button class="button button--primary button--small" type="submit">Lọc</button>
                <a class="text-action" href="/?action=monitoring&amp;tab=<?= $h($activeTab) ?>">Xóa lọc</a>
            </div>
        </form>

        <nav class="workspace-tabs" aria-label="Chọn dữ liệu">
            <a href="<?= $h($healthTabUrl) ?>" <?= $activeTab === 'health' ? 'aria-current="page"' : '' ?>>Sức khỏe <span><?= (int)$totalHealthRows ?></span></a>
            <a href="<?= $h($alertsTabUrl) ?>" <?= $activeTab === 'alerts' ? 'aria-current="page"' : '' ?>>Cảnh báo <span><?= (int)$totalAlertRows ?></span></a>
        </nav>

        <?php if ($activeTab === 'health'): ?>
            <?php if ($chartData === []): ?><div class="empty-state workspace-empty">Chưa có dữ liệu sức khỏe.</div><?php else: ?>
                <div class="health-chart-wrap"><svg id="health-chart" class="health-chart" viewBox="0 0 800 220" role="img" aria-label="Biểu đồ nhịp tim theo thời gian"></svg></div>
                <script type="application/json" id="health-chart-data"><?= $chartJson ?: '[]' ?></script>
            <?php endif; ?>
            <?php if ($healthRows === []): ?><div class="empty-state workspace-empty">Không có dữ liệu sức khỏe phù hợp.</div><?php else: ?>
                <div class="table-scroll"><table class="employee-table data-table">
                    <caption class="visually-hidden">Lịch sử sức khỏe</caption>
                    <thead><tr><th>Mã NV</th><th>Họ tên</th><th>Nhịp tim</th><th>SpO₂</th><th>Thời gian</th></tr></thead>
                    <tbody><?php foreach ($healthRows as $record): $employeeId = (int)$record['MaNV']; ?>
                        <tr><td><span class="employee-code">NV<?= str_pad((string)$employeeId, 3, '0', STR_PAD_LEFT) ?></span></td><td><?= $h($record['HoTen']) ?></td><td><?= $record['NhipTim'] === null ? '--' : $h($record['NhipTim']) . ' bpm' ?></td><td><?= $record['SpO2'] === null ? '--' : $h($record['SpO2']) . ' %' ?></td><td><?= $record['ThoiGian'] === null ? '--' : $h((new DateTimeImmutable((string)$record['ThoiGian']))->format('Y-m-d H:i:s')) ?></td></tr>
                    <?php endforeach; ?></tbody>
                </table></div>
                <?php if ($totalHealthPages > 1): ?><nav class="attendance-pagination" aria-label="Phân trang sức khỏe"><?php if ($healthPage > 1): ?><a class="text-action" href="<?= $h($healthPageUrl($healthPage - 1)) ?>">‹ Trước</a><?php endif; ?><span><?= (int)$healthPage ?> / <?= (int)$totalHealthPages ?></span><?php if ($healthPage < $totalHealthPages): ?><a class="text-action" href="<?= $h($healthPageUrl($healthPage + 1)) ?>">Sau ›</a><?php endif; ?></nav><?php endif; ?>
            <?php endif; ?>
        <?php else: ?>
            <?php if ($alertRows === []): ?><div class="empty-state workspace-empty">Không có cảnh báo phù hợp.</div><?php else: ?>
                <div class="table-scroll"><table class="employee-table data-table">
                    <caption class="visually-hidden">Lịch sử cảnh báo</caption>
                    <thead><tr><th>Thời gian</th><th>Mã NV</th><th>Nhân viên</th><th>Loại</th><th>Nội dung</th></tr></thead>
                    <tbody><?php foreach ($alertRows as $record): $employeeId = (int)$record['MaNV']; ?>
                        <tr><td><?= $record['ThoiGian'] === null ? '--' : $h((new DateTimeImmutable((string)$record['ThoiGian']))->format('Y-m-d H:i:s')) ?></td><td><span class="employee-code">NV<?= str_pad((string)$employeeId, 3, '0', STR_PAD_LEFT) ?></span></td><td><?= $h($record['HoTen']) ?></td><td><?= $h($record['LoaiCanhBao'] ?: 'Cảnh báo AI') ?></td><td><?= $h($record['NoiDung'] ?: '--') ?></td></tr>
                    <?php endforeach; ?></tbody>
                </table></div>
                <?php if ($totalAlertPages > 1): ?><nav class="attendance-pagination" aria-label="Phân trang cảnh báo"><?php if ($alertPage > 1): ?><a class="text-action" href="<?= $h($alertPageUrl($alertPage - 1)) ?>">‹ Trước</a><?php endif; ?><span><?= (int)$alertPage ?> / <?= (int)$totalAlertPages ?></span><?php if ($alertPage < $totalAlertPages): ?><a class="text-action" href="<?= $h($alertPageUrl($alertPage + 1)) ?>">Sau ›</a><?php endif; ?></nav><?php endif; ?>
            <?php endif; ?>
        <?php endif; ?>
    </section>
</main>
<script src="/public/js/health.js" defer></script>
<?php require __DIR__ . '/layout/footer.php'; ?>

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
                <div class="form-field">
                    <label for="monitoring-from">Từ ngày</label>
                    <input id="monitoring-from" type="date" name="from_date" value="<?= $h($filters['from_date']) ?>">
                    <?php if (isset($errors['from_date'])): ?><p class="field-error"><?= $h($errors['from_date']) ?></p><?php endif; ?>
                </div>
                <div class="form-field">
                    <label for="monitoring-to">Đến ngày</label>
                    <input id="monitoring-to" type="date" name="to_date" value="<?= $h($filters['to_date']) ?>">
                    <?php if (isset($errors['to_date'])): ?><p class="field-error"><?= $h($errors['to_date']) ?></p><?php endif; ?>
                </div>
                <div class="form-field">
                    <label for="monitoring-employee">Nhân viên theo dõi</label>
                    <select id="monitoring-employee" name="employee_id" onchange="this.form.submit()">
                        <option value="">-- Tất cả nhân viên (Tổng quan) --</option>
                        <?php foreach ($employees as $employee): $id = (int)$employee['MaNV']; ?>
                            <option value="<?= $id ?>" <?= (int)($filters['employee_id'] ?? 0) === $id ? 'selected' : '' ?>>NV<?= str_pad((string)$id, 3, '0', STR_PAD_LEFT) ?> · <?= $h($employee['HoTen']) ?></option>
                        <?php endforeach; ?>
                    </select>
                    <?php if (isset($errors['employee_id'])): ?><p class="field-error"><?= $h($errors['employee_id']) ?></p><?php endif; ?>
                </div>
                <div class="form-field">
                    <label for="monitoring-keyword">Mã hoặc họ tên</label>
                    <input id="monitoring-keyword" type="search" name="keyword" maxlength="100" value="<?= $h($filters['keyword']) ?>" placeholder="Tìm mã hoặc họ tên">
                    <?php if (isset($errors['keyword'])): ?><p class="field-error"><?= $h($errors['keyword']) ?></p><?php endif; ?>
                </div>
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
                <label for="monitoring-page-size">Số dòng
                    <select id="monitoring-page-size" name="per_page" onchange="this.form.submit()">
                        <?php foreach ([5, 10, 20, 50] as $size): ?>
                            <option value="<?= $size ?>" <?= $size === $pageSize ? 'selected' : '' ?>><?= $size ?></option>
                        <?php endforeach; ?>
                    </select>
                </label>
                <button class="button button--primary button--small" type="submit">Lọc</button>
                <a class="text-action" href="/?action=monitoring&amp;tab=<?= $h($activeTab) ?>">Xóa lọc</a>
            </div>
        </form>

        <nav class="workspace-tabs" aria-label="Chọn dữ liệu">
            <a href="<?= $h($healthTabUrl) ?>" <?= $activeTab === 'health' ? 'aria-current="page"' : '' ?>>
                Sức khỏe <?= $isEmployeeSelected ? 'cá nhân' : 'tổng quan' ?> <span><?= (int)$totalHealthRows ?></span>
            </a>
            <a href="<?= $h($alertsTabUrl) ?>" <?= $activeTab === 'alerts' ? 'aria-current="page"' : '' ?>>
                Cảnh báo <span><?= (int)$totalAlertRows ?></span>
            </a>
        </nav>

        <?php if ($activeTab === 'health'): ?>
            <?php if ($isEmployeeSelected && $selectedEmployeeSummary !== null): ?>
                <!-- ================== CHẾ ĐỘ 1: XEM CHI TIẾT 1 NHÂN VIÊN ================== -->
                <div class="health-profile-card">
                    <div class="health-profile-top">
                        <div class="health-profile-identity">
                            <span class="employee-code">NV<?= str_pad((string)$selectedEmployeeSummary['MaNV'], 3, '0', STR_PAD_LEFT) ?></span>
                            <h3 class="health-profile-name"><?= $h($selectedEmployeeSummary['HoTen']) ?></h3>
                            <?php
                            $st = (string)($selectedEmployeeSummary['LatestTheTrang'] ?? '');
                            if ($st === 'Kiệt sức') {
                                echo '<span class="status-pill status-pill--danger">🔴 Kiệt sức</span>';
                            } elseif ($st === 'Mệt mỏi') {
                                echo '<span class="status-pill status-pill--warning">🟡 Mệt mỏi</span>';
                            } elseif ($st === 'Bình thường') {
                                echo '<span class="status-pill status-pill--success">🟢 Bình thường</span>';
                            } else {
                                echo '<span class="evidence-empty">Chưa có dữ liệu</span>';
                            }
                            ?>
                        </div>
                        <div>
                            <a class="button button--secondary button--small" href="/?action=monitoring&amp;tab=health">✕ Xem tất cả nhân viên</a>
                        </div>
                    </div>
                    <div class="health-profile-stats">
                        <div class="health-stat-box">
                            <span class="stat-label">Nhịp tim gần nhất</span>
                            <div class="stat-main">
                                <span class="stat-number"><?= $selectedEmployeeSummary['LatestNhipTim'] !== null ? $h($selectedEmployeeSummary['LatestNhipTim']) : '--' ?></span>
                                <span class="stat-unit">bpm</span>
                            </div>
                            <span class="stat-sub">Trung bình: <?= $selectedEmployeeSummary['AvgNhipTim'] ?: '--' ?> bpm (<?= $selectedEmployeeSummary['MinNhipTim'] ?: '--' ?> - <?= $selectedEmployeeSummary['MaxNhipTim'] ?: '--' ?>)</span>
                        </div>
                        <div class="health-stat-box">
                            <span class="stat-label">SpO₂ gần nhất</span>
                            <div class="stat-main">
                                <span class="stat-number"><?= $selectedEmployeeSummary['LatestSpO2'] !== null ? $h($selectedEmployeeSummary['LatestSpO2']) : '--' ?></span>
                                <span class="stat-unit">%</span>
                            </div>
                            <span class="stat-sub">Trung bình: <?= $selectedEmployeeSummary['AvgSpO2'] ?: '--' ?> %</span>
                        </div>
                        <div class="health-stat-box">
                            <span class="stat-label">Tổng lượt đo sức khỏe</span>
                            <div class="stat-main">
                                <span class="stat-number"><?= (int)$selectedEmployeeSummary['TotalRecords'] ?></span>
                                <span class="stat-unit">lần</span>
                            </div>
                            <span class="stat-sub">
                                <?php if ((int)$selectedEmployeeSummary['AlertRecords'] > 0): ?>
                                    <strong style="color:var(--red);"><?= (int)$selectedEmployeeSummary['AlertRecords'] ?> lần có dấu hiệu mệt mỏi/kiệt sức</strong>
                                <?php else: ?>
                                    <strong style="color:var(--green);">Tất cả các lần đo bình thường</strong>
                                <?php endif; ?>
                            </span>
                        </div>
                        <div class="health-stat-box">
                            <span class="stat-label">Thời điểm đo cuối</span>
                            <div class="stat-main">
                                <span class="stat-date"><?= $selectedEmployeeSummary['LatestThoiGian'] ? $h((new DateTimeImmutable((string)$selectedEmployeeSummary['LatestThoiGian']))->format('H:i:s d/m/Y')) : '--' ?></span>
                            </div>
                            <span class="stat-sub">Ghi nhận từ thiết bị chấm công</span>
                        </div>
                    </div>
                </div>

                <!-- Biểu đồ diễn biến sức khỏe cá nhân -->
                <div class="health-chart-panel">
                    <div class="health-chart-panel-header">
                        <div>
                            <h4 class="health-panel-title">Biểu đồ biến thiên Nhịp tim &amp; SpO₂ theo dòng thời gian</h4>
                            <p class="health-panel-sub">Theo dõi dữ liệu đo của nhân viên <strong><?= $h($selectedEmployeeSummary['HoTen']) ?></strong></p>
                        </div>
                        <div class="health-chart-legend">
                            <span class="legend-badge"><span class="legend-line legend-line--hr"></span> Nhịp tim (bpm)</span>
                            <span class="legend-badge"><span class="legend-line legend-line--spo2"></span> SpO₂ (%)</span>
                            <span class="legend-badge"><span class="legend-point legend-point--normal"></span> Bình thường</span>
                            <span class="legend-badge"><span class="legend-point legend-point--tired"></span> Mệt mỏi</span>
                            <span class="legend-badge"><span class="legend-point legend-point--exhausted"></span> Kiệt sức</span>
                        </div>
                    </div>
                    <?php if ($chartData === []): ?>
                        <div class="empty-state workspace-empty">Chưa có dữ liệu đo để vẽ biểu đồ.</div>
                    <?php else: ?>
                        <div class="health-chart-wrap">
                            <svg id="health-chart" class="health-chart" viewBox="0 0 840 240" role="img" aria-label="Biểu đồ nhịp tim và SpO2 theo thời gian"></svg>
                            <div id="chart-tooltip" class="health-chart-tooltip" style="display:none;"></div>
                        </div>
                        <script type="application/json" id="health-chart-data"><?= $chartJson ?: '[]' ?></script>
                    <?php endif; ?>
                </div>

                <!-- Bảng lịch sử của riêng nhân viên được chọn -->
                <div class="health-table-panel">
                    <div class="health-table-panel-header">
                        <h4 class="health-panel-title">Lịch sử đo chi tiết của nhân viên (<?= (int)$totalHealthRows ?> lượt ghi)</h4>
                    </div>
                    <?php if ($healthRows === []): ?>
                        <div class="empty-state workspace-empty">Không có dữ liệu đo trong khoảng thời gian đã chọn.</div>
                    <?php else: ?>
                        <div class="table-scroll"><table class="employee-table data-table">
                            <caption class="visually-hidden">Lịch sử sức khỏe chi tiết</caption>
                            <thead>
                                <tr>
                                    <th>STT</th>
                                    <th>Thời gian</th>
                                    <th>Nhịp tim</th>
                                    <th>SpO₂</th>
                                    <th>Thể trạng (AI)</th>
                                    <th>Đánh giá trạng thái</th>
                                </tr>
                            </thead>
                            <tbody>
                                <?php $idx = ($healthPage - 1) * $pageSize + 1; foreach ($healthRows as $record): ?>
                                    <tr>
                                        <td><?= $idx++ ?></td>
                                        <td><strong><?= $record['ThoiGian'] === null ? '--' : $h((new DateTimeImmutable((string)$record['ThoiGian']))->format('Y-m-d H:i:s')) ?></strong></td>
                                        <td>
                                            <span class="metric-value-box <?= (int)($record['NhipTim'] ?? 0) > 100 || (int)($record['NhipTim'] ?? 0) < 60 ? 'metric-alert' : '' ?>">
                                                <?= $record['NhipTim'] === null ? '--' : $h($record['NhipTim']) . ' bpm' ?>
                                            </span>
                                        </td>
                                        <td>
                                            <span class="metric-value-box <?= (float)($record['SpO2'] ?? 100) < 95 ? 'metric-alert' : '' ?>">
                                                <?= $record['SpO2'] === null ? '--' : $h($record['SpO2']) . ' %' ?>
                                            </span>
                                        </td>
                                        <td>
                                            <?php
                                            $tt = (string)($record['TheTrang'] ?? '');
                                            if ($tt === 'Kiệt sức') {
                                                echo '<span class="status-pill status-pill--danger">🔴 Kiệt sức</span>';
                                            } elseif ($tt === 'Mệt mỏi') {
                                                echo '<span class="status-pill status-pill--warning">🟡 Mệt mỏi</span>';
                                            } elseif ($tt === 'Bình thường') {
                                                echo '<span class="status-pill status-pill--success">🟢 Bình thường</span>';
                                            } else {
                                                echo '<span class="evidence-empty">--</span>';
                                            }
                                            ?>
                                        </td>
                                        <td>
                                            <?php
                                            if ($tt === 'Kiệt sức') {
                                                echo '<span class="text-danger">Nhịp tim/SpO2 bất thường, biểu hiện kiệt sức nghiêm trọng</span>';
                                            } elseif ($tt === 'Mệt mỏi') {
                                                echo '<span class="text-warning">Mắt nhắm dài/ngáp hoặc chỉ số cận mức cảnh báo</span>';
                                            } else {
                                                echo '<span class="text-success">Chỉ số sinh hiệu ổn định</span>';
                                            }
                                            ?>
                                        </td>
                                    </tr>
                                <?php endforeach; ?>
                            </tbody>
                        </table></div>
                        <?php if ($totalHealthPages > 1): ?>
                            <nav class="attendance-pagination" aria-label="Phân trang sức khỏe">
                                <?php if ($healthPage > 1): ?><a class="text-action" href="<?= $h($healthPageUrl($healthPage - 1)) ?>">‹ Trước</a><?php endif; ?>
                                <span><?= (int)$healthPage ?> / <?= (int)$totalHealthPages ?></span>
                                <?php if ($healthPage < $totalHealthPages): ?><a class="text-action" href="<?= $h($healthPageUrl($healthPage + 1)) ?>">Sau ›</a><?php endif; ?>
                            </nav>
                        <?php endif; ?>
                    <?php endif; ?>
                </div>

            <?php else: ?>
                <!-- ================== CHẾ ĐỘ 2: TỔNG QUAN TẤT CẢ NHÂN VIÊN ================== -->
                <!-- Strip thống kê sức khỏe toàn thể -->
                <div class="workspace-kpi-strip health-overview-kpi">
                    <div>
                        <span>Tổng nhân sự theo dõi</span>
                        <strong><?= (int)($overallStats['total_employees'] ?? 0) ?></strong>
                    </div>
                    <div>
                        <span>🟢 Thể trạng bình thường</span>
                        <strong style="color:var(--green);"><?= (int)($overallStats['count_normal'] ?? 0) ?></strong>
                    </div>
                    <div>
                        <span>🟡 Cần chú ý (Mệt mỏi)</span>
                        <strong style="color:var(--amber);"><?= (int)($overallStats['count_tired'] ?? 0) ?></strong>
                    </div>
                    <div>
                        <span>🔴 Cảnh báo (Kiệt sức)</span>
                        <strong style="color:var(--red);"><?= (int)($overallStats['count_exhausted'] ?? 0) ?></strong>
                    </div>
                </div>

                <div class="health-guidance-card">
                    <div class="guidance-icon">💡</div>
                    <div class="guidance-content">
                        <strong>Theo dõi sức khỏe cá nhân hóa:</strong>
                        <p>Để đảm bảo tính liên tục và độ tin cậy y tế, biểu đồ chuỗi thời gian chỉ hiển thị khi bạn chọn một nhân viên cụ thể. Vui lòng bấm <strong>[📈 Xem biểu đồ &amp; Chi tiết]</strong> ở danh sách bên dưới hoặc chọn nhân viên từ bộ lọc phía trên.</p>
                    </div>
                </div>

                <div class="health-table-panel">
                    <div class="health-table-panel-header">
                        <h4 class="health-panel-title">Tình trạng sức khỏe mới nhất theo từng nhân viên (<?= (int)$totalHealthRows ?> nhân sự)</h4>
                    </div>
                    <?php if ($overviewRows === []): ?>
                        <div class="empty-state workspace-empty">Không có nhân viên nào có dữ liệu sức khỏe phù hợp với bộ lọc.</div>
                    <?php else: ?>
                        <div class="table-scroll"><table class="employee-table data-table">
                            <caption class="visually-hidden">Tình trạng sức khỏe nhân viên</caption>
                            <thead>
                                <tr>
                                    <th>Mã NV</th>
                                    <th>Họ và tên</th>
                                    <th>Thể trạng gần nhất</th>
                                    <th>Nhịp tim gần nhất</th>
                                    <th>SpO₂ gần nhất</th>
                                    <th>Lần đo cuối</th>
                                    <th>Tổng lượt đo</th>
                                    <th style="text-align:right;">Hành động</th>
                                </tr>
                            </thead>
                            <tbody>
                                <?php foreach ($overviewRows as $row): $id = (int)$row['MaNV']; ?>
                                    <tr>
                                        <td><span class="employee-code">NV<?= str_pad((string)$id, 3, '0', STR_PAD_LEFT) ?></span></td>
                                        <td>
                                            <a class="employee-link" href="/?action=monitoring&amp;employee_id=<?= $id ?>&amp;tab=health">
                                                <strong><?= $h($row['HoTen']) ?></strong>
                                            </a>
                                        </td>
                                        <td>
                                            <?php
                                            $st = (string)($row['TheTrang'] ?? '');
                                            if ($st === 'Kiệt sức') {
                                                echo '<span class="status-pill status-pill--danger">🔴 Kiệt sức</span>';
                                            } elseif ($st === 'Mệt mỏi') {
                                                echo '<span class="status-pill status-pill--warning">🟡 Mệt mỏi</span>';
                                            } elseif ($st === 'Bình thường') {
                                                echo '<span class="status-pill status-pill--success">🟢 Bình thường</span>';
                                            } else {
                                                echo '<span class="evidence-empty">--</span>';
                                            }
                                            ?>
                                        </td>
                                        <td><?= $row['NhipTim'] !== null ? $h($row['NhipTim']) . ' bpm' : '--' ?></td>
                                        <td><?= $row['SpO2'] !== null ? $h($row['SpO2']) . ' %' : '--' ?></td>
                                        <td><?= $row['ThoiGian'] ? $h((new DateTimeImmutable((string)$row['ThoiGian']))->format('Y-m-d H:i:s')) : '--' ?></td>
                                        <td><span class="badge-count"><?= (int)$row['TongSoLanDo'] ?> lần đo</span></td>
                                        <td style="text-align:right;">
                                            <a class="button button--secondary button--small" href="/?action=monitoring&amp;employee_id=<?= $id ?>&amp;tab=health">
                                                📈 Xem biểu đồ &amp; Chi tiết
                                            </a>
                                        </td>
                                    </tr>
                                <?php endforeach; ?>
                            </tbody>
                        </table></div>
                        <?php if ($totalHealthPages > 1): ?>
                            <nav class="attendance-pagination" aria-label="Phân trang sức khỏe">
                                <?php if ($healthPage > 1): ?><a class="text-action" href="<?= $h($healthPageUrl($healthPage - 1)) ?>">‹ Trước</a><?php endif; ?>
                                <span><?= (int)$healthPage ?> / <?= (int)$totalHealthPages ?></span>
                                <?php if ($healthPage < $totalHealthPages): ?><a class="text-action" href="<?= $h($healthPageUrl($healthPage + 1)) ?>">Sau ›</a><?php endif; ?>
                            </nav>
                        <?php endif; ?>
                    <?php endif; ?>
                </div>
            <?php endif; ?>

        <?php else: ?>
            <!-- ================== TAB CẢNH BÁO ================== -->
            <?php if ($alertRows === []): ?>
                <div class="empty-state workspace-empty">Không có cảnh báo phù hợp với bộ lọc hiện tại.</div>
            <?php else: ?>
                <div class="table-scroll"><table class="employee-table data-table">
                    <caption class="visually-hidden">Lịch sử cảnh báo</caption>
                    <thead>
                        <tr>
                            <th>Thời gian</th>
                            <th>Mã NV</th>
                            <th>Nhân viên</th>
                            <th>Loại cảnh báo</th>
                            <th>Nội dung chi tiết</th>
                            <th style="text-align:right;">Chi tiết</th>
                        </tr>
                    </thead>
                    <tbody>
                        <?php foreach ($alertRows as $record): $employeeId = (int)$record['MaNV']; ?>
                            <tr>
                                <td><?= $record['ThoiGian'] === null ? '--' : $h((new DateTimeImmutable((string)$record['ThoiGian']))->format('Y-m-d H:i:s')) ?></td>
                                <td><span class="employee-code">NV<?= str_pad((string)$employeeId, 3, '0', STR_PAD_LEFT) ?></span></td>
                                <td><?= $h($record['HoTen']) ?></td>
                                <td>
                                    <span class="status-pill status-pill--danger">
                                        <?= $h($record['LoaiCanhBao'] ?: 'Cảnh báo AI') ?>
                                    </span>
                                </td>
                                <td><?= $h($record['NoiDung'] ?: '--') ?></td>
                                <td style="text-align:right;">
                                    <a class="text-action" href="/?action=monitoring&amp;employee_id=<?= $employeeId ?>&amp;tab=health">
                                        Xem sức khỏe ›
                                    </a>
                                </td>
                            </tr>
                        <?php endforeach; ?>
                    </tbody>
                </table></div>
                <?php if ($totalAlertPages > 1): ?>
                    <nav class="attendance-pagination" aria-label="Phân trang cảnh báo">
                        <?php if ($alertPage > 1): ?><a class="text-action" href="<?= $h($alertPageUrl($alertPage - 1)) ?>">‹ Trước</a><?php endif; ?>
                        <span><?= (int)$alertPage ?> / <?= (int)$totalAlertPages ?></span>
                        <?php if ($alertPage < $totalAlertPages): ?><a class="text-action" href="<?= $h($alertPageUrl($alertPage + 1)) ?>">Sau ›</a><?php endif; ?>
                    </nav>
                <?php endif; ?>
            <?php endif; ?>
        <?php endif; ?>
    </section>
</main>
<script src="/public/js/health.js" defer></script>
<?php require __DIR__ . '/layout/footer.php'; ?>

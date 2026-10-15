<?php
require __DIR__ . '/layout/header.php';
$h = static fn(mixed $value): string => htmlspecialchars((string)($value ?? ''), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
$summary = $dashboard['summary'];
$attendance = $dashboard['attendance'];
$weekly = $dashboard['weekly'];
$alerts = $dashboard['alerts'];
$dateLabel = (new DateTimeImmutable($dashboard['date']))->format('d/m/Y');
$weeklyMax = 1;
foreach ($weekly as $day) {
    $weeklyMax = max($weeklyMax, (int)$day['check_in'], (int)$day['check_out']);
}
?>
<main class="page-container dashboard-page">
    <?php if ($error !== null): ?><div class="notice notice--error" role="alert"><?= $h($error) ?></div><?php endif; ?>
    <section class="workspace dashboard-workspace" aria-label="Tổng quan chấm công">
        <div class="workspace-date"><time datetime="<?= $h($dashboard['date']) ?>"><?= $h($dateLabel) ?></time></div>
        <div class="workspace-kpi-strip" aria-label="Chỉ số nhân sự hôm nay">
            <div><span>Tổng nhân viên</span><strong><?= (int)$summary['total_employees'] ?></strong></div>
            <div><span>Có phân ca</span><strong><?= (int)$summary['assigned_today'] ?></strong></div>
            <div><span>Đã chấm công</span><strong><?= (int)$summary['checked_in'] ?></strong></div>
            <div><span>Khuôn mặt</span><strong><?= (int)$summary['face_registered'] ?>/<?= (int)$summary['total_employees'] ?></strong></div>
        </div>
        <div class="workspace-status-strip" aria-label="Trạng thái chấm công">
            <div><span>Đang làm</span><strong><?= (int)$summary['working'] ?></strong></div>
            <div><span>Đi trễ</span><strong><?= (int)$summary['late'] ?></strong></div>
            <div><span>Về sớm</span><strong><?= (int)$summary['early'] ?></strong></div>
            <div><span>Chưa chấm</span><strong><?= (int)$summary['not_checked'] ?></strong></div>
        </div>

        <section class="workspace-section" aria-labelledby="today-attendance-title">
            <div class="workspace-section-heading"><h2 id="today-attendance-title">Chấm công hôm nay</h2></div>
            <div class="table-scroll"><table class="employee-table data-table dashboard-attendance-table">
                <caption class="visually-hidden">Chấm công nhân viên ngày <?= $h($dateLabel) ?></caption>
                <thead><tr><th>Mã NV</th><th>Họ tên</th><th>Ca</th><th>Giờ vào</th><th>Giờ ra</th><th>Trạng thái vào</th><th>Trạng thái ra</th></tr></thead>
                <tbody><?php if ($attendance === []): ?><tr><td colspan="7"><div class="empty-state">Chưa có nhân viên để hiển thị.</div></td></tr><?php else: foreach ($attendance as $row): $employeeId = (int)$row['MaNV']; ?>
                    <tr>
                        <td><span class="employee-code">NV<?= str_pad((string)$employeeId, 3, '0', STR_PAD_LEFT) ?></span></td>
                        <td><?= $h($row['HoTen']) ?></td>
                        <td><?= $h($row['TenCaDisplay']) ?><?php if ($row['ThoiGianCa'] !== '--'): ?><small class="dashboard-table-subtext"><?= $h($row['ThoiGianCa']) ?></small><?php endif; ?></td>
                        <td class="dashboard-time"><?= $h($row['GioVaoDisplay']) ?></td><td class="dashboard-time"><?= $h($row['GioRaDisplay']) ?></td>
                        <td><span class="dashboard-badge"><?= $h($row['TrangThaiVao']) ?></span></td><td><span class="dashboard-badge"><?= $h($row['TrangThaiRa']) ?></span></td>
                    </tr>
                <?php endforeach; endif; ?></tbody>
            </table></div>
        </section>

        <div class="workspace-bottom-grid">
            <section class="workspace-section" aria-labelledby="weekly-title">
                <div class="workspace-section-heading"><h2 id="weekly-title">Hoạt động 7 ngày</h2></div>
                <div class="dashboard-chart-body">
                    <div class="dashboard-weekly-chart" role="img" aria-label="Biểu đồ lượt vào và ra trong 7 ngày gần nhất">
                        <?php foreach ($weekly as $day): ?>
                            <?php $inHeight = max(3, (int)round((int)$day['check_in'] / $weeklyMax * 100)); $outHeight = max(3, (int)round((int)$day['check_out'] / $weeklyMax * 100)); ?>
                            <div class="dashboard-weekly-day"><div class="dashboard-weekly-bars"><span class="dashboard-weekly-bar dashboard-weekly-bar--in" style="height: <?= $inHeight ?>%" title="Người vào: <?= (int)$day['check_in'] ?>"></span><span class="dashboard-weekly-bar dashboard-weekly-bar--out" style="height: <?= $outHeight ?>%" title="Người ra: <?= (int)$day['check_out'] ?>"></span></div><span class="dashboard-weekly-label"><?= $h($day['label']) ?></span><small><?= $h(substr($day['date'], 5)) ?></small></div>
                        <?php endforeach; ?>
                    </div>
                    <div class="dashboard-weekly-legend"><span><i class="dashboard-weekly-bar--in"></i>Người vào</span><span><i class="dashboard-weekly-bar--out"></i>Người ra</span></div>
                </div>
            </section>
            <section class="workspace-section" aria-labelledby="recent-alerts-title">
                <div class="workspace-section-heading"><h2 id="recent-alerts-title">Cảnh báo gần đây</h2><a class="text-action" href="/?action=monitoring&amp;tab=alerts">Xem tất cả</a></div>
                <?php if ($alerts === []): ?><p class="dashboard-alert-empty">Chưa có cảnh báo gần đây.</p><?php else: ?><ul class="dashboard-alert-list"><?php foreach ($alerts as $alert): $alertTime = (new DateTimeImmutable($alert['ThoiGian']))->format('d/m H:i'); ?><li><div class="dashboard-alert-main"><strong><?= $h($alert['HoTen'] ?? 'Không rõ nhân viên') ?></strong><span><?= $h($alert['LoaiCanhBao'] ?? 'Cảnh báo') ?></span></div><time datetime="<?= $h($alert['ThoiGian']) ?>"><?= $h($alertTime) ?></time></li><?php endforeach; ?></ul><?php endif; ?>
            </section>
        </div>
    </section>
</main>
<?php require __DIR__ . '/layout/footer.php'; ?>

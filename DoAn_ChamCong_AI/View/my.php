<?php require __DIR__ . '/layout/header.php'; ?>
<?php
$h = static fn(mixed $value): string => htmlspecialchars((string)($value ?? ''), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
$profile = $profile ?? [];
$historyQuery = ['action' => 'my', 'tab' => 'history', 'from_date' => $fromDate, 'to_date' => $toDate];
$pageUrl = static fn(int $targetPage): string => '/?' . http_build_query($historyQuery + ['page' => $targetPage]);
$checkIn = $today['attendance']['GioVao'] ?? null;
$checkOut = $today['attendance']['GioRa'] ?? null;
$myEmployeeId = (int)($profile['MaNV'] ?? 0);
$myEmployeeCode = 'NV' . str_pad((string)$myEmployeeId, 3, '0', STR_PAD_LEFT);
?>
<main class="page-container my-page">
    <?php if ($error !== null): ?><div class="notice notice--error" role="alert"><?= $h($error) ?></div><?php endif; ?>
    <section class="workspace" aria-label="Trang cá nhân">
        <nav class="workspace-tabs" aria-label="Trang cá nhân">
            <a href="/?action=my&amp;tab=today" <?= $activeTab === 'today' ? 'aria-current="page"' : '' ?>>Hôm nay</a>
            <a href="/?action=my&amp;tab=history" <?= $activeTab === 'history' ? 'aria-current="page"' : '' ?>>Lịch sử</a>
            <a href="/?action=my&amp;tab=monitoring" <?= $activeTab === 'monitoring' ? 'aria-current="page"' : '' ?>>Sức khỏe &amp; Cảnh báo</a>
        </nav>

        <?php if ($activeTab === 'today'): ?>
            <div class="my-identity"><strong><?= $h($myEmployeeCode) ?></strong><span><?= $h($profile['HoTen'] ?? '') ?></span><span><?= $h($profile['TenVaiTro'] ?? '') ?></span></div>
            <div class="my-today-grid">
                <div><span>Ca</span><strong><?= $h($today['shift']['TenCa'] ?? 'Chưa được phân ca hôm nay') ?></strong><?php if ($today['shift'] !== null): ?><small><?= $h(substr((string)$today['shift']['GioBatDau'], 0, 5)) ?>–<?= $h(substr((string)$today['shift']['GioKetThuc'], 0, 5)) ?></small><?php endif; ?></div>
                <div><span>Giờ vào</span><strong><?= $checkIn ? $h((new DateTimeImmutable((string)$checkIn))->format('H:i:s')) : '--' ?></strong><small><?= $h($today['statuses']['entry']) ?></small></div>
                <div><span>Giờ ra</span><strong><?= $checkOut ? $h((new DateTimeImmutable((string)$checkOut))->format('H:i:s')) : '--' ?></strong><small><?= $h($today['statuses']['exit']) ?></small></div>
                <div><span>Trạng thái</span><strong><?= $h($today['summary']) ?></strong></div>
            </div>
            <?php if ($today['attendance'] !== null): ?>
                <div class="my-today-evidence" aria-label="Ảnh chấm công hôm nay">
                    <div><span>Ảnh vào</span>
                        <?php
                        $evidenceAttendanceId = (int)$today['attendance']['MaCC'];
                        $evidenceAction = '/?action=my_attendance_image_in';
                        $evidenceKind = 'Ảnh vào';
                        $evidencePerson = (string)($profile['HoTen'] ?? '');
                        $evidenceCode = $myEmployeeCode;
                        $evidenceTime = $checkIn ? (new DateTimeImmutable((string)$checkIn))->format('d/m/Y H:i:s') : '';
                        if ((int)$today['attendance']['HasImageIn'] === 1) {
                            require __DIR__ . '/partials/evidence_thumbnail.php';
                        } else { echo '<span class="evidence-empty">--</span>'; }
                        ?>
                    </div>
                    <div><span>Ảnh ra</span>
                        <?php
                        $evidenceAction = '/?action=my_attendance_image_out';
                        $evidenceKind = 'Ảnh ra';
                        $evidenceTime = $checkOut ? (new DateTimeImmutable((string)$checkOut))->format('d/m/Y H:i:s') : '';
                        if ((int)$today['attendance']['HasImageOut'] === 1) {
                            require __DIR__ . '/partials/evidence_thumbnail.php';
                        } else { echo '<span class="evidence-empty">--</span>'; }
                        ?>
                    </div>
                </div>
            <?php endif; ?>
        <?php elseif ($activeTab === 'history'): ?>
            <form class="workspace-filters my-date-filter" method="get" action="/">
                <input type="hidden" name="action" value="my"><input type="hidden" name="tab" value="history">
                <label for="my-from-date">Từ ngày<input id="my-from-date" type="date" name="from_date" value="<?= $h($fromDate) ?>"></label>
                <label for="my-to-date">Đến ngày<input id="my-to-date" type="date" name="to_date" value="<?= $h($toDate) ?>"></label>
                <button class="button button--primary button--small" type="submit">Lọc</button>
                <a class="text-action" href="/?action=my&amp;tab=history">Xóa lọc</a>
            </form>
            <?php if ($errors !== []): ?><div class="my-validation-errors" role="alert"><?php foreach ($errors as $message): ?><p><?= $h($message) ?></p><?php endforeach; ?></div><?php endif; ?>
            <div class="table-scroll"><table class="employee-table data-table my-history-table">
                <caption class="visually-hidden">Lịch sử chấm công cá nhân</caption>
                <thead><tr><th>Ngày</th><th>Ca</th><th>Giờ vào</th><th>Ảnh vào</th><th>Giờ ra</th><th>Ảnh ra</th><th>Trạng thái vào</th><th>Trạng thái ra</th></tr></thead>
                <tbody><?php if ($attendanceRows === []): ?><tr><td colspan="8"><div class="empty-state">Chưa có lịch sử chấm công phù hợp.</div></td></tr><?php else: foreach ($attendanceRows as $row): ?>
                    <tr>
                        <td><?= $row['GioVao'] ? $h((new DateTimeImmutable((string)$row['GioVao']))->format('Y-m-d')) : '--' ?></td>
                        <td><?= $h($row['TenCa'] ?? '--') ?></td>
                        <td><?= $row['GioVao'] ? $h((new DateTimeImmutable((string)$row['GioVao']))->format('H:i:s')) : '--' ?></td>
                        <td class="evidence-cell"><?php
                            $evidenceAttendanceId = (int)$row['MaCC']; $evidenceAction = '/?action=my_attendance_image_in'; $evidenceKind = 'Ảnh vào';
                            $evidencePerson = (string)($profile['HoTen'] ?? ''); $evidenceCode = $myEmployeeCode;
                            $evidenceTime = !empty($row['GioVao']) ? (new DateTimeImmutable((string)$row['GioVao']))->format('d/m/Y H:i:s') : '';
                            if ((int)$row['HasImageIn'] === 1) require __DIR__ . '/partials/evidence_thumbnail.php'; else echo '<span class="evidence-empty">--</span>';
                        ?></td>
                        <td><?= $row['GioRa'] ? $h((new DateTimeImmutable((string)$row['GioRa']))->format('H:i:s')) : '--' ?></td>
                        <td class="evidence-cell"><?php
                            $evidenceAction = '/?action=my_attendance_image_out'; $evidenceKind = 'Ảnh ra';
                            $evidenceTime = !empty($row['GioRa']) ? (new DateTimeImmutable((string)$row['GioRa']))->format('d/m/Y H:i:s') : '';
                            if ((int)$row['HasImageOut'] === 1) require __DIR__ . '/partials/evidence_thumbnail.php'; else echo '<span class="evidence-empty">--</span>';
                        ?></td>
                        <td><?= $h($row['Statuses']['entry']) ?></td><td><?= $h($row['Statuses']['exit']) ?></td>
                    </tr>
                <?php endforeach; endif; ?></tbody>
            </table></div>
            <?php if ($totalPages > 1): ?><nav class="attendance-pagination" aria-label="Phân trang lịch sử cá nhân"><?php if ($page > 1): ?><a class="text-action" href="<?= $h($pageUrl($page - 1)) ?>">‹ Trước</a><?php endif; ?><span><?= (int)$page ?> / <?= (int)$totalPages ?></span><?php if ($page < $totalPages): ?><a class="text-action" href="<?= $h($pageUrl($page + 1)) ?>">Sau ›</a><?php endif; ?></nav><?php endif; ?>
        <?php else: ?>
            <div class="my-history-block">
                <div class="table-scroll"><table class="employee-table data-table">
                    <caption class="visually-hidden">Lịch sử sức khỏe cá nhân</caption>
                    <thead><tr><th>Nhịp tim</th><th>SpO₂</th><th>Thời gian</th></tr></thead>
                    <tbody><?php if ($healthRows === []): ?><tr><td colspan="3"><div class="empty-state">Chưa có dữ liệu sức khỏe.</div></td></tr><?php else: foreach ($healthRows as $row): ?><tr><td><?= $row['NhipTim'] === null ? '--' : $h($row['NhipTim']) . ' bpm' ?></td><td><?= $row['SpO2'] === null ? '--' : $h($row['SpO2']) . '%' ?></td><td><?= $h($row['ThoiGian']) ?></td></tr><?php endforeach; endif; ?></tbody>
                </table></div>
            </div>
            <div class="my-history-block">
                <div class="table-scroll"><table class="employee-table data-table">
                    <caption class="visually-hidden">Cảnh báo cá nhân</caption>
                    <thead><tr><th>Loại</th><th>Nội dung</th><th>Thời gian</th></tr></thead>
                    <tbody><?php if ($alertRows === []): ?><tr><td colspan="3"><div class="empty-state">Không có cảnh báo.</div></td></tr><?php else: foreach ($alertRows as $row): ?><tr><td><?= $h($row['LoaiCanhBao'] ?: 'Cảnh báo AI') ?></td><td><?= $h($row['NoiDung'] ?? '') ?></td><td><?= $h($row['ThoiGian'] ?? '--') ?></td></tr><?php endforeach; endif; ?></tbody>
                </table></div>
            </div>
        <?php endif; ?>
    </section>
</main>
<?php require __DIR__ . '/partials/evidence_lightbox.php'; ?>
<script src="/public/js/evidence_lightbox.js" defer></script>
<?php require __DIR__ . '/layout/footer.php'; ?>

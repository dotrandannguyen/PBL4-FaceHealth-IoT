<?php require __DIR__ . '/layout/header.php'; ?>
<?php $shiftTab = $activeTab ?? 'assignments'; ?>
<main class="page-container">
    <section class="workspace shift-workspace" aria-label="Phân ca và ca làm việc">
        <nav class="workspace-tabs" aria-label="Chọn chức năng ca làm việc">
            <a href="/?action=shifts&amp;tab=assignments&amp;date=<?= rawurlencode($selectedDate) ?>" <?= $shiftTab === 'assignments' ? 'aria-current="page"' : '' ?>>Phân ca nhân viên</a>
            <a href="/?action=shifts&amp;tab=shifts&amp;date=<?= rawurlencode($selectedDate) ?>" <?= $shiftTab === 'shifts' ? 'aria-current="page"' : '' ?>>Ca làm việc</a>
        </nav>

    <?php if ($successMessage !== null): ?>
        <div class="notice notice--success" role="status"><?= htmlspecialchars((string)$successMessage, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></div>
    <?php endif; ?>
    <?php if ($error !== null): ?>
        <div class="notice notice--error" role="alert"><?= htmlspecialchars($error, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></div>
    <?php endif; ?>

    <?php if ($shiftTab === 'assignments'): ?>
    <section class="workspace-section shift-assignment-form" aria-label="Phân ca nhân viên">
        <form class="employee-form" method="post" action="/?action=assign_shift">
            <input type="hidden" name="_csrf_token" value="<?= htmlspecialchars($csrfToken, ENT_QUOTES, 'UTF-8') ?>">
            <input type="hidden" name="return_tab" value="assignments">
            <?php if ($editingAssignmentId !== null): ?><input type="hidden" name="MaPhanCa" value="<?= (int)$editingAssignmentId ?>"><?php endif; ?>
            <input type="hidden" name="NgayLamViec" value="<?= htmlspecialchars((string)($formValues['NgayLamViec'] ?? $selectedDate), ENT_QUOTES, 'UTF-8') ?>">
            <div class="filter-grid">
                <div class="form-field">
                    <label for="shift-employee">Nhân viên</label>
                    <select id="shift-employee" name="MaNV" required <?= $editingAssignmentId !== null ? 'disabled' : '' ?> aria-invalid="<?= isset($errors['MaNV']) ? 'true' : 'false' ?>">
                        <option value="">Chọn nhân viên</option>
                        <?php foreach ($employees as $employee): ?>
                            <?php $id = (int)$employee['MaNV']; ?>
                            <option value="<?= $id ?>" <?= (string)($formValues['MaNV'] ?? '') === (string)$id ? 'selected' : '' ?>>
                                NV<?= str_pad((string)$id, 3, '0', STR_PAD_LEFT) ?> · <?= htmlspecialchars((string)($employee['HoTen'] ?? ''), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?>
                            </option>
                        <?php endforeach; ?>
                    </select>
                    <?php if ($editingAssignmentId !== null): ?><input type="hidden" name="MaNV" value="<?= htmlspecialchars((string)$formValues['MaNV'], ENT_QUOTES, 'UTF-8') ?>"><?php endif; ?>
                    <?php if (isset($errors['MaNV'])): ?><p class="field-error"><?= htmlspecialchars($errors['MaNV'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></p><?php endif; ?>
                </div>
                <div class="form-field">
                    <label for="shift-id">Ca làm việc</label>
                    <select id="shift-id" name="MaCa" required aria-invalid="<?= isset($errors['MaCa']) ? 'true' : 'false' ?>">
                        <option value="">Chọn ca</option>
                        <?php
                        $selectedShiftIsActive = false;
                        foreach ($availableShifts as $activeShift) {
                            if ((string)$activeShift['MaCa'] === (string)($formValues['MaCa'] ?? '')) {
                                $selectedShiftIsActive = true;
                                break;
                            }
                        }
                        if (!$selectedShiftIsActive && !empty($formValues['MaCa'])):
                            foreach ($allShifts as $historicalShift):
                                if ((string)$historicalShift['MaCa'] === (string)$formValues['MaCa']): ?>
                                    <option value="<?= (int)$historicalShift['MaCa'] ?>" selected disabled>
                                        <?= htmlspecialchars((string)$historicalShift['TenCa'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?> (Ngừng sử dụng)
                                    </option>
                                <?php endif;
                            endforeach;
                        endif;
                        ?>
                        <?php foreach ($availableShifts as $shift): ?>
                            <?php $id = (int)$shift['MaCa']; ?>
                            <option value="<?= $id ?>" <?= (string)($formValues['MaCa'] ?? '') === (string)$id ? 'selected' : '' ?>>
                                <?= htmlspecialchars((string)$shift['TenCa'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?> (<?= htmlspecialchars(substr((string)$shift['GioBatDau'], 0, 5), ENT_QUOTES, 'UTF-8') ?>–<?= htmlspecialchars(substr((string)$shift['GioKetThuc'], 0, 5), ENT_QUOTES, 'UTF-8') ?>)
                            </option>
                        <?php endforeach; ?>
                    </select>
                    <?php if (isset($errors['MaCa'])): ?><p class="field-error"><?= htmlspecialchars($errors['MaCa'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></p><?php endif; ?>
                </div>
            </div>
            <?php if (isset($errors['NgayLamViec'])): ?><p class="field-error" role="alert"><?= htmlspecialchars($errors['NgayLamViec'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></p><?php endif; ?>
            <div class="form-actions">
                <button class="button button--primary" type="submit"><?= $editingAssignmentId === null ? 'Lưu phân ca' : 'Lưu thay đổi' ?></button>
                <?php if ($editingAssignmentId !== null): ?><a class="text-action" href="/?action=shifts&amp;tab=assignments&amp;date=<?= rawurlencode($selectedDate) ?>">Hủy đổi ca</a><?php endif; ?>
            </div>
        </form>
    </section>

    <section class="workspace-section" aria-label="Danh sách phân ca">
            <form class="workspace-toolbar shift-date-toolbar" method="get" action="/">
                <input type="hidden" name="action" value="shifts">
                <input type="hidden" name="tab" value="assignments">
                <strong><?= count($assignments) ?> phân ca</strong>
                <label for="assignment-date">Ngày<input id="assignment-date" type="date" name="date" value="<?= htmlspecialchars($selectedDate, ENT_QUOTES, 'UTF-8') ?>" required></label>
                <button class="button button--secondary button--small" type="submit">Xem</button>
            </form>
        <?php if ($error === null && $assignments === []): ?>
            <div class="empty-state">Chưa có nhân viên được phân ca trong ngày này.</div>
        <?php elseif ($assignments !== []): ?>
            <div class="table-scroll">
                <table class="employee-table data-table">
                    <caption class="visually-hidden">Phân ca nhân viên ngày <?= htmlspecialchars($selectedDate, ENT_QUOTES, 'UTF-8') ?></caption>
                    <thead><tr><th>Mã nhân viên</th><th>Họ tên</th><th>Ca</th><th>Thời gian</th><th>Thao tác</th></tr></thead>
                    <tbody>
                    <?php foreach ($assignments as $assignment): ?>
                        <?php $id = (int)$assignment['MaNV']; ?>
                        <tr>
                            <td><span class="employee-code">NV<?= str_pad((string)$id, 3, '0', STR_PAD_LEFT) ?></span></td>
                            <td><?= htmlspecialchars((string)($assignment['HoTen'] ?? ''), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></td>
                            <td><?= htmlspecialchars((string)$assignment['TenCa'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></td>
                            <td><?= htmlspecialchars(substr((string)$assignment['GioBatDau'], 0, 5), ENT_QUOTES, 'UTF-8') ?>–<?= htmlspecialchars(substr((string)$assignment['GioKetThuc'], 0, 5), ENT_QUOTES, 'UTF-8') ?></td>
                            <td class="shift-actions">
                                <a class="text-action" href="/?action=shifts&amp;tab=assignments&amp;date=<?= rawurlencode($selectedDate) ?>&amp;edit_assignment=<?= (int)$assignment['MaPhanCa'] ?>">Đổi ca</a>
                                <form method="post" action="/?action=unassign_shift" class="inline-action-form">
                                    <input type="hidden" name="_csrf_token" value="<?= htmlspecialchars($csrfToken, ENT_QUOTES, 'UTF-8') ?>">
                                    <input type="hidden" name="return_tab" value="assignments">
                                    <input type="hidden" name="return_date" value="<?= htmlspecialchars($selectedDate, ENT_QUOTES, 'UTF-8') ?>">
                                    <input type="hidden" name="MaPhanCa" value="<?= (int)$assignment['MaPhanCa'] ?>">
                                    <button class="button button--secondary button--small button--danger-text" type="submit">Hủy phân ca</button>
                                </form>
                            </td>
                        </tr>
                    <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
        <?php endif; ?>
    </section>
    <?php else: ?>

    <section class="workspace-section" aria-label="Danh mục ca làm việc">
        <div class="workspace-toolbar"><h2>Ca làm việc <span class="count-label"><?= count($allShifts) ?></span></h2></div>
        <?php if ($editingShiftId !== null): ?>
            <div class="shift-edit-form">
                <div class="section-heading">
                    <div>
                        <h3>Sửa ca CA<?= str_pad((string)$editingShiftId, 3, '0', STR_PAD_LEFT) ?></h3>
                        <?php if ($shiftTimeLocked): ?>
                            <p class="field-hint">Ca này đã phát sinh dữ liệu chấm công; không thể đổi khung giờ.</p>
                        <?php endif; ?>
                    </div>
                </div>
                <form class="employee-form" method="post" action="/?action=update_shift">
                    <input type="hidden" name="_csrf_token" value="<?= htmlspecialchars($csrfToken, ENT_QUOTES, 'UTF-8') ?>">
                    <input type="hidden" name="return_tab" value="shifts">
                    <input type="hidden" name="MaCa" value="<?= (int)$editingShiftId ?>">
                    <input type="hidden" name="return_date" value="<?= htmlspecialchars($selectedDate, ENT_QUOTES, 'UTF-8') ?>">
                    <div class="filter-grid">
                        <div class="form-field">
                            <label for="shift-name-edit">Tên ca *</label>
                            <input id="shift-name-edit" name="TenCa" maxlength="100" required value="<?= htmlspecialchars((string)$shiftFormValues['TenCa'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?>" aria-invalid="<?= isset($shiftErrors['TenCa']) ? 'true' : 'false' ?>">
                            <?php if (isset($shiftErrors['TenCa'])): ?><p class="field-error"><?= htmlspecialchars($shiftErrors['TenCa'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></p><?php endif; ?>
                        </div>
                        <div class="form-field">
                            <label for="shift-start-edit">Giờ bắt đầu *</label>
                            <input id="shift-start-edit" type="time" step="1" name="GioBatDau" required value="<?= htmlspecialchars(substr((string)$shiftFormValues['GioBatDau'], 0, 8), ENT_QUOTES, 'UTF-8') ?>" <?= $shiftTimeLocked ? 'readonly' : '' ?> aria-invalid="<?= isset($shiftErrors['GioBatDau']) ? 'true' : 'false' ?>">
                            <?php if (isset($shiftErrors['GioBatDau'])): ?><p class="field-error"><?= htmlspecialchars($shiftErrors['GioBatDau'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></p><?php endif; ?>
                        </div>
                        <div class="form-field">
                            <label for="shift-end-edit">Giờ kết thúc *</label>
                            <input id="shift-end-edit" type="time" step="1" name="GioKetThuc" required value="<?= htmlspecialchars(substr((string)$shiftFormValues['GioKetThuc'], 0, 8), ENT_QUOTES, 'UTF-8') ?>" <?= $shiftTimeLocked ? 'readonly' : '' ?> aria-invalid="<?= isset($shiftErrors['GioKetThuc']) ? 'true' : 'false' ?>">
                            <?php if (isset($shiftErrors['GioKetThuc'])): ?><p class="field-error"><?= htmlspecialchars($shiftErrors['GioKetThuc'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></p><?php endif; ?>
                        </div>
                    </div>
                    <div class="form-actions">
                        <button class="button button--primary" type="submit">Lưu thay đổi</button>
                        <a class="text-action" href="/?action=shifts&amp;tab=shifts&amp;date=<?= rawurlencode($selectedDate) ?>">Hủy</a>
                    </div>
                </form>
            </div>
        <?php else: ?>
            <details class="shift-create-details" <?= array_key_exists('_NormalizedStart', $shiftFormValues) ? 'open' : '' ?>>
                <summary class="button button--primary">+ Thêm ca</summary>
                <form class="employee-form shift-create-form" method="post" action="/?action=create_shift">
                    <input type="hidden" name="_csrf_token" value="<?= htmlspecialchars($csrfToken, ENT_QUOTES, 'UTF-8') ?>">
                    <input type="hidden" name="return_tab" value="shifts">
                    <input type="hidden" name="return_date" value="<?= htmlspecialchars($selectedDate, ENT_QUOTES, 'UTF-8') ?>">
                    <div class="filter-grid">
                        <div class="form-field">
                            <label for="shift-name-new">Tên ca *</label>
                            <input id="shift-name-new" name="TenCa" maxlength="100" required value="<?= htmlspecialchars((string)$shiftFormValues['TenCa'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?>" aria-invalid="<?= isset($shiftErrors['TenCa']) ? 'true' : 'false' ?>">
                            <?php if (isset($shiftErrors['TenCa'])): ?><p class="field-error"><?= htmlspecialchars($shiftErrors['TenCa'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></p><?php endif; ?>
                        </div>
                        <div class="form-field">
                            <label for="shift-start-new">Giờ bắt đầu *</label>
                            <input id="shift-start-new" type="time" step="1" name="GioBatDau" required value="<?= htmlspecialchars(substr((string)$shiftFormValues['GioBatDau'], 0, 8), ENT_QUOTES, 'UTF-8') ?>" aria-invalid="<?= isset($shiftErrors['GioBatDau']) ? 'true' : 'false' ?>">
                            <?php if (isset($shiftErrors['GioBatDau'])): ?><p class="field-error"><?= htmlspecialchars($shiftErrors['GioBatDau'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></p><?php endif; ?>
                        </div>
                        <div class="form-field">
                            <label for="shift-end-new">Giờ kết thúc *</label>
                            <input id="shift-end-new" type="time" step="1" name="GioKetThuc" required value="<?= htmlspecialchars(substr((string)$shiftFormValues['GioKetThuc'], 0, 8), ENT_QUOTES, 'UTF-8') ?>" aria-invalid="<?= isset($shiftErrors['GioKetThuc']) ? 'true' : 'false' ?>">
                            <?php if (isset($shiftErrors['GioKetThuc'])): ?><p class="field-error"><?= htmlspecialchars($shiftErrors['GioKetThuc'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></p><?php endif; ?>
                        </div>
                    </div>
                    <div class="form-actions"><button class="button button--primary" type="submit">Tạo ca làm việc</button></div>
                </form>
            </details>
        <?php endif; ?>

        <?php if ($allShifts === []): ?>
            <div class="empty-state">Chưa có ca làm việc được khai báo.</div>
        <?php else: ?>
            <div class="table-scroll">
                <table class="employee-table data-table">
                    <caption class="visually-hidden">Danh mục ca làm việc</caption>
                    <thead><tr><th>Mã ca</th><th>Tên ca</th><th>Bắt đầu</th><th>Kết thúc</th><th>Trạng thái</th><th>Sử dụng</th><th>Thao tác</th></tr></thead>
                    <tbody><?php foreach ($allShifts as $shift): ?>
                        <?php
                        $shiftId = (int)$shift['MaCa'];
                        $hasUsage = (int)$shift['SoPhanCa'] > 0 || (int)$shift['SoChamCong'] > 0;
                        ?>
                        <tr>
                            <td>CA<?= str_pad((string)$shiftId, 3, '0', STR_PAD_LEFT) ?></td>
                            <td><?= htmlspecialchars((string)$shift['TenCa'], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></td>
                            <td><?= htmlspecialchars(substr((string)$shift['GioBatDau'], 0, 5), ENT_QUOTES, 'UTF-8') ?></td>
                            <td><?= htmlspecialchars(substr((string)$shift['GioKetThuc'], 0, 5), ENT_QUOTES, 'UTF-8') ?></td>
                            <td><?= (int)$shift['TrangThai'] === 1 ? 'Đang sử dụng' : 'Ngừng sử dụng' ?></td>
                            <td><?= (int)$shift['SoPhanCa'] ?> phân ca · <?= (int)$shift['SoChamCong'] ?> lượt chấm công</td>
                            <td class="shift-actions">
                                <a class="text-action" href="/?action=shifts&amp;tab=shifts&amp;date=<?= rawurlencode($selectedDate) ?>&amp;edit_shift=<?= $shiftId ?>">Sửa</a>
                                <?php if (!$hasUsage): ?>
                                    <form method="post" action="/?action=delete_shift" class="inline-action-form" onsubmit="return confirm('Bạn có chắc muốn xóa ca này?')">
                                        <input type="hidden" name="_csrf_token" value="<?= htmlspecialchars($csrfToken, ENT_QUOTES, 'UTF-8') ?>">
                                        <input type="hidden" name="return_tab" value="shifts">
                                        <input type="hidden" name="MaCa" value="<?= $shiftId ?>">
                                        <button class="button button--secondary button--small button--danger-text" type="submit">Xóa</button>
                                    </form>
                                <?php elseif ((int)$shift['TrangThai'] === 1): ?>
                                    <form method="post" action="/?action=disable_shift" class="inline-action-form" onsubmit="return confirm('Bạn có chắc muốn ngừng sử dụng ca này?')">
                                        <input type="hidden" name="_csrf_token" value="<?= htmlspecialchars($csrfToken, ENT_QUOTES, 'UTF-8') ?>">
                                        <input type="hidden" name="return_tab" value="shifts">
                                        <input type="hidden" name="MaCa" value="<?= $shiftId ?>">
                                        <button class="button button--secondary button--small" type="submit">Ngừng sử dụng</button>
                                    </form>
                                <?php else: ?>
                                    <form method="post" action="/?action=enable_shift" class="inline-action-form">
                                        <input type="hidden" name="_csrf_token" value="<?= htmlspecialchars($csrfToken, ENT_QUOTES, 'UTF-8') ?>">
                                        <input type="hidden" name="return_tab" value="shifts">
                                        <input type="hidden" name="MaCa" value="<?= $shiftId ?>">
                                        <button class="button button--secondary button--small" type="submit">Kích hoạt lại</button>
                                    </form>
                                <?php endif; ?>
                            </td>
                        </tr>
                    <?php endforeach; ?></tbody>
                </table>
            </div>
        <?php endif; ?>
    </section>
    <?php endif; ?>
    </section>
</main>
<?php require __DIR__ . '/layout/footer.php'; ?>

<?php
require __DIR__ . '/layout/header.php';
$isEdit = $mode === 'edit';
$employeeId = $isEdit ? (int)$employee['MaNV'] : null;
$employeeName = $values['HoTen'] ?? ($employee['HoTen'] ?? '');
$username = $values['TenDangNhap'] ?? ($employee['TenDangNhap'] ?? '');
$selectedRole = $values['MaVaiTro'] ?? ($employee['MaVaiTro'] ?? null);
$hasAccount = $isEdit && (int)($employee['HasAccount'] ?? 0) === 1;
$accountOptional = $isEdit && !$hasAccount;
$formAction = $isEdit ? '/?action=update&amp;id=' . $employeeId : '/?action=store';
$h = static fn(mixed $value): string => htmlspecialchars((string)($value ?? ''), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
?>
<main class="page-container page-container--form">
    <div class="form-page-heading"><a class="back-link" href="/">&larr; Nhân viên</a><h1><?= $isEdit ? 'Sửa NV' . str_pad((string)$employeeId, 3, '0', STR_PAD_LEFT) : 'Thêm nhân viên' ?></h1></div>

    <section class="workspace employee-form-workspace" aria-label="Thông tin nhân viên">
    <?php if ($errors !== []): ?>
        <div class="notice notice--error" role="alert">Vui lòng kiểm tra lại thông tin bên dưới.</div>
    <?php endif; ?>

    <form class="employee-form" method="post" action="<?= $formAction ?>">
        <input type="hidden" name="_csrf_token" value="<?= $h($csrfToken) ?>">

        <section class="employee-form-section" aria-labelledby="employee-details-title">
            <div class="employee-form-section-heading">
                <h2 id="employee-details-title">Thông tin nhân viên</h2>
            </div>
            <div class="employee-form-grid">
                <?php if ($isEdit): ?>
                    <div class="form-field">
                        <label for="employee-code">Mã nhân viên</label>
                        <input id="employee-code" type="text" value="NV<?= $h(str_pad((string)$employeeId, 3, '0', STR_PAD_LEFT)) ?>" readonly>
                    </div>
                <?php endif; ?>

                <div class="form-field">
                    <label for="employee-name">Họ tên <span aria-hidden="true">*</span></label>
                    <input
                        id="employee-name"
                        name="HoTen"
                        type="text"
                        value="<?= $h($employeeName) ?>"
                        maxlength="100"
                        autocomplete="name"
                        required
                        aria-invalid="<?= isset($errors['HoTen']) ? 'true' : 'false' ?>"
                        <?= isset($errors['HoTen']) ? 'aria-describedby="employee-name-error"' : '' ?>
                    >
                    <?php if (isset($errors['HoTen'])): ?><p class="field-error" id="employee-name-error"><?= $h($errors['HoTen']) ?></p><?php endif; ?>
                </div>

                <div class="form-field">
                    <label for="employee-role">Vai trò <span aria-hidden="true">*</span></label>
                    <select id="employee-role" name="MaVaiTro" required aria-invalid="<?= isset($errors['MaVaiTro']) ? 'true' : 'false' ?>" <?= isset($errors['MaVaiTro']) ? 'aria-describedby="employee-role-error"' : '' ?>>
                        <option value="">Chọn vai trò</option>
                        <?php foreach ($roles as $role): ?>
                            <?php $roleId = (int)$role['MaVaiTro']; ?>
                            <option value="<?= $roleId ?>" <?= (string)$selectedRole === (string)$roleId ? 'selected' : '' ?>><?= $h($role['TenVaiTro']) ?></option>
                        <?php endforeach; ?>
                    </select>
                    <?php if (isset($errors['MaVaiTro'])): ?><p class="field-error" id="employee-role-error"><?= $h($errors['MaVaiTro']) ?></p><?php endif; ?>
                </div>
            </div>
        </section>

        <section class="employee-form-section" aria-labelledby="account-details-title">
            <div class="employee-form-section-heading">
                <h2 id="account-details-title">Tài khoản đăng nhập</h2>
            </div>
            <?php if ($isEdit && !$hasAccount): ?>
                <p class="form-account-notice">Nhân viên này chưa có tài khoản đăng nhập.</p>
            <?php endif; ?>
            <div class="employee-form-grid">
                <div class="form-field">
                    <label for="employee-username">Tên đăng nhập<?= $accountOptional ? '' : ' *' ?></label>
                    <input id="employee-username" name="TenDangNhap" type="text" value="<?= $h($username) ?>" maxlength="50" autocomplete="username" <?= $accountOptional ? '' : 'required' ?> aria-invalid="<?= isset($errors['TenDangNhap']) ? 'true' : 'false' ?>" <?= isset($errors['TenDangNhap']) ? 'aria-describedby="employee-username-error"' : '' ?>>
                    <?php if (isset($errors['TenDangNhap'])): ?><p class="field-error" id="employee-username-error"><?= $h($errors['TenDangNhap']) ?></p><?php endif; ?>
                </div>

                <div class="form-field">
                    <label for="employee-password"><?= $isEdit && $hasAccount ? 'Mật khẩu mới' : 'Mật khẩu' ?><?= $isEdit && $hasAccount ? '' : ($accountOptional ? ' (khi tạo tài khoản)' : ' *') ?></label>
                    <div class="password-input-wrap">
                        <input id="employee-password" name="<?= $isEdit ? 'NewPassword' : 'MatKhau' ?>" type="password" autocomplete="new-password" minlength="6" <?= $isEdit && $hasAccount || $accountOptional ? '' : 'required' ?> aria-invalid="<?= isset($errors['Password']) ? 'true' : 'false' ?>" <?= isset($errors['Password']) ? 'aria-describedby="employee-password-error"' : '' ?>>
                        <button class="password-toggle" type="button" data-password-toggle="employee-password" aria-pressed="false">Hiện</button>
                    </div>
                    <?php if (isset($errors['Password'])): ?><p class="field-error" id="employee-password-error"><?= $h($errors['Password']) ?></p><?php endif; ?>
                </div>

                <div class="form-field">
                    <label for="employee-password-confirm"><?= $isEdit ? 'Xác nhận mật khẩu mới' : 'Xác nhận mật khẩu' ?><?= $isEdit && $hasAccount ? '' : ($accountOptional ? ' (khi tạo tài khoản)' : ' *') ?></label>
                    <div class="password-input-wrap">
                        <input id="employee-password-confirm" name="ConfirmPassword" type="password" autocomplete="new-password" minlength="6" <?= $isEdit && $hasAccount || $accountOptional ? '' : 'required' ?> aria-invalid="<?= isset($errors['ConfirmPassword']) ? 'true' : 'false' ?>" <?= isset($errors['ConfirmPassword']) ? 'aria-describedby="employee-password-confirm-error"' : '' ?>>
                        <button class="password-toggle" type="button" data-password-toggle="employee-password-confirm" aria-pressed="false">Hiện</button>
                    </div>
                    <?php if (isset($errors['ConfirmPassword'])): ?><p class="field-error" id="employee-password-confirm-error"><?= $h($errors['ConfirmPassword']) ?></p><?php endif; ?>
                </div>
            </div>
        </section>

        <div class="form-actions">
            <a class="button button--secondary" href="/">Hủy</a>
            <button class="button button--primary" type="submit"><?= $isEdit ? 'Lưu thay đổi' : 'Tạo nhân viên và tài khoản' ?></button>
        </div>
    </form>

    <?php if ($isEdit): ?>
        <?php
        $faceCount = count($faceSamples);
        $faceImageCount = count(array_filter($faceSamples, static fn(array $sample): bool => (int)$sample['HasImage'] === 1));
        ?>
        <section class="face-management" aria-labelledby="face-management-title">
            <div class="face-management-heading">
                <div>
                    <h2 id="face-management-title">Khuôn mặt <span class="face-count"><?= $faceCount ?> mẫu<?= $faceImageCount > 0 ? ' · ' . $faceImageCount . ' ảnh' : '' ?></span></h2>
                </div>
                <div class="face-management-actions">
                    <button class="button button--primary" type="button" data-face-start>
                        <?= $faceCount > 0 ? 'Đăng ký lại' : 'Đăng ký khuôn mặt' ?>
                    </button>
                    <?php if ($faceCount > 0): ?>
                        <button class="button button--danger" type="button" data-face-delete>Xóa đăng ký</button>
                    <?php endif; ?>
                </div>
            </div>

            <?php if ($faceSamples === []): ?>
                <p class="empty-state face-empty-state">Chưa có dữ liệu khuôn mặt.</p>
            <?php else: ?>
                <div class="face-sample-grid">
                    <?php foreach ($faceSamples as $sample): ?>
                        <?php
                        $embeddingId = (int)$sample['MaEmbedding'];
                        $createdAt = $sample['ThoiGianTao'] !== null
                            ? date('d/m/Y H:i', strtotime((string)$sample['ThoiGianTao']))
                            : 'Không rõ thời gian';
                        ?>
                        <article class="face-sample">
                            <?php if ((int)$sample['HasImage'] === 1): ?>
                                <button class="face-sample-image" type="button" data-face-preview="/?action=face_image&amp;id=<?= $embeddingId ?>" aria-label="Xem ảnh mẫu <?= $embeddingId ?>">
                                    <img src="/?action=face_image&amp;id=<?= $embeddingId ?>" alt="Mẫu khuôn mặt <?= $embeddingId ?>" loading="lazy">
                                </button>
                                <p class="face-sample-title">Mẫu khuôn mặt</p>
                            <?php else: ?>
                                <div class="face-sample-legacy" aria-hidden="true"><span>Ảnh</span></div>
                                <p class="face-sample-title">Mẫu khuôn mặt cũ</p>
                                <p class="face-sample-note">Không có ảnh xem trước</p>
                            <?php endif; ?>
                            <p class="face-sample-meta">Mã mẫu <?= $embeddingId ?></p>
                            <time class="face-sample-meta" datetime="<?= htmlspecialchars((string)($sample['ThoiGianTao'] ?? ''), ENT_QUOTES, 'UTF-8') ?>"><?= htmlspecialchars($createdAt, ENT_QUOTES, 'UTF-8') ?></time>
                        </article>
                    <?php endforeach; ?>
                </div>
            <?php endif; ?>

            <div class="face-enrollment" data-face-enrollment data-employee-id="<?= $employeeId ?>" data-csrf="<?= htmlspecialchars($csrfToken, ENT_QUOTES, 'UTF-8') ?>" data-face-count="<?= $faceCount ?>" hidden>
                <div class="face-enrollment-camera-wrap">
                    <img class="face-enrollment-camera" data-face-camera alt="Khung hình camera đăng ký khuôn mặt" hidden>
                    <div class="face-enrollment-camera-empty" data-face-camera-empty>Camera sẽ mở từ nguồn camera hiện tại khi bắt đầu đăng ký.</div>
                </div>
                <div class="face-enrollment-progress" aria-live="polite">
                    <p class="face-enrollment-step" data-face-step>Bước 1/5 · Chính diện</p>
                    <p class="face-enrollment-feedback" data-face-feedback>Nhấn “Bắt đầu” để khởi tạo phiên đăng ký.</p>
                    <ol class="face-pose-list" data-face-pose-list>
                        <li data-pose="frontal">Chính diện</li>
                        <li data-pose="left">Nghiêng trái</li>
                        <li data-pose="right">Nghiêng phải</li>
                        <li data-pose="up">Ngẩng nhẹ</li>
                        <li data-pose="down">Cúi nhẹ</li>
                    </ol>
                </div>
                <div class="face-enrollment-actions">
                    <button class="button button--secondary" type="button" data-face-cancel hidden>Hủy phiên</button>
                    <button class="button button--primary" type="button" data-face-complete disabled hidden>Lưu 5 mẫu</button>
                </div>
            </div>
            <p class="notice face-enrollment-result" data-face-result role="status" hidden></p>
        </section>

    <?php endif; ?>
    </section>

    <?php if ($isEdit): ?>
        <dialog class="face-lightbox" data-face-lightbox aria-label="Ảnh mẫu khuôn mặt">
            <div class="face-lightbox-toolbar">
                <span data-face-lightbox-title>Ảnh mẫu khuôn mặt</span>
                <button class="button button--secondary button--small" type="button" data-face-lightbox-close>Đóng</button>
            </div>
            <img data-face-lightbox-image alt="Ảnh mẫu khuôn mặt phóng lớn">
        </dialog>
    <?php endif; ?>
</main>
<script src="/public/js/employee_form.js" defer></script>
<?php if ($isEdit): ?><script src="/public/js/face_enrollment.js" defer></script><?php endif; ?>
<?php require __DIR__ . '/layout/footer.php'; ?>

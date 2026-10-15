<?php require __DIR__ . '/layout/header.php'; ?>
<main class="page-container">
    <section class="workspace" aria-labelledby="employee-list-title">
        <?php if ($successMessage !== null): ?>
            <div class="notice notice--success" role="status"><?= htmlspecialchars((string)$successMessage, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></div>
        <?php endif; ?>
        <div class="workspace-toolbar">
            <h1 id="employee-list-title">Nhân viên (<span id="visible-count"><?= count($employees) ?></span>)</h1>
            <label class="search-field">
                <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <circle cx="10.8" cy="10.8" r="6.3" stroke="currentColor" stroke-width="1.7"/>
                    <path d="m15.5 15.5 4 4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>
                </svg>
                <span class="visually-hidden">Tìm theo mã, họ tên hoặc tên đăng nhập</span>
                <input id="employee-search" type="search" placeholder="Tìm mã, họ tên hoặc tên đăng nhập" autocomplete="off">
            </label>
            <a class="button button--primary" href="/?action=create">Thêm nhân viên</a>
        </div>

        <?php if ($error !== null): ?>
            <div class="notice notice--error" role="alert"><?= htmlspecialchars($error, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></div>
        <?php elseif ($employees === []): ?>
            <div class="empty-state">Chưa có nhân viên trong hệ thống.</div>
        <?php else: ?>
            <div class="table-scroll">
                <table class="employee-table employees-list-table">
                    <caption class="visually-hidden">Danh sách nhân viên và trạng thái đăng ký khuôn mặt</caption>
                    <thead>
                    <tr>
                        <th scope="col">Mã nhân viên</th>
                        <th scope="col">Họ tên</th>
                        <th scope="col">Tên đăng nhập</th>
                        <th scope="col">Vai trò</th>
                        <th scope="col">Tài khoản</th>
                        <th scope="col">Khuôn mặt</th>
                        <th scope="col"><span class="visually-hidden">Thao tác</span></th>
                    </tr>
                    </thead>
                    <tbody id="employee-rows">
                    <?php foreach ($employees as $employee): ?>
                        <?php
                        $employeeId = (int)$employee['MaNV'];
                        $employeeCode = 'NV' . str_pad((string)$employeeId, 3, '0', STR_PAD_LEFT);
                        $employeeName = (string)($employee['HoTen'] ?? '');
                        $username = (string)($employee['TenDangNhap'] ?? '');
                        $role = (string)($employee['TenVaiTro'] ?? 'Chưa phân vai trò');
                        $hasAccount = (int)($employee['HasAccount'] ?? 0) === 1;
                        $faceCount = (int)($employee['FaceEmbeddingCount'] ?? 0);
                        $searchValue = $employeeCode . ' ' . $employeeId . ' ' . $employeeName . ' ' . $username;
                        ?>
                        <tr class="employee-row" data-search="<?= htmlspecialchars($searchValue, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?>">
                            <td><span class="employee-code"><?= htmlspecialchars($employeeCode, ENT_QUOTES, 'UTF-8') ?></span></td>
                            <td class="employee-name"><?= htmlspecialchars($employeeName !== '' ? $employeeName : 'Chưa cập nhật', ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></td>
                            <td><?= htmlspecialchars($username !== '' ? $username : '--', ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></td>
                            <td><span class="role-label"><?= htmlspecialchars($role, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></span></td>
                            <td><span class="status-pill <?= $hasAccount ? 'status-pill--registered' : 'status-pill--pending' ?>"><span aria-hidden="true"></span><?= $hasAccount ? 'Có tài khoản' : 'Chưa có tài khoản' ?></span></td>
                            <td>
                                <?php if ($faceCount > 0): ?>
                                    <span class="status-pill status-pill--registered"><span aria-hidden="true"></span>Đã đăng ký · <?= $faceCount ?> mẫu</span>
                                <?php else: ?>
                                    <span class="status-pill status-pill--pending"><span aria-hidden="true"></span>Chưa đăng ký</span>
                                <?php endif; ?>
                            </td>
                            <td class="employee-actions">
                                <a class="button button--secondary button--small" href="/?action=edit&amp;id=<?= $employeeId ?>" aria-label="Sửa <?= htmlspecialchars($employeeName, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?>">Sửa</a>
                            </td>
                        </tr>
                    <?php endforeach; ?>
                    </tbody>
                </table>
            </div>
            <p class="empty-search" id="empty-search" hidden>Không tìm thấy nhân viên phù hợp.</p>
        <?php endif; ?>
    </section>
</main>
<?php require __DIR__ . '/layout/footer.php'; ?>

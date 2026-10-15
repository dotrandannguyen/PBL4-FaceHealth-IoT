<!doctype html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#f6f7f9">
    <title><?= htmlspecialchars($pageTitle ?? 'Nhân viên', ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></title>
    <link rel="icon" href="data:,">
    <link rel="stylesheet" href="/public/css/app.css">
</head>
<body>
<header class="topbar">
    <?php if (isset($_SESSION['user_id'])): ?>
        <?php if ((int)($_SESSION['ma_vai_tro'] ?? 0) === 1): ?>
            <?php $activeAction = $_GET['action'] ?? 'index'; ?>
            <nav class="topbar-nav" aria-label="Quản lý">
                <a href="/?action=dashboard" <?= $activeAction === 'dashboard' ? 'aria-current="page"' : '' ?>>Tổng quan</a>
                <a href="/" <?= $activeAction === 'index' ? 'aria-current="page"' : '' ?>>Nhân viên</a>
                <a href="/?action=shifts" <?= $activeAction === 'shifts' ? 'aria-current="page"' : '' ?>>Phân ca</a>
                <a href="/?action=attendance" <?= $activeAction === 'attendance' ? 'aria-current="page"' : '' ?>>Chấm công</a>
                <a href="/?action=monitoring" <?= $activeAction === 'monitoring' ? 'aria-current="page"' : '' ?>>Sức khỏe &amp; Cảnh báo</a>
                <a href="/?action=devices" <?= $activeAction === 'devices' ? 'aria-current="page"' : '' ?>>Thiết bị</a>
            </nav>
        <?php elseif ((int)($_SESSION['ma_vai_tro'] ?? 0) === 2): ?>
            <nav class="topbar-nav" aria-label="Trang cá nhân">
                <a href="/?action=my" <?= ($_GET['action'] ?? '') === 'my' ? 'aria-current="page"' : '' ?>>Trang của tôi</a>
            </nav>
        <?php endif; ?>
        <div class="topbar-account">
            <div class="account-meta">
                <span class="account-name"><?= htmlspecialchars((string)($_SESSION['display_name'] ?? ''), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></span>
                <span class="account-role"><?= htmlspecialchars((string)($_SESSION['role'] ?? ''), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></span>
            </div>
            <form class="logout-form" method="post" action="/?action=logout">
                <input type="hidden" name="_csrf_token" value="<?= htmlspecialchars((string)($_SESSION['employee_csrf_token'] ?? ''), ENT_QUOTES, 'UTF-8') ?>">
                <button class="logout-button" type="submit">Đăng xuất</button>
            </form>
        </div>
    <?php endif; ?>
</header>

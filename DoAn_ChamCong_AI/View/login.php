<?php require __DIR__ . '/layout/header.php'; ?>
<main class="auth-container">
    <section class="form-panel auth-panel" aria-labelledby="login-title">
        <h1 id="login-title">Đăng nhập</h1>

        <?php if ($loginError !== null): ?>
            <div class="notice notice--error" role="alert"><?= htmlspecialchars($loginError, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?></div>
        <?php endif; ?>

        <form class="employee-form" method="post" action="/?action=login">
            <input type="hidden" name="_csrf_token" value="<?= htmlspecialchars($csrfToken, ENT_QUOTES, 'UTF-8') ?>">
            <div class="form-field">
                <label for="login-username">Tên đăng nhập</label>
                <input id="login-username" name="username" type="text" value="<?= htmlspecialchars($loginUsername, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') ?>" maxlength="50" autocomplete="username" required autofocus>
            </div>
            <div class="form-field">
                <label for="login-password">Mật khẩu</label>
                <input id="login-password" name="password" type="password" autocomplete="current-password" required>
            </div>
            <button class="button button--primary auth-submit" type="submit">Đăng nhập</button>
        </form>
    </section>
</main>
<?php require __DIR__ . '/layout/footer.php'; ?>

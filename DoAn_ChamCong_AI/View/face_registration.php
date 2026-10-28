<?php
declare(strict_types=1);
require __DIR__ . '/layout/header.php';

$h = static fn(mixed $value): string => htmlspecialchars((string)($value ?? ''), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
$selectedId = $selectedEmployee !== null ? (int)$selectedEmployee['MaNV'] : null;
$selectedName = $selectedEmployee !== null ? (string)$selectedEmployee['HoTen'] : '';
$selectedCode = $selectedId !== null ? 'NV' . str_pad((string)$selectedId, 3, '0', STR_PAD_LEFT) : '';
$faceCount = count($faceSamples);
$faceImageCount = count(array_filter($faceSamples, static fn(array $sample): bool => (int)$sample['HasImage'] === 1));
$aiReady = !empty($aiHealth['model_ready']);
$cameraOpen = !empty($aiHealth['camera_open']);
$cameraSource = !empty($cameraSource) && in_array($cameraSource, ['local', 'esp32'], true) ? $cameraSource : 'local';
?>

<style>
/* ── Giao diện Chuyên mục Đăng ký Khuôn mặt (Hero Studio) ─────────────── */
.face-reg-layout {
    display: grid;
    grid-template-columns: minmax(0, 1.58fr) minmax(360px, 1fr);
    gap: 24px;
    align-items: start;
    margin-top: 12px;
}

@media (max-width: 1024px) {
    .face-reg-layout {
        grid-template-columns: 1fr;
    }
}

/* Card Studio & Card Sidebar */
.face-reg-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 22px;
    box-shadow: 0 2px 10px rgba(15, 23, 42, 0.04);
}

/* Thiết bị Camera quét Segmented Switcher */
.face-device-selector-box {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
    padding: 12px 16px;
    margin-bottom: 18px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
}

.face-device-pills {
    display: inline-flex;
    background: #e2e8f0;
    padding: 3px;
    border-radius: 8px;
    gap: 4px;
}

.face-device-btn {
    border: none;
    padding: 7px 16px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: transparent;
    color: #475467;
}

.face-device-btn:hover {
    color: #1e293b;
}

.face-device-btn.is-active {
    background: #2563eb;
    color: #ffffff;
    box-shadow: 0 1px 3px rgba(37, 99, 235, 0.25);
}

/* Hero Camera Viewport */
.face-hero-viewport {
    position: relative;
    width: 100%;
    min-height: 460px;
    max-height: 560px;
    aspect-ratio: 16 / 10;
    border-radius: 14px;
    overflow: hidden;
    background: #070b14;
    border: 2px solid #1e293b;
    box-shadow: 0 12px 30px -5px rgba(0, 0, 0, 0.35);
    display: flex;
    align-items: center;
    justify-content: center;
}

.face-hero-camera-img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    background: #000;
    display: block;
}

/* Viewfinder Reticle Overlay */
.face-reticle-overlay {
    position: absolute;
    inset: 0;
    pointer-events: none;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    padding: 16px;
    z-index: 10;
}

.face-reticle-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.face-reticle-live-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    background: rgba(15, 23, 42, 0.75);
    backdrop-filter: blur(4px);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
    color: #f8fafc;
}

.face-reticle-live-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #ef4444;
    box-shadow: 0 0 8px #ef4444;
    animation: livePulse 1.6s infinite ease-in-out;
}

@keyframes livePulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.4; transform: scale(0.85); }
}

.face-reticle-center {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 260px;
    height: 330px;
    pointer-events: none;
}

.face-reticle-center svg {
    width: 100%;
    height: 100%;
    overflow: visible;
}

.face-reticle-oval {
    fill: none;
    stroke: rgba(56, 189, 248, 0.65);
    stroke-width: 2.5;
    stroke-dasharray: 8 6;
    transition: all 0.3s ease;
}

.face-reticle-corner {
    fill: none;
    stroke: rgba(56, 189, 248, 0.85);
    stroke-width: 3.5;
    stroke-linecap: round;
    transition: all 0.3s ease;
}

/* Khi khuôn mặt khớp tư thế và khóa chụp */
.face-hero-viewport.is-matched .face-reticle-oval {
    stroke: #22c55e;
    stroke-dasharray: none;
    stroke-width: 3.5;
    filter: drop-shadow(0 0 10px rgba(34, 197, 94, 0.8));
}

.face-hero-viewport.is-matched .face-reticle-corner {
    stroke: #22c55e;
    stroke-width: 4.5;
    filter: drop-shadow(0 0 8px rgba(34, 197, 94, 0.9));
}

.face-reticle-bottom-hint {
    text-align: center;
    background: rgba(15, 23, 42, 0.7);
    backdrop-filter: blur(4px);
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: #e2e8f0;
    padding: 6px 14px;
    border-radius: 8px;
    font-size: 13px;
    align-self: center;
}

/* Pose Step Cards Grid */
.face-pose-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 8px;
    list-style: none;
    padding: 0;
    margin: 14px 0 0;
}

.face-pose-card {
    text-align: center;
    padding: 10px 4px;
    border-radius: 8px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    transition: all 0.25s ease;
}

.face-pose-card .pose-num {
    font-size: 11px;
    font-weight: 700;
    color: #64748b;
    display: block;
    margin-bottom: 2px;
}

.face-pose-card .pose-title {
    font-size: 13px;
    font-weight: 600;
    color: #1e293b;
    display: block;
}

.face-pose-card .pose-status {
    font-size: 11px;
    margin-top: 4px;
    display: block;
    color: #94a3b8;
}

.face-pose-card.is-active {
    background: #eff6ff;
    border-color: #3b82f6;
    box-shadow: 0 0 0 1px #3b82f6, 0 4px 12px rgba(59, 130, 246, 0.12);
}

.face-pose-card.is-active .pose-num {
    color: #2563eb;
}

.face-pose-card.is-active .pose-title {
    color: #1d4ed8;
}

.face-pose-card.is-active .pose-status {
    color: #2563eb;
    font-weight: 600;
}

.face-pose-card.is-complete {
    background: #ecfdf5;
    border-color: #10b981;
}

.face-pose-card.is-complete .pose-num {
    color: #059669;
}

.face-pose-card.is-complete .pose-title {
    color: #047857;
}

.face-pose-card.is-complete .pose-status {
    color: #059669;
    font-weight: 600;
}

/* Feedback Box */
.face-feedback-box {
    margin-top: 16px;
    padding: 14px 18px;
    border-radius: 10px;
    background: #f1f5f9;
    border-left: 4px solid #3b82f6;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
}

/* Bảng danh sách nhân viên */
.face-emp-table th,
.face-emp-table td {
    padding: 10px 12px;
}
</style>

<main class="page-container page-container--wide">
    <!-- Topbar điều hướng & trạng thái AI -->
    <div class="workspace-toolbar" style="margin-bottom: 20px;">
        <div>
            <h1 style="font-size: 24px; font-weight: 700; color: #0f172a; margin: 0 0 4px;">
                Đăng ký nhận diện khuôn mặt
            </h1>
            <p style="margin: 0; color: #64748b; font-size: 14px;">
                Thu thập và lưu trữ 5 góc khuôn mặt (ArcFace 512-dim) phục vụ điểm danh nhận diện khuôn mặt thời gian thực.
            </p>
        </div>
        <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
            <div class="status-pill <?= $aiReady ? 'status-pill--registered' : 'status-pill--pending' ?>" style="font-weight: 500;">
                <span aria-hidden="true"></span>
                AI Service: <?= $aiReady ? 'Sẵn sàng (buffalo_sc)' : 'Chưa kết nối' ?>
            </div>
            <a class="button button--secondary" href="/">Danh sách nhân viên</a>
        </div>
    </div>

    <!-- Bố cục 2 cột: Cột trái Studio Quét Mặt Rộng Lớn | Cột phải Danh bạ & Mẫu lưu -->
    <div class="face-reg-layout">
        <!-- ════════ CỘT TRÁI: STUDIO THU THẬP KHUÔN MẶT ════════ -->
        <section class="face-reg-card" aria-labelledby="studio-heading">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                <div>
                    <h2 id="studio-heading" style="margin: 0; font-size: 19px; font-weight: 700; color: #0f172a;">
                        Studio Camera Quét Mặt
                    </h2>
                    <p style="margin: 3px 0 0; color: #64748b; font-size: 13px;">
                        Khung hình tự động nhận diện và chụp khi đúng góc xoay khuôn mặt.
                    </p>
                </div>
                <?php if ($selectedId !== null): ?>
                    <span class="status-pill status-pill--registered" style="font-size: 13px; padding: 4px 12px;">
                        <?= $h($selectedCode) ?> · <?= $h($selectedName) ?>
                    </span>
                <?php endif; ?>
            </div>

            <?php if ($selectedId === null): ?>
                <div class="empty-state" style="padding: 48px 20px; text-align: center;">
                    <p style="font-size: 16px; font-weight: 600; color: #334155;">Chưa chọn nhân viên</p>
                    <p style="color: #64748b; font-size: 14px; margin-top: 4px;">
                        Vui lòng chọn một nhân viên từ danh sách ở cột bên phải để bắt đầu quét khuôn mặt.
                    </p>
                </div>
            <?php else: ?>
                <!-- 1. Hàng điều khiển: Chọn Nhân viên & Thiết bị quét -->
                <div style="display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, 1.4fr); gap: 14px; margin-bottom: 16px; align-items: end;">
                    <div class="form-field" style="margin: 0;">
                        <label for="employee-select-picker" style="font-weight: 600; font-size: 13px; color: #334155; margin-bottom: 6px; display: block;">
                            Nhân viên đang đăng ký:
                        </label>
                        <select id="employee-select-picker" class="input" style="width: 100%; padding: 8px 12px; border-radius: 8px; border: 1px solid #cbd5e1; font-weight: 500;" onchange="if(this.value) window.location.href='/?action=face_registration&id=' + this.value;">
                            <?php foreach ($employees as $emp): ?>
                                <?php
                                $eId = (int)$emp['MaNV'];
                                $eCode = 'NV' . str_pad((string)$eId, 3, '0', STR_PAD_LEFT);
                                $eName = (string)($emp['HoTen'] ?? '');
                                $eCount = (int)($emp['FaceEmbeddingCount'] ?? 0);
                                $selectedAttr = $eId === $selectedId ? 'selected' : '';
                                $statusText = $eCount > 0 ? " [Đã có {$eCount} mẫu]" : ' [Chưa đăng ký]';
                                ?>
                                <option value="<?= $eId ?>" <?= $selectedAttr ?>>
                                    <?= $h($eCode) ?> - <?= $h($eName) ?><?= $statusText ?>
                                </option>
                            <?php endforeach; ?>
                        </select>
                    </div>

                    <!-- Thiết bị quét: Webcam vs ESP32-CAM -->
                    <div style="margin: 0;">
                        <label style="font-weight: 600; font-size: 13px; color: #334155; margin-bottom: 6px; display: block;">
                            Thiết bị Camera quét:
                        </label>
                        <div class="face-device-pills" style="width: 100%; display: flex;">
                            <button type="button" class="face-device-btn <?= $cameraSource === 'local' ? 'is-active' : '' ?>" data-camera-device="local" style="flex: 1; justify-content: center;">
                                📷 Webcam máy tính
                            </button>
                            <button type="button" class="face-device-btn <?= $cameraSource === 'esp32' ? 'is-active' : '' ?>" data-camera-device="esp32" style="flex: 1; justify-content: center;">
                                📡 ESP32-CAM (WiFi)
                            </button>
                        </div>
                    </div>
                </div>

                <!-- Dòng gợi ý thiết bị nguồn -->
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; font-size: 12px; color: #64748b;">
                    <div id="camera-device-hint" style="font-family: monospace;">
                        <?= $cameraSource === 'esp32' ? '📡 Luồng ESP32: http://esp32cam.local:81/stream' : '📷 Nguồn Webcam: Camera ID 0 (DirectShow 640x480)' ?>
                    </div>
                    <div>
                        Ánh sáng đủ, đứng cách camera 50 - 70 cm.
                    </div>
                </div>

                <!-- 2. Khối Hero Camera Viewport Lớn & Khung ngắm Viewfinder -->
                <div class="face-enrollment-root" data-face-enrollment data-employee-id="<?= $selectedId ?>" data-csrf="<?= $h($csrfToken) ?>" data-face-count="<?= $faceCount ?>" data-camera-source="<?= $h($cameraSource) ?>">
                    <div class="face-hero-viewport" data-face-viewport>
                        <!-- Ảnh stream Camera -->
                        <img class="face-hero-camera-img" data-face-camera alt="Khung hình camera đăng ký khuôn mặt" hidden>

                        <!-- Trạng thái chờ / ngắt kết nối -->
                        <div class="face-hero-empty" data-face-camera-empty style="color: #94a3b8; text-align: center; padding: 32px 20px;">
                            <svg style="width: 56px; height: 56px; margin: 0 auto 14px; stroke: #475467; fill: none;" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.6" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"/>
                            </svg>
                            <div style="font-size: 16px; font-weight: 600; color: #e2e8f0; margin-bottom: 6px;">Camera đang ở chế độ chờ</div>
                            <div style="font-size: 13px; color: #94a3b8; max-width: 360px; margin: 0 auto;">
                                Nhấn nút <strong>"Bắt đầu đăng ký"</strong> bên dưới để mở luồng camera và nhận diện 5 tư thế khuôn mặt.
                            </div>
                        </div>

                        <!-- Khung ngắm Viewfinder Reticle Overlay khi camera đang mở -->
                        <div class="face-reticle-overlay" data-face-reticle hidden>
                            <div class="face-reticle-top">
                                <span class="face-reticle-live-badge">
                                    <span class="face-reticle-live-dot"></span>
                                    <span>LIVE</span>
                                    <span style="color: #94a3b8; margin: 0 2px;">·</span>
                                    <span data-reticle-source-label><?= $cameraSource === 'esp32' ? 'ESP32-CAM' : 'WEBCAM' ?></span>
                                </span>
                                <span style="font-size: 12px; color: rgba(255,255,255,0.7); font-family: monospace; background: rgba(0,0,0,0.5); padding: 3px 8px; border-radius: 6px;">
                                    640x480 · 512-dim ArcFace
                                </span>
                            </div>

                            <!-- Khung hình bầu dục trung tâm định vị khuôn mặt -->
                            <div class="face-reticle-center">
                                <svg viewBox="0 0 260 330">
                                    <!-- 4 góc ngắm nhọn -->
                                    <path class="face-reticle-corner" d="M 20 50 L 20 20 L 50 20" />
                                    <path class="face-reticle-corner" d="M 210 20 L 240 20 L 240 50" />
                                    <path class="face-reticle-corner" d="M 20 280 L 20 310 L 50 310" />
                                    <path class="face-reticle-corner" d="M 210 310 L 240 310 L 240 280" />
                                    <!-- Hình bầu dục khuôn mặt -->
                                    <ellipse class="face-reticle-oval" cx="130" cy="165" rx="90" ry="125" />
                                </svg>
                            </div>

                            <div class="face-reticle-bottom-hint" data-reticle-hint>
                                Đặt khuôn mặt vào giữa khung bầu dục và làm theo chỉ dẫn tư thế bên dưới.
                            </div>
                        </div>
                    </div>

                    <!-- 3. Hộp hướng dẫn trực quan thời gian thực -->
                    <div class="face-feedback-box" aria-live="polite">
                        <div>
                            <div class="face-enrollment-step" data-face-step style="font-size: 16px; font-weight: 700; color: #0f172a;">
                                Bước 1/5 · Chính diện
                            </div>
                            <div class="face-enrollment-feedback" data-face-feedback style="font-size: 14px; color: #475467; margin-top: 4px;">
                                Nhấn "Bắt đầu đăng ký" để hệ thống tự động nhận diện và chụp 5 tư thế khuôn mặt.
                            </div>
                        </div>
                        <div id="pose-match-indicator" style="display: none; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 20px; background: #dcfce7; color: #15803d; font-weight: 600; font-size: 13px;">
                            <span>✓ Khớp tư thế! Giữ yên...</span>
                        </div>
                    </div>

                    <!-- 4. Lưới 5 thẻ tư thế trực quan (100% bề ngang) -->
                    <ol class="face-pose-grid" data-face-pose-list>
                        <li class="face-pose-card" data-pose="frontal">
                            <span class="pose-num">Bước 1</span>
                            <span class="pose-title">👤 Chính diện</span>
                            <span class="pose-status" data-pose-status>Chờ chụp</span>
                        </li>
                        <li class="face-pose-card" data-pose="left">
                            <span class="pose-num">Bước 2</span>
                            <span class="pose-title">👈 Nghiêng trái</span>
                            <span class="pose-status" data-pose-status>Chờ chụp</span>
                        </li>
                        <li class="face-pose-card" data-pose="right">
                            <span class="pose-num">Bước 3</span>
                            <span class="pose-title">👉 Nghiêng phải</span>
                            <span class="pose-status" data-pose-status>Chờ chụp</span>
                        </li>
                        <li class="face-pose-card" data-pose="up">
                            <span class="pose-num">Bước 4</span>
                            <span class="pose-title">👆 Ngẩng nhẹ</span>
                            <span class="pose-status" data-pose-status>Chờ chụp</span>
                        </li>
                        <li class="face-pose-card" data-pose="down">
                            <span class="pose-num">Bước 5</span>
                            <span class="pose-title">👇 Cúi nhẹ</span>
                            <span class="pose-status" data-pose-status>Chờ chụp</span>
                        </li>
                    </ol>

                    <!-- 5. Thanh nút bấm điều khiển hành động -->
                    <div style="display: flex; gap: 10px; margin-top: 20px; flex-wrap: wrap; align-items: center;">
                        <button class="button button--primary" type="button" data-face-start style="padding: 10px 22px; font-size: 15px; font-weight: 600;">
                            <?= $faceCount > 0 ? '🔄 Đăng ký lại (5 góc)' : '📸 Bắt đầu đăng ký khuôn mặt' ?>
                        </button>
                        <button class="button button--secondary" type="button" data-face-cancel hidden style="padding: 10px 18px; font-size: 14px;">
                            ⏸️ Hủy phiên quét
                        </button>
                        <button class="button button--primary" type="button" data-face-complete disabled hidden style="padding: 10px 22px; font-size: 15px; font-weight: 600; background: #16a34a; border-color: #15803d;">
                            💾 Lưu 5 mẫu khuôn mặt
                        </button>
                        <?php if ($faceCount > 0): ?>
                            <button class="button button--danger" type="button" data-face-delete style="margin-left: auto; padding: 10px 16px; font-size: 13px;">
                                🗑️ Xóa toàn bộ dữ liệu khuôn mặt
                            </button>
                        <?php endif; ?>
                    </div>

                    <!-- Thông báo trạng thái kết quả -->
                    <p class="notice face-enrollment-result" data-face-result role="status" style="margin-top: 16px;" hidden></p>
                </div>
            <?php endif; ?>
        </section>

        <!-- ════════ CỘT PHẢI: THƯ VIỆN MẪU & DANH BẠ NHÂN VIÊN ════════ -->
        <div style="display: flex; flex-direction: column; gap: 20px;">
            <!-- Khối 1: Thư viện 5 góc ảnh mẫu của nhân viên đang chọn -->
            <?php if ($selectedId !== null): ?>
                <section class="face-reg-card" aria-labelledby="sample-gallery-title">
                    <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 14px;">
                        <h2 id="sample-gallery-title" style="margin: 0; font-size: 16px; font-weight: 700; color: #0f172a;">
                            Mẫu khuôn mặt hiện có (<?= $faceCount ?>/5)
                        </h2>
                        <?php if ($faceCount >= 5): ?>
                            <span style="font-size: 12px; color: #16a34a; font-weight: 600;">✓ Đủ 5 góc nhận diện</span>
                        <?php elseif ($faceCount > 0): ?>
                            <span style="font-size: 12px; color: #d97706; font-weight: 600;">⚠️ Thiếu mẫu (<?= $faceCount ?>/5)</span>
                        <?php else: ?>
                            <span style="font-size: 12px; color: #64748b;">Chưa đăng ký</span>
                        <?php endif; ?>
                    </div>

                    <?php if ($faceSamples === []): ?>
                        <div class="empty-state" style="padding: 24px 14px; text-align: center; margin: 0; background: #f8fafc; border-radius: 8px; border: 1px dashed #cbd5e1;">
                            <div style="font-size: 13px; color: #64748b;">Nhân viên này chưa có dữ liệu khuôn mặt.</div>
                            <div style="font-size: 12px; color: #94a3b8; margin-top: 4px;">Hãy nhấn nút "Bắt đầu đăng ký" ở bên trái.</div>
                        </div>
                    <?php else: ?>
                        <div class="face-sample-grid" style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px;">
                            <?php foreach ($faceSamples as $idx => $sample): ?>
                                <?php
                                $embeddingId = (int)$sample['MaEmbedding'];
                                $hasImg = (int)($sample['HasImage'] ?? 0) === 1;
                                $timeStr = !empty($sample['ThoiGianTao']) ? date('d/m H:i', strtotime((string)$sample['ThoiGianTao'])) : '';
                                ?>
                                <article class="face-sample" style="text-align: center; border: 1px solid #e2e8f0; border-radius: 8px; padding: 6px; background: #ffffff;">
                                    <?php if ($hasImg): ?>
                                        <button class="face-sample-image" type="button" data-face-preview="/?action=face_image&amp;id=<?= $embeddingId ?>" aria-label="Xem ảnh mẫu <?= $embeddingId ?>" style="width: 100%; border-radius: 6px; overflow: hidden; border: none; padding: 0; background: none; cursor: zoom-in; display: block;">
                                            <img src="/?action=face_image&amp;id=<?= $embeddingId ?>" alt="Mẫu <?= $idx + 1 ?>" style="width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 6px; display: block;" loading="lazy">
                                        </button>
                                    <?php else: ?>
                                        <div style="width: 100%; aspect-ratio: 1; background: #f1f5f9; display: flex; align-items: center; justify-content: center; font-size: 11px; color: #64748b; border-radius: 6px;">
                                            Vector
                                        </div>
                                    <?php endif; ?>
                                    <p style="margin: 4px 0 0; font-size: 11px; font-weight: 700; color: #334155;">#<?= $idx + 1 ?></p>
                                    <?php if ($timeStr): ?>
                                        <span style="font-size: 10px; color: #94a3b8; display: block;"><?= $timeStr ?></span>
                                    <?php endif; ?>
                                </article>
                            <?php endforeach; ?>
                        </div>
                    <?php endif; ?>
                </section>
            <?php endif; ?>

            <!-- Khối 2: Danh bạ nhân viên để chọn nhanh -->
            <section class="face-reg-card" aria-labelledby="employee-directory-title">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; flex-wrap: wrap; gap: 8px;">
                    <div>
                        <h2 id="employee-directory-title" style="margin: 0; font-size: 16px; font-weight: 700; color: #0f172a;">
                            Danh sách nhân viên (<?= count($employees) ?>)
                        </h2>
                        <span style="font-size: 12px; color: #64748b;">Chọn nhân viên để xem hoặc đăng ký lại.</span>
                    </div>
                    <input id="employee-table-search" type="search" placeholder="Tìm tên hoặc mã NV..." style="padding: 6px 12px; font-size: 13px; border-radius: 8px; border: 1px solid #cbd5e1; width: 170px;">
                </div>

                <div class="table-scroll" style="max-height: 440px; overflow-y: auto; border: 1px solid #f1f5f9; border-radius: 8px;">
                    <table class="face-emp-table" style="font-size: 13px; width: 100%; border-collapse: collapse;">
                        <thead style="background: #f8fafc; position: sticky; top: 0; z-index: 1;">
                            <tr style="border-bottom: 1px solid #e2e8f0; color: #475467; text-align: left;">
                                <th>Mã NV</th>
                                <th>Họ tên</th>
                                <th>Khuôn mặt</th>
                                <th style="text-align: right;">Chọn</th>
                            </tr>
                        </thead>
                        <tbody id="employee-table-body">
                            <?php foreach ($employees as $emp): ?>
                                <?php
                                $eId = (int)$emp['MaNV'];
                                $eCode = 'NV' . str_pad((string)$eId, 3, '0', STR_PAD_LEFT);
                                $eName = (string)($emp['HoTen'] ?? '');
                                $eCount = (int)($emp['FaceEmbeddingCount'] ?? 0);
                                $isCurrent = $eId === $selectedId;
                                ?>
                                <tr class="employee-row-item <?= $isCurrent ? 'is-selected' : '' ?>" style="border-bottom: 1px solid #f1f5f9; <?= $isCurrent ? 'background: #eff6ff;' : '' ?>" data-search="<?= $h(strtolower($eCode . ' ' . $eName)) ?>">
                                    <td style="font-weight: 600; color: #1e293b;"><?= $h($eCode) ?></td>
                                    <td><?= $h($eName) ?></td>
                                    <td>
                                        <?php if ($eCount >= 5): ?>
                                            <span style="color: #16a34a; font-weight: 600; font-size: 12px;">✓ 5 mẫu</span>
                                        <?php elseif ($eCount > 0): ?>
                                            <span style="color: #d97706; font-weight: 600; font-size: 12px;"><?= $eCount ?> mẫu</span>
                                        <?php else: ?>
                                            <span style="color: #94a3b8; font-size: 12px;">Chưa có</span>
                                        <?php endif; ?>
                                    </td>
                                    <td style="text-align: right;">
                                        <?php if ($isCurrent): ?>
                                            <span style="font-weight: 700; color: #2563eb; font-size: 12px;">Đang chọn</span>
                                        <?php else: ?>
                                            <a class="button button--secondary button--small" href="/?action=face_registration&amp;id=<?= $eId ?>" style="padding: 3px 10px; font-size: 12px;">Chọn</a>
                                        <?php endif; ?>
                                    </td>
                                </tr>
                            <?php endforeach; ?>
                        </tbody>
                    </table>
                </div>
            </section>
        </div>
    </div>

    <!-- Modal Xem phóng to ảnh mẫu (Lightbox) -->
    <dialog class="face-lightbox" data-face-lightbox aria-label="Ảnh mẫu khuôn mặt">
        <div class="face-lightbox-toolbar" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <span data-face-lightbox-title style="font-weight: 600;">Ảnh mẫu khuôn mặt</span>
            <button class="button button--secondary button--small" type="button" data-face-lightbox-close>Đóng</button>
        </div>
        <img data-face-lightbox-image alt="Ảnh mẫu khuôn mặt phóng lớn" style="width: 100%; max-height: calc(100vh - 120px); object-fit: contain; border-radius: 8px;">
    </dialog>
</main>

<script src="/public/js/face_registration_page.js" defer></script>
<?php require __DIR__ . '/layout/footer.php'; ?>

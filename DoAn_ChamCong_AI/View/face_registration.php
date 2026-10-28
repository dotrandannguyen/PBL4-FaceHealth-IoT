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
/* ── Giao diện Tinh gọn Một Màn Hình (Single Viewport - Không cuộn trang) ── */
.face-compact-layout {
    display: grid;
    grid-template-columns: minmax(0, 1.6fr) minmax(350px, 1fr);
    gap: 14px;
    align-items: stretch;
}

@media (max-width: 992px) {
    .face-compact-layout {
        grid-template-columns: 1fr;
    }
}

.face-compact-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 12px 14px;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}

/* Nút chuyển đổi thiết bị quét */
.face-device-pills {
    display: inline-flex;
    background: #e2e8f0;
    padding: 2px;
    border-radius: 6px;
    gap: 2px;
}

.face-device-btn {
    border: none;
    padding: 4px 10px;
    border-radius: 5px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s ease;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: transparent;
    color: #475467;
}

.face-device-btn:hover {
    color: #0f172a;
}

.face-device-btn.is-active {
    background: #2563eb;
    color: #ffffff;
    box-shadow: 0 1px 2px rgba(37, 99, 235, 0.2);
}

/* Camera Viewport: Chiều cao chuẩn 330px vừa vặn hoàn hảo */
.face-compact-viewport {
    position: relative;
    width: 100%;
    height: 330px;
    border-radius: 10px;
    overflow: hidden;
    background: #060911;
    border: 2px solid #1e293b;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-top: 8px;
}

.face-compact-camera-img {
    width: 100%;
    height: 100%;
    object-fit: contain;
    background: #000000;
    display: block;
}

/* Khung ngắm Reticle Overlay (Tích hợp HUD) */
.face-reticle-overlay {
    position: absolute;
    inset: 0;
    pointer-events: none;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    padding: 10px 12px;
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
    gap: 5px;
    padding: 3px 8px;
    background: rgba(15, 23, 42, 0.8);
    backdrop-filter: blur(4px);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 14px;
    font-size: 11px;
    font-weight: 600;
    color: #f8fafc;
}

.face-reticle-live-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #ef4444;
    box-shadow: 0 0 6px #ef4444;
    animation: livePulse 1.5s infinite ease-in-out;
}

@keyframes livePulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.35; transform: scale(0.8); }
}

/* Tâm định vị khuôn mặt */
.face-reticle-center {
    position: absolute;
    top: 48%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 200px;
    height: 250px;
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
    stroke-width: 2.2;
    stroke-dasharray: 6 5;
    transition: all 0.25s ease;
}

.face-reticle-corner {
    fill: none;
    stroke: rgba(56, 189, 248, 0.85);
    stroke-width: 3;
    stroke-linecap: round;
    transition: all 0.25s ease;
}

.face-compact-viewport.is-matched .face-reticle-oval {
    stroke: #22c55e;
    stroke-dasharray: none;
    stroke-width: 3;
    filter: drop-shadow(0 0 8px rgba(34, 197, 94, 0.85));
}

.face-compact-viewport.is-matched .face-reticle-corner {
    stroke: #22c55e;
    stroke-width: 4;
    filter: drop-shadow(0 0 6px rgba(34, 197, 94, 0.9));
}

/* Thanh chỉ dẫn HUD nằm ngay dưới đáy camera (tiết kiệm diện tích) */
.face-reticle-hud-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: rgba(15, 23, 42, 0.85);
    backdrop-filter: blur(6px);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 8px;
    padding: 6px 12px;
    gap: 8px;
}

/* Dải 5 bước tư thế gọn gàng */
.face-pose-strip {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 6px;
    list-style: none;
    padding: 0;
    margin: 8px 0 0;
}

.face-pose-step {
    text-align: center;
    padding: 6px 2px;
    border-radius: 6px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    font-size: 11px;
    transition: all 0.2s ease;
}

.face-pose-step .step-title {
    font-weight: 600;
    color: #334155;
    display: block;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.face-pose-step .step-status {
    font-size: 10px;
    color: #94a3b8;
    display: block;
    margin-top: 1px;
}

.face-pose-step.is-active {
    background: #eff6ff;
    border-color: #3b82f6;
    box-shadow: 0 0 0 1px #3b82f6;
}

.face-pose-step.is-active .step-title {
    color: #1d4ed8;
}

.face-pose-step.is-active .step-status {
    color: #2563eb;
    font-weight: 600;
}

.face-pose-step.is-complete {
    background: #ecfdf5;
    border-color: #10b981;
}

.face-pose-step.is-complete .step-title {
    color: #047857;
}

.face-pose-step.is-complete .step-status {
    color: #059669;
    font-weight: 600;
}

/* Bảng nhân viên nhỏ gọn có cuộn bên trong */
.face-compact-table th,
.face-compact-table td {
    padding: 6px 8px;
    font-size: 12px;
}
</style>

<main class="page-container page-container--wide" style="padding-top: 8px; padding-bottom: 12px;">
    <!-- 1. Thanh tiêu đề Compact trên 1 dòng -->
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px;">
        <div style="display: flex; align-items: center; gap: 10px;">
            <h1 style="font-size: 19px; font-weight: 700; color: #0f172a; margin: 0;">
                Đăng ký nhận diện khuôn mặt
            </h1>
            <?php if ($selectedId !== null): ?>
                <span class="status-pill status-pill--registered" style="font-size: 12px; padding: 2px 10px;">
                    <?= $h($selectedCode) ?> · <?= $h($selectedName) ?>
                </span>
            <?php endif; ?>
        </div>
        <div style="display: flex; gap: 8px; align-items: center;">
            <div class="status-pill <?= $aiReady ? 'status-pill--registered' : 'status-pill--pending' ?>" style="font-size: 12px; padding: 2px 10px;">
                <span aria-hidden="true"></span>
                AI Service: <?= $aiReady ? 'Sẵn sàng (buffalo_sc)' : 'Chưa bật (Cổng 5001)' ?>
            </div>
            <a class="button button--secondary button--small" href="/" style="padding: 3px 10px; font-size: 12px;">Danh sách nhân viên</a>
        </div>
    </div>

    <!-- Cảnh báo nếu AI Service chưa bật -->
    <?php if (!$aiReady): ?>
        <div class="notice notice--warning" style="margin: 0 0 8px; padding: 6px 12px; font-size: 12px; display: flex; justify-content: space-between; align-items: center;">
            <span>⚠️ <strong>AI Service chưa bật (Cổng 5001):</strong> Hãy chạy file <code>run_ai_service.bat</code> trong thư mục dự án rồi tải lại trang.</span>
            <a class="button button--secondary button--small" href="javascript:location.reload()" style="padding: 2px 8px; font-size: 11px;">🔄 Thử lại</a>
        </div>
    <?php endif; ?>

    <!-- 2. Bố cục 2 cột gọn gàng, khớp trọn 1 màn hình -->
    <div class="face-compact-layout">
        <!-- ════════ CỘT TRÁI: STUDIO CAMERA QUÉT (GỌN GÀNG) ════════ -->
        <section class="face-compact-card" aria-labelledby="studio-heading" style="display: flex; flex-direction: column;">
            <?php if ($selectedId === null): ?>
                <div class="empty-state" style="padding: 48px 16px; text-align: center;">
                    <div style="font-size: 15px; font-weight: 600; color: #334155;">Chưa chọn nhân viên</div>
                    <div style="color: #64748b; font-size: 13px; margin-top: 4px;">
                        Vui lòng chọn nhân viên từ bảng danh sách bên phải để quét khuôn mặt.
                    </div>
                </div>
            <?php else: ?>
                <!-- Hàng điều khiển 1 dòng: Chọn NV + Chọn Thiết bị + Gợi ý -->
                <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap;">
                    <div style="display: flex; align-items: center; gap: 8px; flex: 1; min-width: 220px;">
                        <span style="font-size: 12px; font-weight: 600; color: #475467; white-space: nowrap;">Nhân viên:</span>
                        <select id="employee-select-picker" class="input" style="padding: 4px 8px; border-radius: 6px; border: 1px solid #cbd5e1; font-size: 12px; font-weight: 500; height: 30px; width: 100%; max-width: 250px;" onchange="if(this.value) window.location.href='/?action=face_registration&id=' + this.value;">
                            <?php foreach ($employees as $emp): ?>
                                <?php
                                $eId = (int)$emp['MaNV'];
                                $eCode = 'NV' . str_pad((string)$eId, 3, '0', STR_PAD_LEFT);
                                $eName = (string)($emp['HoTen'] ?? '');
                                $eCount = (int)($emp['FaceEmbeddingCount'] ?? 0);
                                $selectedAttr = $eId === $selectedId ? 'selected' : '';
                                $statusText = $eCount > 0 ? " [{$eCount} mẫu]" : ' [Chưa có]';
                                ?>
                                <option value="<?= $eId ?>" <?= $selectedAttr ?>>
                                    <?= $h($eCode) ?> - <?= $h($eName) ?><?= $statusText ?>
                                </option>
                            <?php endforeach; ?>
                        </select>
                    </div>

                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 12px; font-weight: 600; color: #475467; white-space: nowrap;">Thiết bị:</span>
                        <div class="face-device-pills">
                            <button type="button" class="face-device-btn <?= $cameraSource === 'local' ? 'is-active' : '' ?>" data-camera-device="local">
                                📷 Webcam
                            </button>
                            <button type="button" class="face-device-btn <?= $cameraSource === 'esp32' ? 'is-active' : '' ?>" data-camera-device="esp32">
                                📡 ESP32-CAM
                            </button>
                        </div>
                    </div>
                </div>

                <div id="camera-device-hint" style="font-size: 11px; color: #64748b; font-family: monospace; margin-top: 4px;">
                    <?= $cameraSource === 'esp32' ? '📡 Luồng ESP32: http://esp32cam.local:81/stream' : '📷 Nguồn Webcam: Camera ID 0 (DirectShow)' ?>
                </div>

                <!-- Khung hình Camera Viewport Compact (330px) -->
                <div class="face-enrollment-root" data-face-enrollment data-employee-id="<?= $selectedId ?>" data-csrf="<?= $h($csrfToken) ?>" data-face-count="<?= $faceCount ?>" data-camera-source="<?= $h($cameraSource) ?>" data-ai-ready="<?= $aiReady ? '1' : '0' ?>">
                    <div class="face-compact-viewport" data-face-viewport>
                        <img class="face-compact-camera-img" data-face-camera alt="Khung hình camera đăng ký khuôn mặt" hidden>

                        <div class="face-hero-empty" data-face-camera-empty style="color: #94a3b8; text-align: center; padding: 20px;">
                            <svg style="width: 44px; height: 44px; margin: 0 auto 8px; stroke: #475467; fill: none;" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.6" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"/>
                            </svg>
                            <div style="font-size: 14px; font-weight: 600; color: #e2e8f0;">Camera ở chế độ chờ</div>
                            <div style="font-size: 12px; color: #94a3b8; margin-top: 2px;">
                                Bấm <strong>"Bắt đầu đăng ký"</strong> bên dưới để mở camera và quét 5 góc khuôn mặt.
                            </div>
                        </div>

                        <!-- Khung ngắm Viewfinder HUD Overlay -->
                        <div class="face-reticle-overlay" data-face-reticle hidden>
                            <div class="face-reticle-top">
                                <span class="face-reticle-live-badge">
                                    <span class="face-reticle-live-dot"></span>
                                    <span>LIVE</span>
                                    <span style="color: #64748b; margin: 0 1px;">·</span>
                                    <span data-reticle-source-label><?= $cameraSource === 'esp32' ? 'ESP32-CAM' : 'WEBCAM' ?></span>
                                </span>
                                <span style="font-size: 11px; color: rgba(255,255,255,0.7); font-family: monospace; background: rgba(0,0,0,0.5); padding: 2px 6px; border-radius: 4px;">
                                    640x480 · ArcFace 512-dim
                                </span>
                            </div>

                            <!-- Tâm bầu dục định vị khuôn mặt -->
                            <div class="face-reticle-center">
                                <svg viewBox="0 0 200 250">
                                    <path class="face-reticle-corner" d="M 15 35 L 15 15 L 35 15" />
                                    <path class="face-reticle-corner" d="M 165 15 L 185 15 L 185 35" />
                                    <path class="face-reticle-corner" d="M 15 215 L 15 235 L 35 235" />
                                    <path class="face-reticle-corner" d="M 165 235 L 185 235 L 185 215" />
                                    <ellipse class="face-reticle-oval" cx="100" cy="125" rx="68" ry="94" />
                                </svg>
                            </div>

                            <!-- Thanh HUD đáy: Hướng dẫn tư thế và đèn báo chuẩn -->
                            <div class="face-reticle-hud-bar">
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <strong class="face-enrollment-step" data-face-step style="font-size: 12px; color: #38bdf8; white-space: nowrap;">
                                        Bước 1/5: Chính diện
                                    </strong>
                                    <span class="face-enrollment-feedback" data-face-feedback style="font-size: 11px; color: #e2e8f0;" data-reticle-hint>
                                        Nhìn thẳng vào tâm camera, giữ nét mặt tự nhiên.
                                    </span>
                                </div>
                                <div id="pose-match-indicator" style="display: none; align-items: center; padding: 2px 8px; border-radius: 12px; background: #22c55e; color: #ffffff; font-weight: 700; font-size: 11px; white-space: nowrap;">
                                    ✓ Khớp tư thế! Giữ yên...
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Dải 5 bước tư thế thu nhỏ (chiếm ~36px) -->
                    <ol class="face-pose-strip" data-face-pose-list>
                        <li class="face-pose-step" data-pose="frontal">
                            <span class="step-title">1. Chính diện</span>
                            <span class="step-status" data-pose-status>Chờ chụp</span>
                        </li>
                        <li class="face-pose-step" data-pose="left">
                            <span class="step-title">2. Nghiêng trái</span>
                            <span class="step-status" data-pose-status>Chờ chụp</span>
                        </li>
                        <li class="face-pose-step" data-pose="right">
                            <span class="step-title">3. Nghiêng phải</span>
                            <span class="step-status" data-pose-status>Chờ chụp</span>
                        </li>
                        <li class="face-pose-step" data-pose="up">
                            <span class="step-title">4. Ngẩng nhẹ</span>
                            <span class="step-status" data-pose-status>Chờ chụp</span>
                        </li>
                        <li class="face-pose-step" data-pose="down">
                            <span class="step-title">5. Cúi nhẹ</span>
                            <span class="step-status" data-pose-status>Chờ chụp</span>
                        </li>
                    </ol>

                    <!-- Thanh nút bấm điều khiển (gọn gàng) -->
                    <div style="display: flex; gap: 8px; margin-top: 8px; align-items: center; flex-wrap: wrap;">
                        <button class="button button--primary" type="button" data-face-start style="padding: 7px 18px; font-size: 13px; font-weight: 600;">
                            <?= $faceCount > 0 ? '🔄 Đăng ký lại (5 góc)' : '📸 Bắt đầu đăng ký' ?>
                        </button>
                        <button class="button button--secondary" type="button" data-face-cancel hidden style="padding: 7px 14px; font-size: 13px;">
                            ⏸️ Hủy
                        </button>
                        <button class="button button--primary" type="button" data-face-complete disabled hidden style="padding: 7px 18px; font-size: 13px; font-weight: 600; background: #16a34a; border-color: #15803d;">
                            💾 Lưu 5 mẫu
                        </button>
                        <?php if ($faceCount > 0): ?>
                            <button class="button button--danger" type="button" data-face-delete style="margin-left: auto; padding: 6px 12px; font-size: 12px;">
                                🗑️ Xóa mẫu đã lưu
                            </button>
                        <?php endif; ?>
                    </div>

                    <p class="notice face-enrollment-result" data-face-result role="status" style="margin-top: 8px; padding: 6px 10px; font-size: 12px;" hidden></p>
                </div>
            <?php endif; ?>
        </section>

        <!-- ════════ CỘT PHẢI: MẪU ĐÃ LƯU & DANH BẠ NHÂN VIÊN ════════ -->
        <div style="display: flex; flex-direction: column; gap: 10px;">
            <!-- Khối 1: Mẫu khuôn mặt hiện có (Dải 5 ảnh nhỏ gọn ~85px) -->
            <?php if ($selectedId !== null): ?>
                <section class="face-compact-card" aria-labelledby="sample-gallery-title" style="padding: 10px 12px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <span id="sample-gallery-title" style="font-size: 13px; font-weight: 700; color: #0f172a;">
                            Mẫu đã lưu (<?= $faceCount ?>/5)
                        </span>
                        <?php if ($faceCount >= 5): ?>
                            <span style="font-size: 11px; color: #16a34a; font-weight: 600;">✓ Đủ 5 góc</span>
                        <?php elseif ($faceCount > 0): ?>
                            <span style="font-size: 11px; color: #d97706; font-weight: 600;">Thiếu mẫu</span>
                        <?php else: ?>
                            <span style="font-size: 11px; color: #94a3b8;">Chưa đăng ký</span>
                        <?php endif; ?>
                    </div>

                    <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px;">
                        <?php for ($slot = 0; $slot < 5; $slot++): ?>
                            <?php
                            $sample = $faceSamples[$slot] ?? null;
                            $hasImg = $sample !== null && ((int)($sample['HasImage'] ?? 0) === 1);
                            $embId = $sample !== null ? (int)$sample['MaEmbedding'] : null;
                            ?>
                            <div style="text-align: center; border: 1px solid #e2e8f0; border-radius: 6px; padding: 3px; background: #ffffff;">
                                <?php if ($hasImg && $embId !== null): ?>
                                    <button class="face-sample-image" type="button" data-face-preview="/?action=face_image&amp;id=<?= $embId ?>" aria-label="Xem ảnh mẫu" style="width: 100%; border-radius: 4px; overflow: hidden; border: none; padding: 0; background: none; cursor: zoom-in; display: block;">
                                        <img src="/?action=face_image&amp;id=<?= $embId ?>" alt="Góc <?= $slot + 1 ?>" style="width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 4px; display: block;" loading="lazy">
                                    </button>
                                <?php elseif ($sample !== null): ?>
                                    <div style="width: 100%; aspect-ratio: 1; background: #eff6ff; display: flex; align-items: center; justify-content: center; font-size: 9px; color: #2563eb; border-radius: 4px; font-weight: 600;">Vector</div>
                                <?php else: ?>
                                    <div style="width: 100%; aspect-ratio: 1; background: #f8fafc; border: 1px dashed #cbd5e1; display: flex; align-items: center; justify-content: center; font-size: 9px; color: #94a3b8; border-radius: 4px;">Trống</div>
                                <?php endif; ?>
                                <span style="font-size: 9px; font-weight: 600; color: #64748b; display: block; margin-top: 1px;">#<?= $slot + 1 ?></span>
                            </div>
                        <?php endfor; ?>
                    </div>
                </section>
            <?php endif; ?>

            <!-- Khối 2: Danh bạ nhân viên gọn gàng có cuộn nội bộ -->
            <section class="face-compact-card" aria-labelledby="employee-directory-title" style="flex: 1; display: flex; flex-direction: column;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; gap: 8px;">
                    <span id="employee-directory-title" style="font-size: 13px; font-weight: 700; color: #0f172a; white-space: nowrap;">
                        Nhân viên (<?= count($employees) ?>)
                    </span>
                    <input id="employee-table-search" type="search" placeholder="Tìm tên / mã NV..." style="padding: 3px 8px; font-size: 12px; border-radius: 6px; border: 1px solid #cbd5e1; height: 26px; width: 140px;">
                </div>

                <div class="table-scroll" style="max-height: 290px; overflow-y: auto; border: 1px solid #f1f5f9; border-radius: 6px;">
                    <table class="face-compact-table" style="width: 100%; border-collapse: collapse;">
                        <thead style="background: #f8fafc; position: sticky; top: 0; z-index: 1;">
                            <tr style="border-bottom: 1px solid #e2e8f0; color: #475467; text-align: left;">
                                <th>Mã</th>
                                <th>Họ tên</th>
                                <th>Mẫu</th>
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
                                <tr class="employee-row-item <?= $isCurrent ? 'is-selected' : '' ?>" style="border-bottom: 1px solid #f8fafc; <?= $isCurrent ? 'background: #eff6ff;' : '' ?>" data-search="<?= $h(strtolower($eCode . ' ' . $eName)) ?>">
                                    <td style="font-weight: 600; color: #1e293b;"><?= $h($eCode) ?></td>
                                    <td><?= $h($eName) ?></td>
                                    <td>
                                        <?php if ($eCount >= 5): ?>
                                            <span style="color: #16a34a; font-weight: 600;">✓ 5</span>
                                        <?php elseif ($eCount > 0): ?>
                                            <span style="color: #d97706; font-weight: 600;"><?= $eCount ?></span>
                                        <?php else: ?>
                                            <span style="color: #94a3b8;">0</span>
                                        <?php endif; ?>
                                    </td>
                                    <td style="text-align: right;">
                                        <?php if ($isCurrent): ?>
                                            <span style="font-weight: 700; color: #2563eb;">Đang chọn</span>
                                        <?php else: ?>
                                            <a class="button button--secondary button--small" href="/?action=face_registration&amp;id=<?= $eId ?>" style="padding: 2px 6px; font-size: 11px;">Chọn</a>
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
        <div class="face-lightbox-toolbar" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <span data-face-lightbox-title style="font-weight: 600; font-size: 13px;">Ảnh mẫu khuôn mặt</span>
            <button class="button button--secondary button--small" type="button" data-face-lightbox-close style="padding: 2px 8px; font-size: 12px;">Đóng</button>
        </div>
        <img data-face-lightbox-image alt="Ảnh mẫu khuôn mặt phóng lớn" style="width: 100%; max-height: calc(100vh - 100px); object-fit: contain; border-radius: 6px;">
    </dialog>
</main>

<script src="/public/js/face_registration_page.js" defer></script>
<?php require __DIR__ . '/layout/footer.php'; ?>

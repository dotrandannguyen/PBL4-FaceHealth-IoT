<?php 
declare(strict_types=1);
require __DIR__ . '/layout/header.php'; 

$h = static fn(mixed $value): string => htmlspecialchars((string)($value ?? ''), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); 
$defaultAvatar = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64' viewBox='0 0 24 24' fill='%2394a3b8'><circle cx='12' cy='8' r='4'/><path d='M4 20c0-4 4-6 8-6s8 2 8 6'/></svg>";
$isOut = ($latest['PunchType'] ?? 'IN') === 'OUT';
$hasImg = $isOut ? ($latest['HasImageOut'] ?? 0) : ($latest['HasImageIn'] ?? 0);
$imgKind = $isOut ? 'attendance_image_out' : 'attendance_image_in';
$avatarSrc = $hasImg ? "/?action={$imgKind}&id=" . (int)($latest['MaCC'] ?? 0) : $defaultAvatar;
?>

<style>
/* ── Giao diện Chấm công Trực tiếp Tối giản Đơn sắc ── */
.live-kiosk-page {
    max-width: 1240px;
    margin: 0 auto;
    padding: 16px 20px;
    box-sizing: border-box;
}

.live-kiosk-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px solid #e2e8f0;
    gap: 12px;
    flex-wrap: wrap;
}

.live-kiosk-title {
    font-size: 18px;
    font-weight: 700;
    color: #0f172a;
    margin: 0 0 4px 0;
}

.live-kiosk-subtitle {
    font-size: 13px;
    color: #64748b;
    margin: 0;
}

.live-kiosk-meta {
    display: flex;
    align-items: center;
    gap: 10px;
}

.live-kiosk-clock {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 13px;
    font-weight: 600;
    color: #0f172a;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    padding: 4px 10px;
    border-radius: 6px;
}

.live-kiosk-status-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    font-size: 12px;
    color: #334155;
    font-weight: 500;
}

.live-kiosk-status-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #0f172a;
}

/* ── Bố cục 2 cột chính ── */
.live-kiosk-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.35fr) minmax(360px, 1fr);
    gap: 16px;
    margin-bottom: 20px;
}

@media (max-width: 900px) {
    .live-kiosk-grid {
        grid-template-columns: 1fr;
    }
}

.live-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
    overflow: hidden;
    display: flex;
    flex-direction: column;
}

.live-card-header {
    padding: 10px 14px;
    background: #f8fafc;
    border-bottom: 1px solid #e2e8f0;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.live-card-title {
    font-size: 13px;
    font-weight: 600;
    color: #0f172a;
    margin: 0;
}

.live-card-badge {
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 4px;
    text-transform: uppercase;
}

.live-card-badge-dark {
    background: #0f172a;
    color: #ffffff;
}

.live-card-badge-outline {
    background: #ffffff;
    color: #334155;
    border: 1px solid #cbd5e1;
}

/* ── Khung Camera ── */
.live-camera-view {
    position: relative;
    background: #090d16;
    min-height: 380px;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
}

.live-camera-stream {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
}

.live-camera-hud-tl, .live-camera-hud-tr, .live-camera-hud-bl, .live-camera-hud-br {
    position: absolute;
    width: 24px;
    height: 24px;
    pointer-events: none;
    border-color: #64748b;
    border-style: solid;
}

.live-camera-hud-tl { top: 16px; left: 16px; border-width: 2px 0 0 2px; }
.live-camera-hud-tr { top: 16px; right: 16px; border-width: 2px 2px 0 0; }
.live-camera-hud-bl { bottom: 16px; left: 16px; border-width: 0 0 2px 2px; }
.live-camera-hud-br { bottom: 16px; right: 16px; border-width: 0 2px 2px 0; }

.live-camera-caption {
    position: absolute;
    bottom: 12px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(15, 23, 42, 0.85);
    color: #cbd5e1;
    font-size: 12px;
    padding: 4px 12px;
    border-radius: 4px;
    border: 1px solid #334155;
    pointer-events: none;
    white-space: nowrap;
}

/* ── Thẻ Thông Tin Chấm Công ── */
.live-card-body {
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 14px;
    flex: 1;
}

.live-person-row {
    display: flex;
    gap: 14px;
    align-items: center;
}

.live-avatar {
    width: 90px;
    height: 90px;
    border-radius: 8px;
    object-fit: cover;
    border: 1px solid #cbd5e1;
    background: #f8fafc;
    flex-shrink: 0;
}

.live-person-info {
    flex: 1;
    min-width: 0;
}

.live-person-code {
    display: inline-block;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 11px;
    font-weight: 600;
    color: #475569;
    background: #f1f5f9;
    padding: 2px 6px;
    border-radius: 4px;
    margin-bottom: 3px;
}

.live-person-name {
    font-size: 16px;
    font-weight: 700;
    color: #0f172a;
    margin: 0 0 4px 0;
    line-height: 1.3;
}

.live-person-shift {
    font-size: 12px;
    color: #64748b;
    margin-bottom: 2px;
}

.live-person-time {
    font-size: 12px;
    color: #475569;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

/* ── Chỉ số sinh trắc học ── */
.live-metrics-grid {
    display: grid;
    grid-template-columns: 1fr 1fr 1.1fr;
    gap: 8px;
}

.live-metric-box {
    border: 1px solid #e2e8f0;
    background: #fafafa;
    border-radius: 6px;
    padding: 10px 12px;
    text-align: center;
}

.live-metric-label {
    font-size: 11px;
    font-weight: 500;
    color: #64748b;
    margin-bottom: 2px;
}

.live-metric-val {
    font-size: 20px;
    font-weight: 700;
    color: #0f172a;
    line-height: 1.2;
}

.live-metric-unit {
    font-size: 12px;
    font-weight: 500;
    color: #64748b;
}

.live-prompt-footer {
    padding: 10px 14px;
    background: #f8fafc;
    border-top: 1px solid #e2e8f0;
    font-size: 12px;
    color: #64748b;
    text-align: center;
}

/* ── Bảng Lịch Sử Hôm Nay ── */
.live-table-section {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 14px;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}

.live-table-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
}

.live-table-title {
    font-size: 13px;
    font-weight: 600;
    color: #0f172a;
    margin: 0;
}

.live-table-link {
    font-size: 12px;
    color: #0f172a;
    text-decoration: none;
    font-weight: 500;
}

.live-table-link:hover {
    text-decoration: underline;
}

.live-mini-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
}

.live-mini-table th {
    background: #f8fafc;
    color: #475569;
    font-weight: 600;
    text-align: left;
    padding: 8px 10px;
    border-bottom: 1px solid #e2e8f0;
    font-size: 11px;
}

.live-mini-table td {
    padding: 8px 10px;
    border-bottom: 1px solid #f1f5f9;
    color: #334155;
    vertical-align: middle;
}

.live-mini-table tr:hover td {
    background: #fafafa;
}

.live-table-tag {
    display: inline-block;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
}

.live-table-tag-in {
    background: #0f172a;
    color: #ffffff;
}

.live-table-tag-out {
    background: #ffffff;
    color: #334155;
    border: 1px solid #cbd5e1;
}
</style>

<main class="page-container live-kiosk-page">
    <!-- TIÊU ĐỀ TỐI GIẢN -->
    <header class="live-kiosk-header">
        <div>
            <h1 class="live-kiosk-title">Chấm công trực tiếp</h1>
            <p class="live-kiosk-subtitle">Nhận diện khuôn mặt &amp; sinh trắc học IoT</p>
        </div>
        <div class="live-kiosk-meta">
            <div class="live-kiosk-clock" id="liveClock">--:--:--</div>
            <div class="live-kiosk-status-pill">
                <span class="live-kiosk-status-dot"></span>
                <span>ESP32-CAM</span>
            </div>
            <div class="live-kiosk-status-pill">
                <span class="live-kiosk-status-dot" style="background:#475569;"></span>
                <span>MAX30102</span>
            </div>
        </div>
    </header>

    <!-- KHUNG CHÍNH (CAMERA + THẺ KẾT QUẢ) -->
    <div class="live-kiosk-grid">
        
        <!-- CỘT 1: KHUNG CAMERA (TỰ ĐỘNG BẬT KHI CHẠM TAY) -->
        <section class="live-card" aria-label="Camera trực tiếp">
            <div class="live-card-header">
                <h2 class="live-card-title">Camera nhận diện</h2>
                <span id="cameraStatusText" style="font-size: 11px; color: #64748b;">Chế độ chờ (Tắt)</span>
            </div>
            
            <div class="live-camera-view" id="cameraContainer">
                <!-- ẢNH KHUÔN MẶT KHI KÍCH HOẠT -->
                <img id="liveStreamImg" 
                     class="live-camera-stream"
                     alt="Ảnh nhận diện" 
                     style="display: none;">
                
                <div class="live-camera-hud-tl camera-active-element" style="display: none;"></div>
                <div class="live-camera-hud-tr camera-active-element" style="display: none;"></div>
                <div class="live-camera-hud-bl camera-active-element" style="display: none;"></div>
                <div class="live-camera-hud-br camera-active-element" style="display: none;"></div>
                
                <!-- Khung Chờ (Camera Tắt khi chưa chạm tay) -->
                <div id="cameraStandbyBox" style="text-align: center; color: #64748b; padding: 24px; max-width: 320px;">
                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#475569" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom: 10px; display: inline-block;">
                        <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path>
                        <circle cx="12" cy="13" r="4"></circle>
                        <line x1="1" y1="1" x2="23" y2="23"></line>
                    </svg>
                    <div style="font-size: 13px; font-weight: 600; color: #94a3b8; margin-bottom: 4px;">Camera ở chế độ chờ (Tắt)</div>
                    <div style="font-size: 12px; color: #475569; line-height: 1.4;">Chạm ngón tay vào cảm biến MAX30102 để kích hoạt</div>
                </div>

                <div class="live-camera-caption" id="cameraCaption">
                    Chế độ chờ · Sẵn sàng nhận ngón tay
                </div>
            </div>
        </section>

        <!-- CỘT 2: THẺ KẾT QUẢ CHẤM CÔNG -->
        <section class="live-card" id="punchCard" aria-label="Kết quả lượt chấm công">
            <div class="live-card-header">
                <h2 class="live-card-title">Lượt chấm công</h2>
                <span id="punchTypeBadge" class="live-card-badge <?= $isOut ? 'live-card-badge-outline' : 'live-card-badge-dark' ?>">
                    <?= $isOut ? 'Check-out' : 'Check-in' ?>
                </span>
            </div>

            <div class="live-card-body">
                <div class="live-person-row">
                    <img id="employeeAvatar" 
                         class="live-avatar"
                         src="<?= $h($avatarSrc) ?>" 
                         alt="Ảnh nhân viên"
                         onerror="this.onerror=null;this.src='<?= $defaultAvatar ?>';">

                    <div class="live-person-info">
                        <span id="employeeCode" class="live-person-code">
                            NV<?= str_pad((string)(int)($latest['MaNV'] ?? 0), 3, '0', STR_PAD_LEFT) ?>
                        </span>
                        <h3 id="employeeName" class="live-person-name">
                            <?= $h($latest['HoTen'] ?? 'Chưa có lượt đo') ?>
                        </h3>
                        <div id="employeeShift" class="live-person-shift">
                            <?= $h($latest['TenCa'] ?? 'Ca làm việc') ?> · Đúng giờ
                        </div>
                        <div id="punchTime" class="live-person-time">
                            <?= $h($latest['ThoiGianMoiNhat'] ?? '--:--:--') ?>
                        </div>
                    </div>
                </div>

                <!-- CHỈ SỐ SINH TRẮC HỌC TỐI GIẢN -->
                <div class="live-metrics-grid">
                    <div class="live-metric-box">
                        <div class="live-metric-label">Nhịp tim</div>
                        <div class="live-metric-val">
                            <span id="valBpm"><?= (int)($latest['NhipTim'] ?? 75) ?></span>
                            <span class="live-metric-unit">bpm</span>
                        </div>
                    </div>

                    <div class="live-metric-box">
                        <div class="live-metric-label">SpO2</div>
                        <div class="live-metric-val">
                            <span id="valSpo2"><?= number_format((float)($latest['SpO2'] ?? 98.5), 1) ?></span><span class="live-metric-unit">%</span>
                        </div>
                    </div>

                    <div class="live-metric-box">
                        <div class="live-metric-label">Thể trạng</div>
                        <div class="live-metric-val" style="font-size: 14px; padding-top: 5px;">
                            <span id="valTheTrang"><?= $h($latest['TheTrangSK'] ?? $latest['TheTrangVao'] ?? 'Bình thường') ?></span>
                        </div>
                    </div>
                </div>
            </div>

            <div class="live-prompt-footer" id="livePromptFooter">
                Đặt ngón tay lên cảm biến MAX30102 để chấm công
            </div>
        </section>
    </div>

    <!-- BẢNG LỊCH SỬ CHẤM CÔNG GẦN ĐÂY -->
    <section class="live-table-section" aria-label="Lịch sử chấm công">
        <div class="live-table-header">
            <h2 class="live-table-title">Các lượt chấm công gần đây</h2>
            <a href="/?action=attendance" class="live-table-link">Xem tất cả &rarr;</a>
        </div>

        <div style="overflow-x: auto;">
            <table class="live-mini-table">
                <thead>
                    <tr>
                        <th style="width: 50px;">Ảnh</th>
                        <th style="width: 90px;">Mã NV</th>
                        <th>Họ tên</th>
                        <th style="width: 90px;">Loại</th>
                        <th>Ca làm việc</th>
                        <th style="width: 150px;">Thời gian</th>
                        <th style="width: 80px;">Nhịp tim</th>
                        <th style="width: 70px;">SpO2</th>
                        <th style="width: 100px;">Thể trạng</th>
                    </tr>
                </thead>
                <tbody id="recentPunchesBody">
                    <?php if ($recent === []): ?>
                        <tr><td colspan="9" style="text-align: center; color: #94a3b8; padding: 16px;">Chưa có lượt chấm công nào trong ngày.</td></tr>
                    <?php else: ?>
                        <?php foreach ($recent as $r): ?>
                            <?php 
                            $rowOut = ($r['PunchType'] ?? 'IN') === 'OUT';
                            $rowImgKind = $rowOut ? 'attendance_image_out' : 'attendance_image_in';
                            $rowHasPic = $rowOut ? ($r['HasImageOut'] ?? 0) : ($r['HasImageIn'] ?? 0);
                            $rowPic = $rowHasPic ? "/?action={$rowImgKind}&id=" . (int)$r['MaCC'] : $defaultAvatar;
                            ?>
                            <tr>
                                <td>
                                    <img src="<?= $h($rowPic) ?>" style="width: 32px; height: 32px; border-radius: 4px; object-fit: cover; border: 1px solid #e2e8f0;" onerror="this.onerror=null;this.src='<?= $defaultAvatar ?>';">
                                </td>
                                <td><span class="live-person-code">NV<?= str_pad((string)(int)$r['MaNV'], 3, '0', STR_PAD_LEFT) ?></span></td>
                                <td style="font-weight: 600; color: #0f172a;"><?= $h($r['HoTen']) ?></td>
                                <td>
                                    <span class="live-table-tag <?= $rowOut ? 'live-table-tag-out' : 'live-table-tag-in' ?>">
                                        <?= $rowOut ? 'Check-out' : 'Check-in' ?>
                                    </span>
                                </td>
                                <td><?= $h($r['TenCa'] ?? 'Ca chuẩn') ?></td>
                                <td style="font-family: monospace; font-size: 11px;"><?= $h($r['ThoiGianMoiNhat']) ?></td>
                                <td style="font-weight: 600;"><?= $r['NhipTim'] !== null ? ((int)$r['NhipTim'] . ' bpm') : '--' ?></td>
                                <td style="font-weight: 600;"><?= $r['SpO2'] !== null ? (number_format((float)$r['SpO2'], 1) . '%') : '--' ?></td>
                                <td><?= $h($r['TheTrangSK'] ?? $r['TheTrangVao'] ?? 'Bình thường') ?></td>
                            </tr>
                        <?php endforeach; ?>
                    <?php endif; ?>
                </tbody>
            </table>
        </div>
    </section>
</main>

<script>
// Đồng hồ thời gian thực
function updateClock() {
    const now = new Date();
    const h = String(now.getHours()).padStart(2, '0');
    const m = String(now.getMinutes()).padStart(2, '0');
    const s = String(now.getSeconds()).padStart(2, '0');
    const d = String(now.getDate()).padStart(2, '0');
    const mo = String(now.getMonth() + 1).padStart(2, '0');
    const y = now.getFullYear();
    const el = document.getElementById('liveClock');
    if (el) el.textContent = `${h}:${m}:${s} - ${d}/${mo}/${y}`;
}
setInterval(updateClock, 1000);
updateClock();

// Âm thanh nhẹ nhàng khi chấm công hoàn tất
function playMinimalBeep() {
    try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.type = 'sine';
        osc.frequency.setValueAtTime(659.25, audioCtx.currentTime); // E5
        gain.gain.setValueAtTime(0.08, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.25);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.25);
    } catch (e) {}
}

const DEFAULT_AVATAR = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64' viewBox='0 0 24 24' fill='%2394a3b8'><circle cx='12' cy='8' r='4'/><path d='M4 20c0-4 4-6 8-6s8 2 8 6'/></svg>";
let isCameraActive = false;
let lastPunchId = <?= (int)($latest['MaCC'] ?? 0) ?>;
let lastPunchType = "<?= $h($latest['PunchType'] ?? '') ?>";
let activeImageB64 = null;

function showCameraActive() {
    const img = document.getElementById('liveStreamImg');
    const standby = document.getElementById('cameraStandbyBox');
    const caption = document.getElementById('cameraCaption');
    const statusText = document.getElementById('cameraStatusText');
    const huds = document.querySelectorAll('.camera-active-element');
    const footer = document.getElementById('livePromptFooter');

    if (!isCameraActive) {
        isCameraActive = true;
        if (standby) standby.style.display = 'none';
        huds.forEach(el => el.style.display = 'block');
        if (caption) {
            caption.textContent = 'Đang nhận diện & Đo nhịp tim... Giữ yên ngón tay';
            caption.style.borderColor = '#0f172a';
        }
        if (statusText) {
            statusText.textContent = 'Đang hoạt động (Trực tiếp)';
            statusText.style.color = '#0f172a';
            statusText.style.fontWeight = '600';
        }
        if (footer) {
            footer.textContent = 'Đang đo nhịp tim & SpO2 (Giữ ngón tay khoảng 2-3 giây)...';
            footer.style.color = '#0f172a';
            footer.style.fontWeight = '600';
        }

        // Kích hoạt luồng Video MJPEG trực tiếp thời gian thực mượt mà từ ESP32-CAM
        if (img) {
            img.src = 'http://192.168.1.14:81/stream';
            img.style.display = 'block';
        }
    }
}

function showCameraStandby() {
    if (!isCameraActive) return;
    isCameraActive = false;
    const img = document.getElementById('liveStreamImg');
    const standby = document.getElementById('cameraStandbyBox');
    const caption = document.getElementById('cameraCaption');
    const statusText = document.getElementById('cameraStatusText');
    const huds = document.querySelectorAll('.camera-active-element');
    const footer = document.getElementById('livePromptFooter');

    if (img) {
        img.removeAttribute('src'); // Ngắt stream ngay lập tức để ESP32-CAM nghỉ
        img.style.display = 'none';
    }
    if (standby) standby.style.display = 'block';
    huds.forEach(el => el.style.display = 'none');
    if (caption) {
        caption.textContent = 'Chế độ chờ · Sẵn sàng nhận ngón tay';
        caption.style.borderColor = '#334155';
    }
    if (statusText) {
        statusText.textContent = 'Chế độ chờ (Tắt)';
        statusText.style.color = '#64748b';
        statusText.style.fontWeight = 'normal';
    }
    if (footer) {
        footer.textContent = 'Đặt ngón tay lên cảm biến MAX30102 để chấm công';
        footer.style.color = '#64748b';
        footer.style.fontWeight = 'normal';
    }
}

let isPollingLive = false;

async function pollLiveAttendance() {
    if (isPollingLive) return;
    isPollingLive = true;
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 2000);

        const res = await fetch('/?action=live_attendance_feed', { 
            cache: 'no-store',
            signal: controller.signal 
        });
        clearTimeout(timeoutId);

        if (!res.ok) return;
        const data = await res.json();
        if (!data.success) return;

        // 1. Phản hồi tức thì khi có người đặt tay lên cảm biến (On-Demand Activation)
        if (data.active_session) {
            showCameraActive();
            if (data.current_session) {
                if (data.current_session.name) {
                    document.getElementById('employeeName').textContent = data.current_session.name;
                }
                if (data.current_session.MaNV) {
                    document.getElementById('employeeCode').textContent = 'NV' + String(data.current_session.MaNV).padStart(3, '0');
                }
                if (data.current_session.image_b64) {
                    const avatarEl = document.getElementById('employeeAvatar');
                    if (avatarEl) {
                        avatarEl.src = 'data:image/jpeg;base64,' + data.current_session.image_b64;
                    }
                }
            }
        } else {
            showCameraStandby();
        }

        // 2. Cập nhật khi hoàn tất một lượt chấm công mới
        const latest = data.latest;
        if (latest && (latest.MaCC !== lastPunchId || latest.PunchType !== lastPunchType)) {
            lastPunchId = latest.MaCC;
            lastPunchType = latest.PunchType;

            const isOut = latest.PunchType === 'OUT';
            const badge = document.getElementById('punchTypeBadge');
            if (badge) {
                badge.textContent = isOut ? 'Check-out' : 'Check-in';
                badge.className = 'live-card-badge ' + (isOut ? 'live-card-badge-outline' : 'live-card-badge-dark');
            }

            document.getElementById('employeeCode').textContent = 'NV' + String(latest.MaNV).padStart(3, '0');
            document.getElementById('employeeName').textContent = latest.HoTen || 'Nhân viên';
            document.getElementById('employeeShift').textContent = `${latest.TenCa || 'Ca chuẩn'} · Đúng giờ`;
            document.getElementById('punchTime').textContent = latest.ThoiGianMoiNhat;
            document.getElementById('valBpm').textContent = latest.NhipTim || 75;
            document.getElementById('valSpo2').textContent = Number(latest.SpO2 || 98.5).toFixed(1);
            document.getElementById('valTheTrang').textContent = latest.TheTrangSK || latest.TheTrangVao || 'Bình thường';
            
            const imgKind = isOut ? 'attendance_image_out' : 'attendance_image_in';
            const hasPic = isOut ? latest.HasImageOut : latest.HasImageIn;
            const avatarEl = document.getElementById('employeeAvatar');
            if (avatarEl) {
                avatarEl.onerror = function() { this.onerror = null; this.src = DEFAULT_AVATAR; };
                avatarEl.src = hasPic ? `/?action=${imgKind}&id=${latest.MaCC}&t=${Date.now()}` : DEFAULT_AVATAR;
            }

            playMinimalBeep();

            // Hiệu ứng viền phản hồi
            const card = document.getElementById('punchCard');
            if (card) {
                card.style.borderColor = '#0f172a';
                setTimeout(() => { card.style.borderColor = '#e2e8f0'; }, 2000);
            }

            if (Array.isArray(data.recent)) {
                renderRecentTable(data.recent);
            }
        }
    } catch (e) {
        // Bỏ qua lỗi ngắt kết nối định kỳ
    } finally {
        isPollingLive = false;
    }
}

function renderRecentTable(list) {
    const tbody = document.getElementById('recentPunchesBody');
    if (!tbody) return;
    tbody.innerHTML = list.map(r => {
        const isOut = r.PunchType === 'OUT';
        const imgKind = isOut ? 'attendance_image_out' : 'attendance_image_in';
        const hasPic = isOut ? r.HasImageOut : r.HasImageIn;
        const pic = hasPic ? `/?action=${imgKind}&id=${r.MaCC}` : DEFAULT_AVATAR;
        const tagClass = isOut ? 'live-table-tag-out' : 'live-table-tag-in';
        return `
            <tr>
                <td><img src="${pic}" style="width:32px;height:32px;border-radius:4px;object-fit:cover;border:1px solid #e2e8f0;" onerror="this.onerror=null;this.src='${DEFAULT_AVATAR}'"></td>
                <td><span class="live-person-code">NV${String(r.MaNV).padStart(3, '0')}</span></td>
                <td style="font-weight:600;color:#0f172a;">${r.HoTen || ''}</td>
                <td><span class="live-table-tag ${tagClass}">${isOut ? 'Check-out' : 'Check-in'}</span></td>
                <td>${r.TenCa || 'Ca chuẩn'}</td>
                <td style="font-family:monospace;font-size:11px;">${r.ThoiGianMoiNhat || ''}</td>
                <td style="font-weight:600;">${r.NhipTim ? (r.NhipTim + ' bpm') : '--'}</td>
                <td style="font-weight:600;">${r.SpO2 ? (Number(r.SpO2).toFixed(1) + '%') : '--'}</td>
                <td>${r.TheTrangSK || r.TheTrangVao || 'Bình thường'}</td>
            </tr>
        `;
    }).join('');
}

setInterval(pollLiveAttendance, 1500);
</script>

<?php require __DIR__ . '/layout/footer.php'; ?>

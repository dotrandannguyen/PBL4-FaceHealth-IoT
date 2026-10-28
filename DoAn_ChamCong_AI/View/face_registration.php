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
?>
<main class="page-container page-container--wide">
    <div class="workspace-toolbar" style="margin-bottom: 18px;">
        <div>
            <h1>Đăng ký nhận diện khuôn mặt</h1>
            <p style="margin: 4px 0 0; color: #475467; font-size: 14px;">
                Thu thập và lưu trữ 5 góc khuôn mặt (ArcFace 512-dim) phục vụ điểm danh thông minh qua Camera.
            </p>
        </div>
        <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
            <div class="status-pill <?= $aiReady ? 'status-pill--registered' : 'status-pill--pending' ?>" style="font-weight: 500;">
                <span aria-hidden="true"></span>
                AI Service: <?= $aiReady ? 'Sẵn sàng (buffalo_sc)' : 'Chưa kết nối' ?>
            </div>
            <a class="button button--secondary" href="/">Quản lý nhân viên</a>
        </div>
    </div>

    <div style="display: grid; grid-template-columns: minmax(420px, 1.2fr) minmax(360px, 1fr); gap: 24px; align-items: start;">
        <!-- Cột trái: Live Camera & Studio Đăng ký 5 góc -->
        <section class="workspace" aria-labelledby="camera-studio-title" style="padding: 20px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                <h2 id="camera-studio-title" style="margin: 0; font-size: 18px; font-weight: 600;">
                    Camera Đăng ký khuôn mặt
                </h2>
                <?php if ($selectedId !== null): ?>
                    <span class="status-pill status-pill--registered">
                        <?= $h($selectedCode) ?> · <?= $h($selectedName) ?>
                    </span>
                <?php endif; ?>
            </div>

            <?php if ($selectedId === null): ?>
                <div class="empty-state" style="padding: 32px 16px; text-align: center;">
                    Vui lòng chọn nhân viên ở danh sách bên phải để bắt đầu đăng ký khuôn mặt.
                </div>
            <?php else: ?>
                <!-- Khu vực điều khiển chọn nhân viên nhanh -->
                <div class="form-field" style="margin-bottom: 16px;">
                    <label for="employee-select-picker" style="font-weight: 600; margin-bottom: 6px; display: block;">
                        Nhân viên đang chọn:
                    </label>
                    <select id="employee-select-picker" class="input" style="width: 100%; padding: 8px 12px; border-radius: 8px; border: 1px solid #d0d5dd;" onchange="if(this.value) window.location.href='/?action=face_registration&id=' + this.value;">
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

                <!-- Studio Đăng ký khuôn mặt 5 góc -->
                <div class="face-management" style="padding: 0; border: none; box-shadow: none;">
                    <div class="face-management-actions" style="margin-bottom: 16px; gap: 8px;">
                        <button class="button button--primary" type="button" data-face-start>
                            <?= $faceCount > 0 ? '🔄 Đăng ký lại (5 góc)' : '📸 Bắt đầu đăng ký khuôn mặt' ?>
                        </button>
                        <?php if ($faceCount > 0): ?>
                            <button class="button button--danger" type="button" data-face-delete>
                                🗑️ Xóa đăng ký
                            </button>
                        <?php endif; ?>
                    </div>

                    <!-- Khung hình Camera và điều khiển quá trình thu thập -->
                    <div class="face-enrollment" data-face-enrollment data-employee-id="<?= $selectedId ?>" data-csrf="<?= $h($csrfToken) ?>" data-face-count="<?= $faceCount ?>" style="margin-top: 0;">
                        <div class="face-enrollment-camera-wrap" style="position: relative; border-radius: 12px; overflow: hidden; background: #0f172a; min-height: 280px; display: flex; align-items: center; justify-content: center;">
                            <img class="face-enrollment-camera" data-face-camera alt="Khung hình camera đăng ký khuôn mặt" style="max-height: 380px; object-fit: contain; width: 100%;" hidden>
                            <div class="face-enrollment-camera-empty" data-face-camera-empty style="color: #94a3b8; text-align: center; padding: 20px;">
                                <svg style="width: 48px; height: 48px; margin: 0 auto 12px; stroke: #64748b; fill: none;" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"/>
                                </svg>
                                <div>Camera sẽ tự động kết nối khi nhấn "Bắt đầu đăng ký".</div>
                            </div>
                        </div>

                        <div class="face-enrollment-progress" aria-live="polite" style="margin-top: 16px;">
                            <p class="face-enrollment-step" data-face-step style="font-size: 15px; font-weight: 600; color: #1e293b;">
                                Bước 1/5 · Chính diện
                            </p>
                            <p class="face-enrollment-feedback" data-face-feedback style="font-size: 14px; color: #475467; margin: 6px 0 12px; min-height: 38px;">
                                Nhấn “Bắt đầu đăng ký” để kích hoạt camera và nhận diện 5 tư thế khuôn mặt.
                            </p>
                            <ol class="face-pose-list" data-face-pose-list style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; list-style: none; padding: 0;">
                                <li data-pose="frontal" style="text-align: center; padding: 8px 4px; border-radius: 6px; background: #f1f5f9; font-size: 12px; font-weight: 500;">1. Chính diện</li>
                                <li data-pose="left" style="text-align: center; padding: 8px 4px; border-radius: 6px; background: #f1f5f9; font-size: 12px; font-weight: 500;">2. Nghiêng trái</li>
                                <li data-pose="right" style="text-align: center; padding: 8px 4px; border-radius: 6px; background: #f1f5f9; font-size: 12px; font-weight: 500;">3. Nghiêng phải</li>
                                <li data-pose="up" style="text-align: center; padding: 8px 4px; border-radius: 6px; background: #f1f5f9; font-size: 12px; font-weight: 500;">4. Ngẩng nhẹ</li>
                                <li data-pose="down" style="text-align: center; padding: 8px 4px; border-radius: 6px; background: #f1f5f9; font-size: 12px; font-weight: 500;">5. Cúi nhẹ</li>
                            </ol>
                        </div>

                        <div class="face-enrollment-actions" style="margin-top: 16px; display: flex; gap: 8px;">
                            <button class="button button--secondary" type="button" data-face-cancel hidden>Hủy phiên</button>
                            <button class="button button--primary" type="button" data-face-complete disabled hidden>Lưu 5 mẫu khuôn mặt</button>
                        </div>
                    </div>

                    <p class="notice face-enrollment-result" data-face-result role="status" style="margin-top: 16px;" hidden></p>
                </div>
            <?php endif; ?>
        </section>

        <!-- Cột phải: Danh sách Nhân viên & Thư viện 5 ảnh mẫu đã lưu -->
        <div style="display: flex; flex-direction: column; gap: 20px;">
            <!-- Khối thư viện ảnh mẫu của nhân viên đang chọn -->
            <?php if ($selectedId !== null): ?>
                <section class="workspace" aria-labelledby="sample-gallery-title" style="padding: 20px;">
                    <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 12px;">
                        <h2 id="sample-gallery-title" style="margin: 0; font-size: 16px; font-weight: 600;">
                            Mẫu khuôn mặt hiện tại (<?= $faceCount ?> mẫu)
                        </h2>
                        <?php if ($faceCount > 0): ?>
                            <span style="font-size: 12px; color: #16a34a; font-weight: 500;">✓ Sẵn sàng nhận diện</span>
                        <?php endif; ?>
                    </div>

                    <?php if ($faceSamples === []): ?>
                        <p class="empty-state" style="padding: 20px; text-align: center; margin: 0;">
                            Nhân viên này chưa có dữ liệu khuôn mặt. Hãy bắt đầu đăng ký ở cột bên trái.
                        </p>
                    <?php else: ?>
                        <div class="face-sample-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(90px, 1fr)); gap: 10px; margin-top: 10px;">
                            <?php foreach ($faceSamples as $idx => $sample): ?>
                                <?php
                                $embeddingId = (int)$sample['MaEmbedding'];
                                $hasImg = (int)($sample['HasImage'] ?? 0) === 1;
                                $timeStr = !empty($sample['ThoiGianTao']) ? date('d/m H:i', strtotime((string)$sample['ThoiGianTao'])) : '';
                                ?>
                                <article class="face-sample" style="text-align: center; border: 1px solid #e2e8f0; border-radius: 8px; padding: 6px; background: #fff;">
                                    <?php if ($hasImg): ?>
                                        <button class="face-sample-image" type="button" data-face-preview="/?action=face_image&amp;id=<?= $embeddingId ?>" aria-label="Xem ảnh mẫu <?= $embeddingId ?>" style="width: 100%; border-radius: 6px; overflow: hidden; border: none; padding: 0; background: none; cursor: zoom-in;">
                                            <img src="/?action=face_image&amp;id=<?= $embeddingId ?>" alt="Mẫu <?= $idx + 1 ?>" style="width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 6px;" loading="lazy">
                                        </button>
                                    <?php else: ?>
                                        <div style="width: 100%; aspect-ratio: 1; background: #f1f5f9; display: flex; align-items: center; justify-content: center; font-size: 11px; color: #64748b; border-radius: 6px;">Vector</div>
                                    <?php endif; ?>
                                    <p style="margin: 4px 0 0; font-size: 11px; font-weight: 600; color: #334155;">Mẫu #<?= $idx + 1 ?></p>
                                    <?php if ($timeStr): ?>
                                        <span style="font-size: 10px; color: #94a3b8;"><?= $timeStr ?></span>
                                    <?php endif; ?>
                                </article>
                            <?php endforeach; ?>
                        </div>
                    <?php endif; ?>
                </section>
            <?php endif; ?>

            <!-- Bảng danh sách nhân viên để chọn nhanh -->
            <section class="workspace" aria-labelledby="employee-directory-title" style="padding: 20px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;">
                    <h2 id="employee-directory-title" style="margin: 0; font-size: 16px; font-weight: 600;">
                        Danh sách nhân viên (<?= count($employees) ?>)
                    </h2>
                    <input id="employee-table-search" type="search" placeholder="Tìm theo tên hoặc mã NV..." style="padding: 6px 10px; font-size: 13px; border-radius: 6px; border: 1px solid #d0d5dd; width: 200px;">
                </div>

                <div class="table-scroll" style="max-height: 420px; overflow-y: auto;">
                    <table class="employee-table" style="font-size: 13px; width: 100%;">
                        <thead>
                            <tr>
                                <th style="padding: 8px;">Mã NV</th>
                                <th style="padding: 8px;">Họ tên</th>
                                <th style="padding: 8px;">Khuôn mặt</th>
                                <th style="padding: 8px; text-align: right;">Chọn</th>
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
                                <tr class="employee-row-item <?= $isCurrent ? 'is-selected' : '' ?>" style="<?= $isCurrent ? 'background: #eff6ff;' : '' ?>" data-search="<?= $h(strtolower($eCode . ' ' . $eName)) ?>">
                                    <td style="padding: 8px; font-weight: 600;"><?= $h($eCode) ?></td>
                                    <td style="padding: 8px;"><?= $h($eName) ?></td>
                                    <td style="padding: 8px;">
                                        <?php if ($eCount > 0): ?>
                                            <span style="color: #16a34a; font-weight: 500;">✓ <?= $eCount ?> mẫu</span>
                                        <?php else: ?>
                                            <span style="color: #94a3b8;">Chưa có</span>
                                        <?php endif; ?>
                                    </td>
                                    <td style="padding: 8px; text-align: right;">
                                        <?php if ($isCurrent): ?>
                                            <span style="font-weight: 600; color: #2563eb;">Đang chọn</span>
                                        <?php else: ?>
                                            <a class="button button--secondary button--small" href="/?action=face_registration&amp;id=<?= $eId ?>" style="padding: 2px 8px; font-size: 12px;">Chọn</a>
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

    <!-- Modal Phóng to ảnh khuôn mặt Lightbox -->
    <dialog class="face-lightbox" data-face-lightbox aria-label="Ảnh mẫu khuôn mặt">
        <div class="face-lightbox-toolbar">
            <span data-face-lightbox-title>Ảnh mẫu khuôn mặt</span>
            <button class="button button--secondary button--small" type="button" data-face-lightbox-close>Đóng</button>
        </div>
        <img data-face-lightbox-image alt="Ảnh mẫu khuôn mặt phóng lớn">
    </dialog>
</main>

<script src="/public/js/face_registration_page.js" defer></script>
<?php require __DIR__ . '/layout/footer.php'; ?>

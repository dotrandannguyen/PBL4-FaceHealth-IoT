(() => {
    // ── 1. Quản lý tìm kiếm nhanh danh sách nhân viên ──────────────────────
    const searchInput = document.getElementById('employee-table-search');
    const tableBody = document.getElementById('employee-table-body');
    if (searchInput && tableBody) {
        searchInput.addEventListener('input', () => {
            const query = searchInput.value.trim().toLowerCase();
            const rows = tableBody.querySelectorAll('.employee-row-item');
            rows.forEach((row) => {
                const text = row.dataset.search || row.textContent.toLowerCase();
                row.hidden = query !== '' && !text.includes(query);
            });
        });
    }

    // ── 2. Quản lý Lightbox phóng to ảnh mẫu ───────────────────────────────
    const lightbox = document.querySelector('[data-face-lightbox]');
    const lightboxImage = document.querySelector('[data-face-lightbox-image]');
    const lightboxClose = document.querySelector('[data-face-lightbox-close]');
    if (lightbox && lightboxImage && lightboxClose) {
        document.querySelectorAll('[data-face-preview]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const src = btn.dataset.facePreview;
                if (!src) return;
                lightboxImage.src = src;
                if (typeof lightbox.showModal === 'function') {
                    lightbox.showModal();
                } else {
                    lightbox.setAttribute('open', '');
                }
            });
        });

        lightboxClose.addEventListener('click', () => {
            if (typeof lightbox.close === 'function') {
                lightbox.close();
            } else {
                lightbox.removeAttribute('open');
            }
        });

        lightbox.addEventListener('click', (e) => {
            if (e.target === lightbox) {
                if (typeof lightbox.close === 'function') {
                    lightbox.close();
                } else {
                    lightbox.removeAttribute('open');
                }
            }
        });
    }

    // ── 3. Quản lý Đăng ký khuôn mặt 5 góc qua Camera ─────────────────────
    const root = document.querySelector('[data-face-enrollment]');
    if (!root) return;

    const employeeId = root.dataset.employeeId;
    const csrfToken = root.dataset.csrf;
    let currentSource = root.dataset.cameraSource || 'local';

    const startButton = document.querySelector('[data-face-start]');
    const deleteButton = document.querySelector('[data-face-delete]');
    const cancelButton = root.querySelector('[data-face-cancel]');
    const completeButton = root.querySelector('[data-face-complete]');
    const camera = root.querySelector('[data-face-camera]');
    const cameraEmpty = root.querySelector('[data-face-camera-empty]');
    const viewport = root.querySelector('[data-face-viewport]');
    const reticle = root.querySelector('[data-face-reticle]');
    const reticleSourceLabel = root.querySelector('[data-reticle-source-label]');
    const reticleHint = root.querySelector('[data-reticle-hint]');
    const matchIndicator = document.getElementById('pose-match-indicator');
    const deviceHint = document.getElementById('camera-device-hint');
    const stepLabel = root.querySelector('[data-face-step]');
    const feedback = root.querySelector('[data-face-feedback]');
    const poseList = root.querySelector('[data-face-pose-list]');
    const result = document.querySelector('[data-face-result]');
    const deviceButtons = document.querySelectorAll('[data-camera-device]');

    const poses = [
        { key: 'frontal', label: 'Chính diện', guide: 'Nhìn thẳng vào tâm camera, giữ nét mặt tự nhiên.' },
        { key: 'left', label: 'Nghiêng trái', guide: 'Nghiêng đầu nhẹ sang bên TRÁI khoảng 15 độ.' },
        { key: 'right', label: 'Nghiêng phải', guide: 'Nghiêng đầu nhẹ sang bên PHẢI khoảng 15 độ.' },
        { key: 'up', label: 'Ngẩng nhẹ', guide: 'Ngẩng cằm lên trên nhẹ nhàng khoảng 10 độ.' },
        { key: 'down', label: 'Cúi nhẹ', guide: 'Cúi đầu nhẹ xuống dưới khoảng 10 độ.' },
    ];

    let captured = 0;
    let running = false;
    let busy = false;
    let stableSince = 0;
    let poseTimer = null;
    let frameTimer = null;

    // ── Xử lý chuyển đổi thiết bị quét (Webcam vs ESP32-CAM) ──────────────
    const updateDeviceUi = (source) => {
        currentSource = source;
        root.dataset.cameraSource = source;
        deviceButtons.forEach((btn) => {
            const active = btn.dataset.cameraDevice === source;
            btn.classList.toggle('is-active', active);
        });

        if (deviceHint) {
            deviceHint.textContent = source === 'esp32'
                ? '📡 Luồng ESP32: http://esp32cam.local:81/stream'
                : '📷 Nguồn Webcam: Camera ID 0 (DirectShow 640x480)';
        }

        if (reticleSourceLabel) {
            reticleSourceLabel.textContent = source === 'esp32' ? 'ESP32-CAM' : 'WEBCAM';
        }
    };

    deviceButtons.forEach((btn) => {
        btn.addEventListener('click', async () => {
            const newSource = btn.dataset.cameraDevice;
            if (newSource === currentSource) return;

            updateDeviceUi(newSource);

            // Gửi thông báo chuyển nguồn tới backend
            try {
                const body = new URLSearchParams({ _csrf_token: csrfToken, source: newSource });
                await fetch(`/?action=face_camera_set_source&id=${encodeURIComponent(employeeId)}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8' },
                    body,
                    credentials: 'same-origin',
                });
            } catch (err) {
                console.warn('Lỗi lưu nguồn camera:', err);
            }

            // Nếu đang trong phiên quét camera, làm mới khung hình ngay lập tức
            if (running && camera && !camera.hidden) {
                camera.src = `/?action=face_camera_frame&source=${encodeURIComponent(newSource)}&ts=${Date.now()}`;
            }
        });
    });

    const post = async (action, extraParams = {}) => {
        const body = new URLSearchParams({
            _csrf_token: csrfToken,
            source: currentSource,
            ...extraParams,
        });
        const response = await fetch(`/?action=${action}&id=${encodeURIComponent(employeeId)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8' },
            body,
            credentials: 'same-origin',
            cache: 'no-store',
        });
        let payload;
        try {
            payload = await response.json();
        } catch {
            throw new Error('Phản hồi từ máy chủ không hợp lệ.');
        }
        if (!response.ok && !payload.message) {
            throw new Error('Không thể hoàn tất yêu cầu.');
        }
        return { response, payload };
    };

    const showResult = (message, kind = 'info') => {
        if (!result) return;
        result.textContent = message;
        result.className = `notice face-enrollment-result notice--${kind}`;
        result.hidden = false;
    };

    const renderStep = () => {
        const step = poses[captured];
        if (stepLabel) {
            stepLabel.textContent = step
                ? `Bước ${captured + 1}/5 · ${step.label}`
                : '✅ Đã hoàn tất 5/5 góc khuôn mặt!';
        }
        if (feedback && step) {
            feedback.textContent = step.guide;
        }
        if (poseList) {
            [...poseList.children].forEach((card, index) => {
                const statusSpan = card.querySelector('[data-pose-status]');
                card.classList.remove('is-active', 'is-complete');
                if (index < captured) {
                    card.classList.add('is-complete');
                    if (statusSpan) statusSpan.textContent = '✓ Đã đạt';
                } else if (index === captured && captured < poses.length) {
                    card.classList.add('is-active');
                    if (statusSpan) statusSpan.textContent = 'Đang quét...';
                } else {
                    if (statusSpan) statusSpan.textContent = 'Chờ chụp';
                }
            });
        }
    };

    const setReticleMatched = (matched) => {
        if (viewport) {
            viewport.classList.toggle('is-matched', matched);
        }
        if (matchIndicator) {
            matchIndicator.style.display = matched ? 'inline-flex' : 'none';
        }
    };

    const setCamera = (enabled) => {
        if (camera) camera.hidden = !enabled;
        if (cameraEmpty) cameraEmpty.hidden = enabled;
        if (reticle) reticle.hidden = !enabled;

        if (!enabled) {
            setReticleMatched(false);
            if (camera) camera.removeAttribute('src');
            clearInterval(frameTimer);
            frameTimer = null;
            return;
        }

        const refreshFrame = () => {
            if (document.hidden || !running) return;
            if (camera) {
                camera.src = `/?action=face_camera_frame&source=${encodeURIComponent(currentSource)}&ts=${Date.now()}`;
            }
        };

        refreshFrame();
        clearInterval(frameTimer);
        frameTimer = setInterval(refreshFrame, 350);
    };

    const stopPosePolling = () => {
        clearInterval(poseTimer);
        poseTimer = null;
        running = false;
        busy = false;
        stableSince = 0;
        setReticleMatched(false);
    };

    if (camera) {
        camera.addEventListener('error', () => {
            camera.hidden = true;
            if (reticle) reticle.hidden = true;
            if (cameraEmpty) {
                cameraEmpty.hidden = false;
                const isEsp = currentSource === 'esp32';
                cameraEmpty.innerHTML = `
                    <div style="color: #ef4444; font-weight: 700; font-size: 15px; margin-bottom: 6px;">
                        ⚠️ Không kết nối được Camera (${isEsp ? 'ESP32-CAM' : 'Webcam máy tính'})!
                    </div>
                    <div style="font-size: 13px; color: #cbd5e1; max-width: 440px; margin: 0 auto; line-height: 1.5;">
                        ${isEsp 
                            ? 'Vui lòng kiểm tra nguồn điện và mạng WiFi của ESP32-CAM (mặc định: http://esp32cam.local:81/stream).'
                            : 'Vui lòng kiểm tra AI Service trên cổng 5001 hoặc thử chuyển thiết bị sang ESP32-CAM ở trên.'}
                    </div>
                `;
            }
        });

        camera.addEventListener('load', () => {
            if (camera.naturalWidth > 0) {
                camera.hidden = false;
                if (cameraEmpty) cameraEmpty.hidden = true;
                if (reticle && running) reticle.hidden = false;
            }
        });
    }

    const captureCurrentPose = async () => {
        busy = true;
        stableSince = 0;
        setReticleMatched(true);
        try {
            const { response, payload } = await post('face_enrollment_capture');
            if (!response.ok || !payload.success) {
                setReticleMatched(false);
                if (feedback) feedback.textContent = payload.instruction || payload.message || 'Mẫu chưa đạt chuẩn, hãy giữ đúng hướng.';
                return;
            }
            captured = Number(payload.captured || captured + 1);
            renderStep();
            setReticleMatched(false);

            if (captured >= poses.length) {
                stopPosePolling();
                setCamera(false);
                if (feedback) feedback.textContent = '🎉 Đã thu thập đủ 5 góc! Nhấn nút "Lưu 5 mẫu khuôn mặt" bên dưới để hoàn tất.';
                if (completeButton) {
                    completeButton.hidden = false;
                    completeButton.disabled = false;
                }
            } else {
                if (feedback) feedback.textContent = `✨ Chụp thành công góc ${captured}/5! Hãy chuyển sang: ${poses[captured].label}.`;
                if (reticleHint) reticleHint.textContent = poses[captured].guide;
            }
        } catch (error) {
            setReticleMatched(false);
            if (feedback) feedback.textContent = error.message || 'Lỗi thu nhận mẫu.';
        } finally {
            busy = false;
        }
    };

    const pollPose = async () => {
        if (!running || busy || captured >= poses.length) return;
        busy = true;
        try {
            const { response, payload } = await post('face_enrollment_pose');
            if (!response.ok || !payload.success) {
                stableSince = 0;
                setReticleMatched(false);
                if (feedback) feedback.textContent = payload.instruction || payload.message || 'Đang chờ phát hiện khuôn mặt...';
                return;
            }

            if (payload.pose_ok) {
                const now = Date.now();
                setReticleMatched(true);
                if (!stableSince) {
                    stableSince = now;
                    if (feedback) feedback.textContent = `🎯 Đúng tư thế: ${poses[captured].label}! Giữ yên 1 giây để chụp...`;
                } else if (now - stableSince >= 650) {
                    await captureCurrentPose();
                }
            } else {
                stableSince = 0;
                setReticleMatched(false);
                if (feedback) feedback.textContent = payload.instruction || payload.message || `Vui lòng xoay mặt theo hướng: ${poses[captured].label}.`;
            }
        } catch (error) {
            stableSince = 0;
            setReticleMatched(false);
            if (feedback) feedback.textContent = error.message || 'Lỗi kiểm tra hướng mặt.';
        } finally {
            busy = false;
        }
    };

    // ── Nút Bắt đầu đăng ký ───────────────────────────────────────────────
    if (startButton) {
        startButton.addEventListener('click', async () => {
            if (root.dataset.aiReady === '0') {
                showResult('⚠️ AI Service chưa được kết nối trên cổng 5001! Vui lòng chạy file "run_ai_service.bat" trong thư mục dự án rồi tải lại trang.', 'error');
                return;
            }

            startButton.disabled = true;
            if (deleteButton) deleteButton.disabled = true;
            if (result) result.hidden = true;
            captured = 0;
            renderStep();

            if (completeButton) {
                completeButton.hidden = true;
                completeButton.disabled = true;
            }
            if (cancelButton) cancelButton.hidden = false;

            try {
                const { response, payload } = await post('face_enrollment_start');
                if (!response.ok || !payload.success) {
                    throw new Error(payload.message || 'Không thể khởi tạo phiên đăng ký. Vui lòng kiểm tra AI Service trên cổng 5001.');
                }
                running = true;
                setCamera(true);
                if (feedback) feedback.textContent = `Camera đã kích hoạt. Nhìn vào tâm camera theo hướng: ${poses[0].label}.`;
                if (reticleHint) reticleHint.textContent = poses[0].guide;
                poseTimer = setInterval(pollPose, 550);
            } catch (error) {
                const errorMsg = error.message || 'Không thể khởi tạo phiên đăng ký.';
                showResult(errorMsg, 'error');
                startButton.disabled = false;
                if (deleteButton) deleteButton.disabled = false;
                setCamera(false);
            }
        });
    }

    // ── Nút Hủy phiên quét ────────────────────────────────────────────────
    if (cancelButton) {
        cancelButton.addEventListener('click', async () => {
            stopPosePolling();
            setCamera(false);
            cancelButton.hidden = true;
            if (completeButton) completeButton.hidden = true;
            startButton.disabled = false;
            if (deleteButton) deleteButton.disabled = false;
            if (feedback) feedback.textContent = 'Đã hủy phiên quét. Nhấn nút "Bắt đầu đăng ký" khi bạn sẵn sàng.';
            try {
                await post('face_enrollment_cancel');
            } catch {}
        });
    }

    // ── Nút Lưu 5 mẫu khuôn mặt ──────────────────────────────────────────
    if (completeButton) {
        completeButton.addEventListener('click', async () => {
            completeButton.disabled = true;
            try {
                const { response, payload } = await post('face_enrollment_complete');
                if (!response.ok || !payload.success) {
                    throw new Error(payload.message || 'Không thể lưu mẫu khuôn mặt.');
                }
                showResult('✅ Đã lưu thành công 5 mẫu khuôn mặt và đồng bộ nhận diện AI!', 'success');
                setTimeout(() => window.location.reload(), 1200);
            } catch (error) {
                showResult(error.message, 'error');
                completeButton.disabled = false;
            }
        });
    }

    // ── Nút Xóa dữ liệu khuôn mặt ────────────────────────────────────────
    if (deleteButton) {
        deleteButton.addEventListener('click', async () => {
            if (!confirm('Bạn có chắc chắn muốn xóa toàn bộ mẫu khuôn mặt của nhân viên này?')) {
                return;
            }
            deleteButton.disabled = true;
            try {
                const { response, payload } = await post('face_registration_delete');
                if (!response.ok || !payload.success) {
                    throw new Error(payload.message || 'Không thể xóa mẫu khuôn mặt.');
                }
                showResult('Đã xóa thành công dữ liệu khuôn mặt.', 'success');
                setTimeout(() => window.location.reload(), 900);
            } catch (error) {
                showResult(error.message, 'error');
                deleteButton.disabled = false;
            }
        });
    }
})();

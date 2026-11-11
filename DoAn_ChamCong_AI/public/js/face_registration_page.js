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

        const closeBox = () => {
            if (typeof lightbox.close === 'function') {
                lightbox.close();
            } else {
                lightbox.removeAttribute('open');
            }
        };

        lightboxClose.addEventListener('click', closeBox);
        lightbox.addEventListener('click', (e) => {
            if (e.target === lightbox) closeBox();
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
    const snapButton = root.querySelector('[data-face-snap]');
    const completeButton = root.querySelector('[data-face-complete]');

    const localVideo = root.querySelector('[data-face-video]');
    const camera = root.querySelector('[data-face-camera]');
    const canvas = root.querySelector('[data-face-canvas]') || document.createElement('canvas');
    const cameraEmpty = root.querySelector('[data-face-camera-empty]');
    const viewport = root.querySelector('[data-face-viewport]');
    const reticle = root.querySelector('[data-face-reticle]');
    const reticleSourceLabel = root.querySelector('[data-reticle-source-label]');
    const reticleHint = root.querySelector('[data-reticle-hint]');
    const countdownContainer = document.getElementById('pose-countdown-container');
    const countdownProgress = document.getElementById('countdown-ring-progress');
    const matchIndicator = document.getElementById('pose-match-indicator');
    const deviceHint = document.getElementById('camera-device-hint');
    const stepLabel = root.querySelector('[data-face-step]');
    const feedback = root.querySelector('[data-face-feedback]');
    const poseList = root.querySelector('[data-face-pose-list]');
    const result = document.querySelector('[data-face-result]');
    const deviceButtons = document.querySelectorAll('[data-camera-device]');
    const toggleFitBtn = document.getElementById('toggle-camera-fit-btn');

    if (toggleFitBtn) {
        toggleFitBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const isContain = camera.classList.toggle('is-contain');
            localVideo.classList.toggle('is-contain', isContain);
            toggleFitBtn.textContent = isContain ? '🔲 Toàn khung' : '⛶ Lấp đầy';
            toggleFitBtn.title = isContain
                ? 'Chuyển sang chế độ lấp đầy khung hình (Cover)'
                : 'Chuyển sang chế độ xem trọn tỉ lệ gốc 4:3 (Contain)';
        });
    }

    const poses = [
        { key: 'frontal', label: 'Chính diện', guide: 'Nhìn thẳng vào tâm camera, giữ nét mặt tự nhiên.' },
        { key: 'left', label: 'Nghiêng trái', guide: '⬅️ Quay nhẹ đầu sang bên TRÁI khoảng 10-15 độ.' },
        { key: 'right', label: 'Nghiêng phải', guide: '➡️ Quay nhẹ đầu sang bên PHẢI khoảng 10-15 độ.' },
        { key: 'up', label: 'Ngẩng nhẹ', guide: '⬆️ Hơi ngẩng cằm lên trên khoảng 10 độ.' },
        { key: 'down', label: 'Cúi nhẹ', guide: '⬇️ Cúi đầu nhẹ xuống dưới khoảng 10 độ.' },
    ];

    let captured = 0;
    let running = false;
    let busy = false;
    let stableSince = 0;
    let poseTimer = null;
    let webRtcStream = null;
    const HOLD_DURATION_MS = 250; // Thời gian giữ tư thế chuẩn trước khi chụp (0.25s)

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
                ? '📡 Luồng ESP32: http://esp32cam.local:81/stream (Proxy 25-30 FPS)'
                : '📷 Nguồn Webcam: WebRTC Trực tiếp (30-60 FPS)';
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

            // Gửi thông báo chuyển nguồn tới backend session
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

            // Nếu đang trong phiên quét camera, chuyển đổi nguồn mượt mà ngay
            if (running) {
                stopCameraStreams();
                startCameraStream(newSource);
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

    const setReticleMatched = (matched, progressPercent = 0) => {
        if (viewport) {
            viewport.classList.toggle('is-matched', matched);
        }
        if (countdownContainer) {
            countdownContainer.style.display = matched ? 'inline-flex' : 'none';
        }
        if (countdownProgress) {
            const offset = 100 - Math.min(100, Math.max(0, progressPercent));
            countdownProgress.style.strokeDashoffset = offset;
        }
    };

    // ── Trích xuất snapshot frame hiện tại từ Video/Img qua Canvas ─────────
    const getSnapshotBase64 = () => {
        const isLocal = currentSource === 'local';
        const sourceElement = isLocal ? localVideo : camera;
        if (!sourceElement) return null;

        const w = isLocal ? (sourceElement.videoWidth || 640) : (sourceElement.naturalWidth || 640);
        const h = isLocal ? (sourceElement.videoHeight || 480) : (sourceElement.naturalHeight || 480);
        if (w <= 0 || h <= 0) return null;

        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d');
        if (!ctx) return null;

        // Lật gương ngang cho CẢ Webcam VÀ ESP32-CAM để người dùng cử động tự nhiên như soi gương
        ctx.save();
        ctx.translate(w, 0);
        ctx.scale(-1, 1);
        ctx.drawImage(sourceElement, 0, 0, w, h);
        ctx.restore();

        try {
            return canvas.toDataURL('image/jpeg', 0.88);
        } catch (err) {
            console.warn('Canvas export error:', err);
            return null;
        }
    };

    // ── Bật luồng Camera (WebRTC cho Webcam hoặc MJPEG Stream cho ESP32) ───
    const startCameraStream = async (source) => {
        if (cameraEmpty) cameraEmpty.hidden = true;
        if (reticle) reticle.hidden = false;

        if (source === 'local') {
            // WEBCAM: Mở trực tiếp qua WebRTC (30-60 FPS mượt mà, không bị lock 503)
            if (camera) {
                camera.hidden = true;
                camera.style.display = 'none';
                camera.removeAttribute('src');
            }
            if (localVideo) {
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({
                        video: {
                            width: { ideal: 640 },
                            height: { ideal: 480 },
                            facingMode: 'user',
                        },
                        audio: false,
                    });
                    webRtcStream = stream;
                    localVideo.srcObject = stream;
                    await localVideo.play();
                    localVideo.hidden = false;
                    localVideo.style.display = 'block';
                } catch (err) {
                    console.error('Không thể mở Webcam qua WebRTC:', err);
                    localVideo.hidden = true;
                    localVideo.style.display = 'none';
                    if (cameraEmpty) {
                        cameraEmpty.hidden = false;
                        cameraEmpty.innerHTML = `
                            <div style="color: #ef4444; font-weight: 700; font-size: 14px; margin-bottom: 6px;">
                                ⚠️ Trình duyệt chưa được cấp quyền truy cập Webcam!
                            </div>
                            <div style="font-size: 12px; color: #cbd5e1; max-width: 440px; margin: 0 auto; line-height: 1.5;">
                                Vui lòng bấm vào biểu tượng Camera trên thanh địa chỉ trình duyệt để Cho phép (Allow) quyền truy cập.
                            </div>
                        `;
                    }
                }
            }
        } else {
            // ESP32-CAM: Mở luồng MJPEG Server Proxy Stream (25-30 FPS mượt mà)
            if (localVideo) {
                localVideo.hidden = true;
                localVideo.style.display = 'none';
                if (localVideo.srcObject) {
                    localVideo.srcObject.getTracks().forEach((t) => t.stop());
                    localVideo.srcObject = null;
                }
            }
            if (camera) {
                camera.hidden = false;
                camera.style.display = 'block';
                camera.src = `/?action=face_camera_stream&source=esp32&ts=${Date.now()}`;
            }
        }
    };

    const stopCameraStreams = () => {
        if (webRtcStream) {
            webRtcStream.getTracks().forEach((track) => track.stop());
            webRtcStream = null;
        }
        if (localVideo) {
            localVideo.hidden = true;
            localVideo.style.display = 'none';
            localVideo.srcObject = null;
        }
        if (camera) {
            camera.hidden = true;
            camera.style.display = 'none';
            camera.removeAttribute('src');
        }
    };

    const setCamera = (enabled) => {
        if (!enabled) {
            stopCameraStreams();
            if (cameraEmpty) cameraEmpty.hidden = false;
            if (reticle) reticle.hidden = true;
            setReticleMatched(false);
            return;
        }
        startCameraStream(currentSource);
    };

    const stopPosePolling = () => {
        clearInterval(poseTimer);
        poseTimer = null;
        running = false;
        busy = false;
        stableSince = 0;
        setReticleMatched(false);
        if (snapButton) snapButton.hidden = true;
    };

    if (camera) {
        camera.addEventListener('error', () => {
            if (currentSource === 'esp32' && running) {
                camera.hidden = true;
                if (reticle) reticle.hidden = true;
                if (cameraEmpty) {
                    cameraEmpty.hidden = false;
                    cameraEmpty.innerHTML = `
                        <div style="color: #ef4444; font-weight: 700; font-size: 14px; margin-bottom: 6px;">
                            ⚠️ Không kết nối được luồng video ESP32-CAM!
                        </div>
                        <div style="font-size: 12px; color: #cbd5e1; max-width: 440px; margin: 0 auto; line-height: 1.5;">
                            Vui lòng kiểm tra nguồn điện và mạng WiFi của ESP32-CAM (mặc định: http://esp32cam.local:81/stream).
                        </div>
                    `;
                }
            }
        });
    }

    const captureCurrentPose = async () => {
        busy = true;
        stableSince = 0;
        setReticleMatched(true, 100);
        try {
            const snapshot = getSnapshotBase64();
            const extra = snapshot ? { image: snapshot } : {};
            const { response, payload } = await post('face_enrollment_capture', extra);
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
                if (feedback) feedback.textContent = '🎉 Đã thu thập đủ 5/5 góc! Đang tự động lưu...';
                showResult('⏳ Đang tự động lưu 5 mẫu khuôn mặt vào hệ thống...', 'info');

                // Tự động lưu 5 mẫu khuôn mặt sau góc thứ 5
                try {
                    const { response: saveRes, payload: savePayload } = await post('face_enrollment_complete');
                    if (saveRes.ok && savePayload.success) {
                        showResult('✅ Đã lưu thành công 5 mẫu khuôn mặt và đồng bộ nhận diện AI!', 'success');
                        setTimeout(() => {
                            window.location.href = `/?action=face_registration&id=${encodeURIComponent(employeeId)}&ts=${Date.now()}`;
                        }, 1000);
                        return;
                    } else {
                        showResult(savePayload.message || 'Không thể lưu mẫu khuôn mặt.', 'error');
                        if (completeButton) {
                            completeButton.hidden = false;
                            completeButton.disabled = false;
                        }
                    }
                } catch (saveErr) {
                    showResult(saveErr.message || 'Không thể lưu mẫu khuôn mặt.', 'error');
                    if (completeButton) {
                        completeButton.hidden = false;
                        completeButton.disabled = false;
                    }
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
            const snapshot = getSnapshotBase64();
            const extra = snapshot ? { image: snapshot } : {};
            const { response, payload } = await post('face_enrollment_pose', extra);
            if (!response.ok || !payload.success) {
                stableSince = 0;
                setReticleMatched(false);
                if (feedback) feedback.textContent = payload.instruction || payload.message || 'Đang chờ phát hiện khuôn mặt...';
                return;
            }

            if (payload.pose_ok) {
                const now = Date.now();
                if (!stableSince) {
                    stableSince = now;
                    setReticleMatched(true, 30);
                    if (feedback) feedback.textContent = payload.instruction || `🎯 Đúng tư thế: ${poses[captured].label}! Giữ yên 0.25s để chụp...`;
                } else {
                    const elapsed = now - stableSince;
                    const percent = Math.min(100, Math.round((elapsed / HOLD_DURATION_MS) * 100));
                    setReticleMatched(true, percent);

                    if (elapsed >= HOLD_DURATION_MS) {
                        await captureCurrentPose();
                    }
                }
            } else {
                stableSince = 0;
                setReticleMatched(false);
                if (feedback) feedback.textContent = payload.instruction || payload.message || `Vui lòng xoay mặt theo hướng: ${poses[captured].label}.`;
                if (reticleHint && payload.instruction) reticleHint.textContent = payload.instruction;
            }
        } catch (error) {
            stableSince = 0;
            setReticleMatched(false);
            if (feedback) feedback.textContent = error.message || 'Lỗi kiểm tra hướng mặt.';
        } finally {
            busy = false;
        }
    };

    // Hỗ trợ nút Chụp Ngay và phím cách (SPACE) để chụp tức thì
    if (snapButton) {
        snapButton.addEventListener('click', (e) => {
            e.preventDefault();
            if (running && !busy && captured < poses.length) {
                captureCurrentPose();
            }
        });
    }

    window.addEventListener('keydown', (e) => {
        if (e.code === 'Space' && running && !busy && captured < poses.length) {
            e.preventDefault();
            captureCurrentPose();
        }
    });

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
            if (snapButton) {
                snapButton.hidden = false;
                snapButton.disabled = false;
            }

            try {
                const { response, payload } = await post('face_enrollment_start');
                if (!response.ok || !payload.success) {
                    throw new Error(payload.message || 'Không thể khởi tạo phiên đăng ký. Vui lòng kiểm tra AI Service trên cổng 5001.');
                }
                running = true;
                setCamera(true);
                if (feedback) feedback.textContent = `Camera đã kích hoạt. Nhìn vào tâm camera theo hướng: ${poses[0].label}.`;
                if (reticleHint) reticleHint.textContent = poses[0].guide;
                poseTimer = setInterval(pollPose, 450);
            } catch (error) {
                const errorMsg = error.message || 'Không thể khởi tạo phiên đăng ký.';
                showResult(errorMsg, 'error');
                startButton.disabled = false;
                if (deleteButton) deleteButton.disabled = false;
                if (snapButton) snapButton.hidden = true;
                setCamera(false);
            }
        });
    }

    // ── Nút Hủy phiên quét ────────────────────────────────────────────────
    if (cancelButton) {
        cancelButton.addEventListener('click', async () => {
            stopPosePolling();
            if (snapButton) snapButton.hidden = true;
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

    // ── Nút Lưu 5 mẫu khuôn mặt (dự phòng) ────────────────────────────────
    if (completeButton) {
        completeButton.addEventListener('click', async () => {
            completeButton.disabled = true;
            try {
                const { response, payload } = await post('face_enrollment_complete');
                if (!response.ok || !payload.success) {
                    throw new Error(payload.message || 'Không thể lưu mẫu khuôn mặt.');
                }
                showResult('✅ Đã lưu thành công 5 mẫu khuôn mặt và đồng bộ nhận diện AI!', 'success');
                setTimeout(() => {
                    window.location.href = `/?action=face_registration&id=${encodeURIComponent(employeeId)}&ts=${Date.now()}`;
                }, 1000);
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

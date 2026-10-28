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
    const startButton = document.querySelector('[data-face-start]');
    const deleteButton = document.querySelector('[data-face-delete]');
    const cancelButton = root.querySelector('[data-face-cancel]');
    const completeButton = root.querySelector('[data-face-complete]');
    const camera = root.querySelector('[data-face-camera]');
    const cameraEmpty = root.querySelector('[data-face-camera-empty]');
    const stepLabel = root.querySelector('[data-face-step]');
    const feedback = root.querySelector('[data-face-feedback]');
    const poseList = root.querySelector('[data-face-pose-list]');
    const result = document.querySelector('[data-face-result]');

    const poses = [
        { key: 'frontal', label: 'Chính diện' },
        { key: 'left', label: 'Nghiêng trái' },
        { key: 'right', label: 'Nghiêng phải' },
        { key: 'up', label: 'Ngẩng nhẹ' },
        { key: 'down', label: 'Cúi nhẹ' },
    ];

    let captured = 0;
    let running = false;
    let busy = false;
    let stableSince = 0;
    let poseTimer = null;
    let frameTimer = null;

    const post = async (action) => {
        const body = new URLSearchParams({ _csrf_token: csrfToken });
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
        if (poseList) {
            [...poseList.children].forEach((item, index) => {
                item.style.background = index < captured ? '#dcfce7' : (index === captured && captured < poses.length ? '#dbeafe' : '#f1f5f9');
                item.style.color = index < captured ? '#166534' : (index === captured && captured < poses.length ? '#1e40af' : '#475467');
                item.style.border = index === captured && captured < poses.length ? '1px solid #3b82f6' : '1px solid transparent';
            });
        }
    };

    const setCamera = (enabled) => {
        if (camera) camera.hidden = !enabled;
        if (cameraEmpty) cameraEmpty.hidden = enabled;
        if (!enabled) {
            if (camera) camera.removeAttribute('src');
            clearInterval(frameTimer);
            frameTimer = null;
            return;
        }
        const refreshFrame = () => {
            if (document.hidden || !running) return;
            if (camera) {
                camera.src = `/?action=face_camera_frame&ts=${Date.now()}`;
            }
        };
        refreshFrame();
        clearInterval(frameTimer);
        frameTimer = setInterval(refreshFrame, 400);
    };

    const stopPosePolling = () => {
        clearInterval(poseTimer);
        poseTimer = null;
        running = false;
        busy = false;
        stableSince = 0;
    };

    if (camera) {
        camera.addEventListener('error', () => {
            camera.hidden = true;
            if (cameraEmpty) {
                cameraEmpty.hidden = false;
                cameraEmpty.innerHTML = '<div style="color: #ef4444; font-weight: 500;">⚠️ Không kết nối được Camera!</div><div style="font-size: 13px; margin-top: 6px;">Vui lòng kiểm tra AI Service trên cổng 5001 hoặc nguồn Camera ESP32/Webcam.</div>';
            }
        });

        camera.addEventListener('load', () => {
            if (camera.naturalWidth > 0) {
                camera.hidden = false;
                if (cameraEmpty) cameraEmpty.hidden = true;
            }
        });
    }

    const captureCurrentPose = async () => {
        busy = true;
        stableSince = 0;
        try {
            const { response, payload } = await post('face_enrollment_capture');
            if (!response.ok || !payload.success) {
                if (feedback) feedback.textContent = payload.instruction || payload.message || 'Mẫu chưa đạt chuẩn, hãy giữ đúng hướng.';
                return;
            }
            captured = Number(payload.captured || captured + 1);
            renderStep();
            if (captured >= poses.length) {
                stopPosePolling();
                setCamera(false);
                if (feedback) feedback.textContent = '🎉 Đã thu thập đủ 5 góc! Nhấn nút "Lưu 5 mẫu khuôn mặt" bên dưới để hoàn tất.';
                if (completeButton) {
                    completeButton.hidden = false;
                    completeButton.disabled = false;
                }
            } else {
                if (feedback) feedback.textContent = `Chụp thành công! Chuyển sang góc tiếp theo: ${poses[captured].label}.`;
            }
        } catch (error) {
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
                if (feedback) feedback.textContent = payload.instruction || payload.message || 'Đang chờ phát hiện khuôn mặt...';
                return;
            }

            if (payload.pose_ok) {
                const now = Date.now();
                if (!stableSince) {
                    stableSince = now;
                    if (feedback) feedback.textContent = `Tư thế chuẩn: ${poses[captured].label}! Giữ nguyên để chụp...`;
                } else if (now - stableSince >= 700) {
                    await captureCurrentPose();
                }
            } else {
                stableSince = 0;
                if (feedback) feedback.textContent = payload.instruction || payload.message || `Vui lòng xoay mặt theo hướng: ${poses[captured].label}.`;
            }
        } catch (error) {
            stableSince = 0;
            if (feedback) feedback.textContent = error.message || 'Lỗi kiểm tra hướng mặt.';
        } finally {
            busy = false;
        }
    };

    // Bắt đầu đăng ký
    if (startButton) {
        startButton.addEventListener('click', async () => {
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
                    throw new Error(payload.message || 'Không thể khởi tạo phiên đăng ký.');
                }
                running = true;
                setCamera(true);
                if (feedback) feedback.textContent = `Đã mở camera. Hãy nhìn vào camera theo hướng: ${poses[0].label}.`;
                poseTimer = setInterval(pollPose, 600);
            } catch (error) {
                showResult(error.message, 'error');
                startButton.disabled = false;
                if (deleteButton) deleteButton.disabled = false;
                setCamera(false);
            }
        });
    }

    // Hủy phiên
    if (cancelButton) {
        cancelButton.addEventListener('click', async () => {
            stopPosePolling();
            setCamera(false);
            cancelButton.hidden = true;
            if (completeButton) completeButton.hidden = true;
            startButton.disabled = false;
            if (deleteButton) deleteButton.disabled = false;
            if (feedback) feedback.textContent = 'Đã hủy phiên đăng ký.';
            try {
                await post('face_enrollment_cancel');
            } catch {}
        });
    }

    // Lưu 5 mẫu
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

    // Xóa đăng ký
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

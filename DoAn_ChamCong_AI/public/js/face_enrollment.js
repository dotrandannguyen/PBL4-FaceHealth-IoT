(() => {
    const root = document.querySelector('[data-face-enrollment]');
    if (!root) return;

    const employeeId = root.dataset.employeeId;
    const csrfToken = root.dataset.csrf;
    const sampleCount = Number(root.dataset.faceCount || 0);
    const section = root.closest('.face-management');
    const startButton = section.querySelector('[data-face-start]');
    const deleteButton = section.querySelector('[data-face-delete]');
    const cancelButton = root.querySelector('[data-face-cancel]');
    const completeButton = root.querySelector('[data-face-complete]');
    const camera = root.querySelector('[data-face-camera]');
    const cameraEmpty = root.querySelector('[data-face-camera-empty]');
    const stepLabel = root.querySelector('[data-face-step]');
    const feedback = root.querySelector('[data-face-feedback]');
    const poseList = root.querySelector('[data-face-pose-list]');
    const result = section.querySelector('[data-face-result]');
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
        result.textContent = message;
        result.className = `notice face-enrollment-result notice--${kind}`;
        result.hidden = false;
    };

    const renderStep = () => {
        const step = poses[captured];
        stepLabel.textContent = step
            ? `Bước ${captured + 1}/5 · ${step.label}`
            : 'Đã hoàn tất 5/5 góc';
        [...poseList.children].forEach((item, index) => {
            item.classList.toggle('is-complete', index < captured);
            item.classList.toggle('is-active', index === captured && captured < poses.length);
        });
    };

    const setCamera = (enabled) => {
        camera.hidden = !enabled;
        cameraEmpty.hidden = enabled;
        if (!enabled) {
            camera.removeAttribute('src');
            clearInterval(frameTimer);
            frameTimer = null;
            return;
        }
        const refreshFrame = () => {
            camera.src = `/?action=face_camera_frame&ts=${Date.now()}`;
        };
        refreshFrame();
        clearInterval(frameTimer);
        frameTimer = setInterval(refreshFrame, 400);
    };

    const stopPosePolling = () => {
        clearInterval(poseTimer);
        poseTimer = null;
        running = false;
        stableSince = 0;
    };

    camera.addEventListener('error', () => {
        camera.hidden = true;
        cameraEmpty.hidden = false;
        cameraEmpty.textContent = 'Không kết nối được camera relay. Kiểm tra camera singleton và thử lại.';
    });

    camera.addEventListener('load', () => {
        if (camera.naturalWidth > 0) {
            camera.hidden = false;
            cameraEmpty.hidden = true;
        }
    });

    const captureCurrentPose = async () => {
        busy = true;
        stableSince = 0;
        try {
            const { response, payload } = await post('face_enrollment_capture');
            if (!response.ok || !payload.success) {
                feedback.textContent = payload.instruction || payload.message || 'Mẫu chưa hợp lệ, hãy giữ đúng hướng.';
                return;
            }
            captured = Number(payload.captured);
            renderStep();
            if (payload.complete) {
                stopPosePolling();
                completeButton.hidden = false;
                completeButton.disabled = false;
                cancelButton.hidden = true;
                feedback.textContent = 'Đã ghi nhận đủ 5 góc. Lưu batch để hoàn tất.';
            } else {
                feedback.textContent = 'Đã ghi nhận. Đang chuyển sang hướng tiếp theo.';
            }
        } catch (error) {
            feedback.textContent = error.message;
        } finally {
            busy = false;
        }
    };

    const inspectPose = async () => {
        if (!running || busy) return;
        busy = true;
        try {
            const { response, payload } = await post('face_enrollment_pose');
            if (!response.ok || !payload.success) {
                stableSince = 0;
                feedback.textContent = payload.message || 'Không đọc được frame từ camera.';
                return;
            }
            feedback.textContent = payload.instruction || 'Đang kiểm tra hướng khuôn mặt.';
            if (!payload.pose_ok) {
                stableSince = 0;
                return;
            }
            if (stableSince === 0) stableSince = Date.now();
            if (Date.now() - stableSince >= 800) {
                await captureCurrentPose();
            }
        } catch (error) {
            stableSince = 0;
            feedback.textContent = error.message;
        } finally {
            busy = false;
        }
    };

    startButton.addEventListener('click', async () => {
        if (sampleCount > 0 && !window.confirm('Mẫu khuôn mặt cũ sẽ được giữ nguyên cho đến khi đủ 5 mẫu mới và lưu thành công. Bắt đầu đăng ký lại?')) {
            return;
        }
        startButton.disabled = true;
        try {
            const { response, payload } = await post('face_enrollment_start');
            if (!response.ok || !payload.success) throw new Error(payload.message || 'Không thể bắt đầu đăng ký.');
            captured = 0;
            renderStep();
            root.hidden = false;
            result.hidden = true;
            setCamera(true);
            cancelButton.hidden = false;
            completeButton.hidden = true;
            completeButton.disabled = true;
            feedback.textContent = 'Đang chờ khuôn mặt trước camera.';
            running = true;
            poseTimer = setInterval(inspectPose, 500);
        } catch (error) {
            showResult(error.message, 'error');
        } finally {
            startButton.disabled = false;
        }
    });

    completeButton.addEventListener('click', async () => {
        completeButton.disabled = true;
        try {
            const { response, payload } = await post('face_enrollment_complete');
            if (!response.ok || !payload.success) throw new Error(payload.message || 'Không thể lưu batch.');
            showResult(payload.gallery_updated
                ? 'Đã lưu 5 mẫu khuôn mặt và làm mới gallery AI.'
                : 'Đã lưu 5 mẫu. Gallery AI chưa làm mới; dữ liệu cũ vẫn an toàn.', 'success');
            setTimeout(() => window.location.reload(), 900);
        } catch (error) {
            completeButton.disabled = false;
            showResult(error.message, 'error');
        }
    });

    cancelButton.addEventListener('click', async () => {
        stopPosePolling();
        try {
            await post('face_enrollment_cancel');
        } catch {
            // The PHP session expires automatically if cancellation cannot reach the server.
        }
        root.hidden = true;
        setCamera(false);
        showResult('Đã hủy phiên. Chưa có mẫu nào được lưu.', 'info');
    });

    if (deleteButton) {
        deleteButton.addEventListener('click', async () => {
            if (!window.confirm('Xóa toàn bộ mẫu khuôn mặt của nhân viên này? Hồ sơ, tài khoản và lịch sử chấm công sẽ được giữ nguyên.')) return;
            deleteButton.disabled = true;
            try {
                const { response, payload } = await post('face_registration_delete');
                if (!response.ok || !payload.success) throw new Error(payload.message || 'Không thể xóa đăng ký.');
                showResult('Đã xóa toàn bộ mẫu khuôn mặt.', 'success');
                setTimeout(() => window.location.reload(), 700);
            } catch (error) {
                deleteButton.disabled = false;
                showResult(error.message, 'error');
            }
        });
    }

    const dialog = document.querySelector('[data-face-lightbox]');
    const dialogImage = dialog.querySelector('[data-face-lightbox-image]');
    const dialogTitle = dialog.querySelector('[data-face-lightbox-title]');
    section.querySelectorAll('[data-face-preview]').forEach((button) => {
        button.addEventListener('click', () => {
            dialogImage.src = button.dataset.facePreview;
            dialogTitle.textContent = button.getAttribute('aria-label') || 'Ảnh mẫu khuôn mặt';
            dialog.showModal();
        });
    });
    dialog.querySelector('[data-face-lightbox-close]').addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', (event) => {
        if (event.target === dialog) dialog.close();
    });
    dialog.addEventListener('close', () => {
        dialogImage.removeAttribute('src');
    });
})();

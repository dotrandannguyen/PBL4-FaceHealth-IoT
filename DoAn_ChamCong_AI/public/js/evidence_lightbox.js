(() => {
    const dialog = document.getElementById('evidence-lightbox');
    const image = document.getElementById('evidence-lightbox-image');
    const title = document.getElementById('evidence-lightbox-title');
    const kind = document.getElementById('evidence-lightbox-kind');
    const meta = document.getElementById('evidence-lightbox-meta');
    const close = document.getElementById('evidence-lightbox-close');

    if (!dialog || !image || !title || !kind || !meta || !close) return;

    document.addEventListener('click', (event) => {
        const button = event.target.closest('[data-evidence-open]');
        if (!button) return;

        image.src = button.dataset.evidenceSrc || '';
        title.textContent = button.dataset.evidencePerson || 'Nhân viên';
        kind.textContent = button.dataset.evidenceKind || 'Ảnh bằng chứng';
        meta.textContent = [button.dataset.evidenceCode, button.dataset.evidenceTime]
            .filter(Boolean)
            .join(' · ');
        dialog.showModal();
    });

    close.addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', (event) => {
        if (event.target === dialog) dialog.close();
    });
    dialog.addEventListener('close', () => {
        image.removeAttribute('src');
    });
})();

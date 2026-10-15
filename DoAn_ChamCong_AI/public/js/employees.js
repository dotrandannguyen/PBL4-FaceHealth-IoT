(() => {
    const input = document.querySelector('#employee-search');
    const rows = [...document.querySelectorAll('.employee-row')];
    const visibleCount = document.querySelector('#visible-count');
    const emptySearch = document.querySelector('#empty-search');

    if (!input || rows.length === 0 || !visibleCount || !emptySearch) return;

    const normalize = (value) => value
        .toLocaleLowerCase('vi')
        .normalize('NFD')
        .replace(/\p{Diacritic}/gu, '')
        .trim();

    input.addEventListener('input', () => {
        const query = normalize(input.value);
        let visible = 0;

        rows.forEach((row) => {
            const matches = normalize(row.dataset.search || '').includes(query);
            row.hidden = !matches;
            if (matches) visible += 1;
        });

        visibleCount.textContent = String(visible);
        emptySearch.hidden = visible !== 0;
    });
})();

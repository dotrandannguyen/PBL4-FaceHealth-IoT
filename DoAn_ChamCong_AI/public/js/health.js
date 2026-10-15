(() => {
    const chart = document.getElementById('health-chart');
    const dataNode = document.getElementById('health-chart-data');
    if (!chart || !dataNode) return;

    const points = JSON.parse(dataNode.textContent || '[]')
        .filter((row) => row.NhipTim !== null && row.NhipTim !== '')
        .map((row) => ({
            value: Number(row.NhipTim),
            time: row.ThoiGian ? String(row.ThoiGian).slice(11, 19) : '--',
        }))
        .filter((point) => Number.isFinite(point.value));
    if (points.length === 0) return;

    const ns = 'http://www.w3.org/2000/svg';
    const add = (tag, attrs, text) => {
        const node = document.createElementNS(ns, tag);
        Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
        if (text !== undefined) node.textContent = text;
        chart.appendChild(node);
        return node;
    };
    const left = 42;
    const right = 786;
    const top = 24;
    const bottom = 174;
    const values = points.map((point) => point.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const coordinates = points.map((point, index) => ({
        ...point,
        x: points.length === 1 ? (left + right) / 2 : left + (index / (points.length - 1)) * (right - left),
        y: bottom - ((point.value - min) / span) * (bottom - top),
    }));

    [top, (top + bottom) / 2, bottom].forEach((y) => {
        add('line', { x1: left, y1: y, x2: right, y2: y, class: 'health-chart-gridline' });
    });
    add('polyline', {
        points: coordinates.map((point) => `${point.x},${point.y}`).join(' '),
        class: 'health-chart-line',
    });
    coordinates.forEach((point, index) => {
        add('circle', { cx: point.x, cy: point.y, r: 4, class: 'health-chart-point' });
        if (points.length <= 10 || index === 0 || index === points.length - 1 || index % 3 === 0) {
            add('text', { x: point.x, y: point.y - 9, class: 'health-chart-value', 'text-anchor': 'middle' }, String(point.value));
            add('text', { x: point.x, y: 202, class: 'health-chart-label', 'text-anchor': 'middle' }, point.time);
        }
    });
})();

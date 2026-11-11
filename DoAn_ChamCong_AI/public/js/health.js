(() => {
    const chart = document.getElementById('health-chart');
    const dataNode = document.getElementById('health-chart-data');
    const tooltip = document.getElementById('chart-tooltip');
    if (!chart || !dataNode) return;

    let rawData = [];
    try {
        rawData = JSON.parse(dataNode.textContent || '[]');
    } catch (e) {
        return;
    }

    const points = rawData
        .filter((row) => row && row.NhipTim !== null && row.NhipTim !== '')
        .map((row) => ({
            hr: Number(row.NhipTim),
            spo2: row.SpO2 !== null && row.SpO2 !== '' ? Number(row.SpO2) : null,
            status: String(row.TheTrang || 'Bình thường'),
            rawTime: String(row.ThoiGian || ''),
            timeShort: row.ThoiGian ? String(row.ThoiGian).slice(11, 19) : '--',
            dateShort: row.ThoiGian ? String(row.ThoiGian).slice(5, 10) : '',
        }))
        .filter((p) => Number.isFinite(p.hr));

    if (points.length === 0) return;

    const ns = 'http://www.w3.org/2000/svg';
    const add = (tag, attrs, text) => {
        const node = document.createElementNS(ns, tag);
        Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)));
        if (text !== undefined) node.textContent = text;
        chart.appendChild(node);
        return node;
    };

    // Chart layout dimensions
    const width = 840;
    const height = 240;
    const left = 55;
    const right = 785;
    const top = 30;
    const bottom = 185;

    // Heart Rate Scale (BPM)
    const hrValues = points.map((p) => p.hr);
    const minHrRaw = Math.min(...hrValues);
    const maxHrRaw = Math.max(...hrValues);
    const hrMin = Math.max(40, Math.floor((minHrRaw - 8) / 10) * 10);
    const hrMax = Math.min(160, Math.ceil((maxHrRaw + 8) / 10) * 10);
    const hrSpan = (hrMax - hrMin) || 1;

    // SpO2 Scale (%)
    const spo2Min = 85;
    const spo2Max = 100;
    const spo2Span = spo2Max - spo2Min;

    const getX = (index) => {
        if (points.length === 1) return (left + right) / 2;
        return left + (index / (points.length - 1)) * (right - left);
    };

    const getY_Hr = (hr) => {
        const clamped = Math.max(hrMin, Math.min(hrMax, hr));
        return bottom - ((clamped - hrMin) / hrSpan) * (bottom - top);
    };

    const getY_Spo2 = (spo2) => {
        if (spo2 === null || !Number.isFinite(spo2)) return null;
        const clamped = Math.max(spo2Min, Math.min(spo2Max, spo2));
        return bottom - ((clamped - spo2Min) / spo2Span) * (bottom - top);
    };

    // Draw horizontal grid lines & BPM axis labels
    const gridSteps = 4;
    for (let i = 0; i <= gridSteps; i++) {
        const ratio = i / gridSteps;
        const y = bottom - ratio * (bottom - top);
        const hrVal = Math.round(hrMin + ratio * hrSpan);

        add('line', {
            x1: left,
            y1: y,
            x2: right,
            y2: y,
            class: 'health-chart-gridline',
            stroke: '#e5e7eb',
            'stroke-dasharray': i === 0 || i === gridSteps ? 'none' : '3 3'
        });

        // Left label: BPM
        add('text', {
            x: left - 8,
            y: y + 4,
            class: 'health-chart-axis-label',
            'text-anchor': 'end',
            fill: '#6b7280',
            'font-size': '11px',
            'font-weight': '500'
        }, `${hrVal}`);

        // Right label: SpO2 %
        const spo2Val = Math.round(spo2Min + ratio * spo2Span);
        add('text', {
            x: right + 8,
            y: y + 4,
            class: 'health-chart-axis-label',
            'text-anchor': 'start',
            fill: '#0d9488',
            'font-size': '11px',
            'font-weight': '500'
        }, `${spo2Val}%`);
    }

    // Normal safe zone reference bands (BPM: 60 - 100 bpm)
    if (hrMax >= 60 && hrMin <= 100) {
        const safeTop = getY_Hr(Math.min(100, hrMax));
        const safeBottom = getY_Hr(Math.max(60, hrMin));
        add('rect', {
            x: left,
            y: safeTop,
            width: right - left,
            height: safeBottom - safeTop,
            fill: 'rgba(16, 185, 129, 0.04)',
            class: 'health-chart-safezone'
        });
    }

    // Calculate Coordinates
    const coordinates = points.map((p, index) => ({
        ...p,
        index,
        x: getX(index),
        yHr: getY_Hr(p.hr),
        ySpo2: getY_Spo2(p.spo2)
    }));

    // Draw SpO2 Polyline (Dashed teal)
    const validSpo2Coords = coordinates.filter((c) => c.ySpo2 !== null);
    if (validSpo2Coords.length > 1) {
        add('polyline', {
            points: validSpo2Coords.map((c) => `${c.x},${c.ySpo2}`).join(' '),
            fill: 'none',
            stroke: '#0d9488',
            'stroke-width': '2',
            'stroke-dasharray': '5 4',
            'stroke-linecap': 'round',
            'stroke-linejoin': 'round',
            opacity: '0.8'
        });
    }

    // Draw Heart Rate Polyline (Solid royal blue)
    if (coordinates.length > 1) {
        // Gradient fill under HR curve
        const areaPoints = [
            `${coordinates[0].x},${bottom}`,
            ...coordinates.map((c) => `${c.x},${c.yHr}`),
            `${coordinates[coordinates.length - 1].x},${bottom}`
        ].join(' ');

        add('polygon', {
            points: areaPoints,
            fill: 'rgba(37, 99, 235, 0.06)',
            stroke: 'none'
        });

        add('polyline', {
            points: coordinates.map((c) => `${c.x},${c.yHr}`).join(' '),
            fill: 'none',
            stroke: '#2563eb',
            'stroke-width': '2.5',
            'stroke-linecap': 'round',
            'stroke-linejoin': 'round'
        });
    }

    // Draw measurement dots, value labels and hover interactions
    coordinates.forEach((point) => {
        // Dot Color based on Status
        let dotColor = '#10b981'; // Bình thường
        let dotStroke = '#059669';
        let dotRadius = 4.5;

        if (point.status === 'Kiệt sức' || point.hr >= 110 || (point.spo2 && point.spo2 < 94)) {
            dotColor = '#ef4444';
            dotStroke = '#b91c1c';
            dotRadius = 6;
        } else if (point.status === 'Mệt mỏi' || point.hr >= 95 || (point.spo2 && point.spo2 < 96)) {
            dotColor = '#f59e0b';
            dotStroke = '#d97706';
            dotRadius = 5.5;
        }

        // SpO2 small diamond/dot
        if (point.ySpo2 !== null) {
            add('rect', {
                x: point.x - 3,
                y: point.ySpo2 - 3,
                width: 6,
                height: 6,
                transform: `rotate(45, ${point.x}, ${point.ySpo2})`,
                fill: '#0d9488',
                stroke: '#ffffff',
                'stroke-width': 1.5,
                opacity: '0.85'
            });
        }

        // Heart Rate Main Circle
        const circle = add('circle', {
            cx: point.x,
            cy: point.yHr,
            r: dotRadius,
            fill: dotColor,
            stroke: '#ffffff',
            'stroke-width': '2',
            style: 'cursor: pointer; transition: transform 0.15s ease;'
        });

        // Value text above point
        const shouldShowValue = points.length <= 15 || point.index === 0 || point.index === points.length - 1 || point.index % 2 === 0;
        if (shouldShowValue) {
            add('text', {
                x: point.x,
                y: point.yHr - 10,
                class: 'health-chart-value',
                'text-anchor': 'middle',
                fill: '#111827',
                'font-size': '11px',
                'font-weight': '600'
            }, `${point.hr}`);

            // X-axis time label below
            add('text', {
                x: point.x,
                y: bottom + 18,
                class: 'health-chart-time-label',
                'text-anchor': 'middle',
                fill: '#6b7280',
                'font-size': '10px'
            }, point.timeShort);

            if (point.dateShort && (point.index === 0 || point.index === points.length - 1)) {
                add('text', {
                    x: point.x,
                    y: bottom + 30,
                    class: 'health-chart-date-label',
                    'text-anchor': 'middle',
                    fill: '#9ca3af',
                    'font-size': '9px'
                }, point.dateShort);
            }
        }

        // Tooltip interaction
        if (tooltip) {
            const showTooltip = (evt) => {
                circle.setAttribute('r', String(dotRadius + 2.5));
                circle.setAttribute('stroke', '#1e293b');
                circle.setAttribute('stroke-width', '3');

                let statusBadge = '<span style="color:#10b981;font-weight:600;">🟢 Bình thường</span>';
                if (point.status === 'Kiệt sức') {
                    statusBadge = '<span style="color:#ef4444;font-weight:600;">🔴 Kiệt sức</span>';
                } else if (point.status === 'Mệt mỏi') {
                    statusBadge = '<span style="color:#f59e0b;font-weight:600;">🟡 Mệt mỏi</span>';
                }

                tooltip.innerHTML = `
                    <div style="font-weight:600;margin-bottom:4px;border-bottom:1px solid #374151;padding-bottom:3px;">
                        🕒 ${point.rawTime.slice(0, 19)}
                    </div>
                    <div style="display:flex;justify-content:space-between;gap:12px;margin:2px 0;">
                        <span>💓 Nhịp tim:</span>
                        <strong style="color:#60a5fa;">${point.hr} bpm</strong>
                    </div>
                    <div style="display:flex;justify-content:space-between;gap:12px;margin:2px 0;">
                        <span>🫁 SpO₂:</span>
                        <strong style="color:#2dd4bf;">${point.spo2 !== null ? point.spo2 + ' %' : '--'}</strong>
                    </div>
                    <div style="display:flex;justify-content:space-between;gap:12px;margin-top:4px;border-top:1px dashed #374151;padding-top:3px;">
                        <span>Thể trạng AI:</span>
                        <span>${statusBadge}</span>
                    </div>
                `;
                tooltip.style.display = 'block';

                const rect = chart.getBoundingClientRect();
                const chartWrap = chart.parentElement.getBoundingClientRect();
                const svgScaleX = rect.width / width;
                const svgScaleY = rect.height / height;

                const posX = point.x * svgScaleX;
                const posY = point.yHr * svgScaleY;

                tooltip.style.left = `${Math.min(chartWrap.width - 180, Math.max(10, posX - 90))}px`;
                tooltip.style.top = `${Math.max(10, posY - 100)}px`;
            };

            const hideTooltip = () => {
                circle.setAttribute('r', String(dotRadius));
                circle.setAttribute('stroke', '#ffffff');
                circle.setAttribute('stroke-width', '2');
                tooltip.style.display = 'none';
            };

            circle.addEventListener('mouseenter', showTooltip);
            circle.addEventListener('mouseleave', hideTooltip);
            circle.addEventListener('touchstart', showTooltip, { passive: true });
        }
    });
})();

const CHANNEL_COLORS = ['yellow', 'cyan', 'magenta', '#00aaff'];
let lastChannelValues = {
    CH1: { value: null, time: null },
    CH2: { value: null, time: null },
    CH3: { value: null, time: null },
    CH4: { value: null, time: null }
};

let oscilloscopeTestLiveData = {
    CH1: [],
    CH2: [],
    CH3: [],
    CH4: [],
    index: 0
};

let oscilloscopeTestData = {
    timestamps: [],
    channels: {
        CH1: { values: [], active: true },
        CH2: { values: [], active: true },
        CH3: { values: [], active: true },
        CH4: { values: [], active: true }
    }
};

function updateOscilloscopeData(data) {
    if (!measurementsActive) return;
    renderOscilloscopeSVG(data.channels);
    const trigger = data.trigger || { level: 1.23, mode: 'Auto', source: 'CH1', slope: 'Rising' };
    renderChannelInfoSVG(data.channels, trigger);
    renderOscilloscopeChannelControls(data.channels);
    if (data.trigger) {
        updateTriggerInfo(data.trigger);
    } else {
        updateTriggerInfo({ level: 1.23, mode: 'Auto', source: 'CH1', slope: 'Rising' });
    }
}

function updateChannelInfo(channelName, settings) {
    const channelInfo = document.getElementById(`${channelName.toLowerCase()}_info`);
    if (channelInfo && settings) {
        const info = [
            `Volts/Div: ${settings.volts_div}V`,
            `Offset: ${settings.offset}V`,
            `Coupling: ${settings.coupling}`,
            `Display: ${settings.display === '1' ? 'On' : 'Off'}`
        ].join('<br>');
        channelInfo.innerHTML = info;
    }
}

function updateTriggerLevel(level) {
    const triggerInfo = document.getElementById('trigger_info');
    if (triggerInfo) {
        triggerInfo.textContent = `Trigger Level: ${level}V`;
    }
}

function renderOscilloscopeSVG(channelsData) {
    const width = 2700, height = 1000, padding = 60, gridCountY = 6, gridCountX = 10;
    let svg = `<svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}" style="background:#000;display:block;">`;
    let allTimes = [], allVoltages = [];
    Object.values(channelsData).forEach(ch => {
        if (ch.time && ch.voltage) {
            allTimes = allTimes.concat(ch.time);
            allVoltages = allVoltages.concat(ch.voltage);
        }
    });
    if (allTimes.length === 0 || allVoltages.length === 0) {
        svg += '</svg>';
        document.getElementById('oscilloscopeSVG').innerHTML = svg;
        return;
    }
    let minT = Math.min(...allTimes), maxT = Math.max(...allTimes);
    let minV = Math.min(...allVoltages), maxV = Math.max(...allVoltages);
    let padV = (maxV - minV) * 0.1 || 1;
    minV -= padV; maxV += padV;
    for (let i = 0; i <= gridCountY; i++) {
        let y = padding + ((height - 2 * padding) * i) / gridCountY;
        let v = (maxV - minV) * (1 - i / gridCountY) + minV;
        svg += `<line x1="${padding}" y1="${y}" x2="${width - padding}" y2="${y}" stroke="#222"/>`;
        svg += `<text x="${padding - 8}" y="${y + 4}" fill="#888" font-size="14" text-anchor="end">${v.toFixed(2)}</text>`;
    }
    for (let i = 0; i <= gridCountX; i++) {
        let x = padding + ((width - 2 * padding) * i) / gridCountX;
        let t = (maxT - minT) * (i / gridCountX) + minT;
        svg += `<line x1="${x}" y1="${padding}" x2="${x}" y2="${height - padding}" stroke="#222"/>`;
        svg += `<text x="${x}" y="${height - padding + 22}" fill="#888" font-size="14" text-anchor="middle">${t.toFixed(2)}</text>`;
    }
    Object.entries(channelsData).forEach(([ch, chData], idx) => {
        if (!chData.voltage || !chData.time || chData.voltage.length === 0) return;
        const color = chData.color || ['yellow', 'cyan', 'magenta', '#00aaff'][idx];
        let points = chData.time.map((t, i) => {
            let x = padding + ((t - minT) / ((maxT - minT) || 1)) * (width - 2 * padding);
            let y = padding + (height - 2 * padding) * (1 - (chData.voltage[i] - minV) / ((maxV - minV) || 1));
            return `${x},${y}`;
        }).join(' ');
        svg += `<polyline fill="none" stroke="${color}" stroke-width="2" points="${points}"/>`;
    });
    let legendX = width - padding - 120, legendY = padding;
    Object.entries(channelsData).forEach(([ch, chData], idx) => {
        const color = chData.color || ['yellow', 'cyan', 'magenta', '#00aaff'][idx];
        svg += `<rect x="${legendX}" y="${legendY + idx * 26}" width="22" height="10" fill="${color}" />`;
        svg += `<text x="${legendX + 30}" y="${legendY + idx * 26 + 10}" fill="#fff" font-size="16">${ch}</text>`;
    });
    svg += `</svg>`;
    document.getElementById('oscilloscopeSVG').innerHTML = svg;
}

function renderChannelInfoSVG(channelsData, triggerData) {
    const svgElem = document.getElementById('channelInfoSVG');
    if (!svgElem) return;
    const cardW = 260, cardH = 120, gap = 18;
    const nChannels = Object.keys(channelsData).length;
    const totalCards = nChannels + 1;
    const svgW = Math.max(totalCards * (cardW + gap) + gap, 900);
    const svgH = cardH + 20;
    svgElem.setAttribute('viewBox', `0 0 ${svgW} ${svgH}`);
    svgElem.setAttribute('width', '100%');
    svgElem.setAttribute('height', svgH);
    let svg = '';
    const trigX = gap, trigY = 10;
    svg += `
      <g>
        <rect x="${trigX}" y="${trigY}" width="${cardW}" height="${cardH}" rx="12" fill="#222" stroke="#ff9800" stroke-width="2.5"/>
        <text x="${trigX+18}" y="${trigY+32}" fill="#ff9800" font-size="22" font-family="monospace" font-weight="bold">Триггер</text>
        <text x="${trigX+cardW-18}" y="${trigY+32}" fill="#2ecc71" font-size="16" font-family="monospace" text-anchor="end">${triggerData.mode||'Auto'}</text>
        <text x="${trigX+18}" y="${trigY+60}" fill="#fff" font-size="16" font-family="monospace"><tspan fill="#00ccff">Уровень:</tspan> <tspan fill="#ff0">${triggerData.level!==undefined?triggerData.level:'--'} В</tspan></text>
        <text x="${trigX+18}" y="${trigY+84}" fill="#fff" font-size="16" font-family="monospace"><tspan fill="#00ccff">Источник:</tspan> <tspan fill="#0ff">${triggerData.source||'CH1'}</tspan></text>
        <text x="${trigX+18}" y="${trigY+108}" fill="#fff" font-size="16" font-family="monospace"><tspan fill="#00ccff">Slope:</tspan> <tspan fill="#0f0">${triggerData.slope||'Rising'}</tspan></text>
      </g>
    `;
    let idx = 0;
    Object.entries(channelsData).forEach(([ch, chData]) => {
        const x = gap + (cardW + gap) * (idx + 1);
        const y = trigY;
        const color = chData.color || ['yellow', 'cyan', 'magenta', '#00aaff'][idx];
        const settings = chData.settings || {};
        const isActive = settings.display === '1' || settings.display === 1 || settings.display === true;
        svg += `
          <g>
            <rect x="${x}" y="${y}" width="${cardW}" height="${cardH}" rx="12" fill="#222" stroke="${color}" stroke-width="2.5" opacity="${isActive?'1':'0.5'}"/>
            <text x="${x+18}" y="${y+32}" fill="${color}" font-size="22" font-family="monospace" font-weight="bold">${ch}</text>
            <text x="${x+cardW-18}" y="${y+32}" fill="${isActive?'#2ecc71':'#e74c3c'}" font-size="16" font-family="monospace" text-anchor="end">${isActive?'Активен':'Отключен'}</text>
            <text x="${x+18}" y="${y+60}" fill="#00ccff" font-size="16" font-family="monospace">Volts/Div: <tspan fill="#fff">${settings.volts_div??'--'} В</tspan></text>
            <text x="${x+18}" y="${y+80}" fill="#00ccff" font-size="16" font-family="monospace">Offset: <tspan fill="#fff">${settings.offset??'--'} В</tspan></text>
            <text x="${x+18}" y="${y+100}" fill="#00ccff" font-size="16" font-family="monospace">Coupling: <tspan fill="#fff">${settings.coupling??'--'}</tspan></text>
            <text x="${x+18}" y="${y+120}" fill="#00ccff" font-size="16" font-family="monospace">Display: <tspan fill="#fff">${isActive?'On':'Off'}</tspan></text>
          </g>
        `;
        idx++;
    });
    svgElem.innerHTML = svg;
}

function renderOscilloscopeChannelControls(channelsData) {
    const controlsBlock = document.querySelector('#oscilloscopeChannelControls .d-flex');
    if (!controlsBlock) return;
    controlsBlock.innerHTML = '';
    const couplingOptions = [
        { value: 'DC', label: 'DC' },
        { value: 'AC', label: 'AC' },
        { value: 'GND', label: 'GND' }
    ];
    Object.entries(channelsData).forEach(([ch, chData], idx) => {
        const settings = chData.settings || {};
        const color = chData.color || CHANNEL_COLORS[idx] || 'yellow';
        const isActive = settings.display === '1' || settings.display === 1 || settings.display === true;
        const card = document.createElement('div');
        card.className = 'p-2 border rounded bg-secondary bg-opacity-10';
        card.style.minWidth = '220px';
        card.style.maxWidth = '260px';
        card.style.borderColor = color;
        card.style.boxShadow = '0 1px 4px rgba(0,0,0,0.12)';
        card.innerHTML = `
            <div class="mb-2" style="color:${color};font-weight:bold;font-size:1.1em;">${ch}</div>
            <div class="form-check form-switch mb-2">
                <input class="form-check-input" type="checkbox" id="${ch}_display" ${isActive ? 'checked' : ''}>
                <label class="form-check-label" for="${ch}_display">Включить канал</label>
            </div>
            <div class="mb-2">
                <label for="${ch}_volts_div" class="form-label mb-0">Volts/Div</label>
                <input type="number" step="0.01" min="0.001" max="50" class="form-control form-control-sm" id="${ch}_volts_div" value="${settings.volts_div ?? ''}" style="max-width:90px;display:inline-block;">
            </div>
            <div class="mb-2">
                <label for="${ch}_offset" class="form-label mb-0">Offset</label>
                <input type="number" step="0.01" min="-100" max="100" class="form-control form-control-sm" id="${ch}_offset" value="${settings.offset ?? ''}" style="max-width:90px;display:inline-block;">
            </div>
            <div class="mb-2">
                <label for="${ch}_coupling" class="form-label mb-0">Coupling</label>
                <select class="form-select form-select-sm" id="${ch}_coupling" style="max-width:90px;display:inline-block;">
                    ${couplingOptions.map(opt => `<option value="${opt.value}" ${settings.coupling === opt.value ? 'selected' : ''}>${opt.label}</option>`).join('')}
                </select>
            </div>
        `;
        controlsBlock.appendChild(card);
        setTimeout(() => {
            card.querySelector(`#${ch}_display`).onchange = function() {
                sendOscChannelSettings(ch, {
                    display: this.checked ? 1 : 0
                });
            };
            card.querySelector(`#${ch}_volts_div`).onchange = function() {
                sendOscChannelSettings(ch, {
                    volts_div: parseFloat(this.value)
                });
            };
            card.querySelector(`#${ch}_offset`).onchange = function() {
                sendOscChannelSettings(ch, {
                    offset: parseFloat(this.value)
                });
            };
            card.querySelector(`#${ch}_coupling`).onchange = function() {
                sendOscChannelSettings(ch, {
                    coupling: this.value
                });
            };
        }, 0);
    });
}

function sendOscChannelSettings(channel, settings) {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify({
            action: 'set_channel_settings',
            channel: channel,
            settings: settings
        }));
    }
}

function updateTriggerInfo(trigger) {
    let infoBlock = document.getElementById('oscilloscopeTriggerInfo');
    if (!infoBlock) {
        const parent = document.getElementById('oscilloscopeChannelControls');
        infoBlock = document.createElement('div');
        infoBlock.id = 'oscilloscopeTriggerInfo';
        infoBlock.className = 'mt-2 mb-2 p-2 bg-dark rounded border border-warning';
        if (parent) parent.parentElement.insertBefore(infoBlock, parent.nextSibling);
    }
    if (!trigger) {
        infoBlock.innerHTML = '<span class="text-warning">Нет данных о триггере</span>';
        return;
    }
    infoBlock.innerHTML = `
        <span style="color:#ff9800;font-weight:bold;">Триггер:</span>
        <span class="ms-3"><b>Уровень:</b>
            <input type="number" id="triggerLevelInput" style="width:80px" step="0.01" value="${trigger.level !== undefined ? trigger.level : ''}"> В
        </span>
        <span class="ms-3"><b>Режим:</b> <span style="color:#0ff;">${trigger.mode || '--'}</span></span>
        <span class="ms-3"><b>Источник:</b> <span style="color:#0ff;">${trigger.source || '--'}</span></span>
        <span class="ms-3"><b>Фронт:</b> <span style="color:#0f0;">${trigger.slope || '--'}</span></span>
    `;
    const input = document.getElementById('triggerLevelInput');
    if (input) {
        input.onchange = function() {
            const newLevel = parseFloat(input.value);
            if (!isNaN(newLevel) && websocket && websocket.readyState === WebSocket.OPEN) {
                websocket.send(JSON.stringify({
                    action: 'set_trigger',
                    trigger: { ...trigger, level: newLevel }
                }));
            }
        };
    }
}

function renderChannelInfoBlock(containerId, channelsData) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '';
    Object.entries(channelsData).forEach(([channelName, channelData], idx) => {
        if (channelData && channelData.settings) {
            const color = channelData.color || CHANNEL_COLORS[idx] || 'yellow';
            const settings = channelData.settings;
            const isActive = settings.display === '1' || settings.display === 1 || settings.display === true;
            const card = document.createElement('div');
            card.className = 'channel-card';
            card.style.borderColor = color;
            card.style.opacity = isActive ? '1' : '0.5';
            card.innerHTML = `
                <div class="channel-header">
                    <h5 style="color:${color}">${channelName}</h5>
                    <span style="font-size:0.9em; color:${isActive ? '#2ecc71' : '#e74c3c'}">${isActive ? 'Активен' : 'Отключен'}</span>
                </div>
                <div class="settings-group">
                    <div><strong>Volts/Div:</strong> ${settings.volts_div} В</div>
                    <div><strong>Offset:</strong> ${settings.offset} В</div>
                    <div><strong>Coupling:</strong> ${settings.coupling}</div>
                    <div><strong>Display:</strong> ${settings.display === '1' ? 'On' : 'Off'}</div>
                </div>
            `;
            container.appendChild(card);
        }
    });
}

function updateOscilloscopeChartTestLive() {
    renderOscilloscopeSVGTest(oscilloscopeTestLiveData);
    const channelsBlock = {};
    ['CH1', 'CH2', 'CH3', 'CH4'].forEach((ch, i) => {
        const chData = oscilloscopeTestLiveData[ch];
        if (chData && chData.settings) {
            channelsBlock[ch] = {
                settings: chData.settings,
                color: chData.color || CHANNEL_COLORS[i]
            };
        }
    });
    const trigger = window.oscilloscopeTestTrigger || { level: 1.23, mode: 'Auto', source: 'CH1', slope: 'Rising' };
    renderChannelInfoSVGTest(channelsBlock, trigger);
}

function renderOscilloscopeSVGTest(channelsData) {
    const width = 2700, height = 800, padding = 60, gridCountY = 6, gridCountX = 10;
    let svg = `<svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}" style="background:#000;display:block;">`;
    let allTimes = [], allVoltages = [];
    Object.values(channelsData).forEach(ch => {
        if (ch.time && ch.voltage) {
            allTimes = allTimes.concat(ch.time);
            allVoltages = allVoltages.concat(ch.voltage);
        }
    });
    if (allTimes.length === 0 || allVoltages.length === 0) {
        svg += '</svg>';
        const el = document.getElementById('oscilloscopeChartTest');
        if (el) el.innerHTML = svg;
        return;
    }
    let minT = Math.min(...allTimes), maxT = Math.max(...allTimes);
    let minV = Math.min(...allVoltages), maxV = Math.max(...allVoltages);
    let padV = (maxV - minV) * 0.1 || 1;
    minV -= padV; maxV += padV;
    for (let i = 0; i <= gridCountY; i++) {
        let y = padding + ((height - 2 * padding) * i) / gridCountY;
        let v = (maxV - minV) * (1 - i / gridCountY) + minV;
        svg += `<line x1="${padding}" y1="${y}" x2="${width - padding}" y2="${y}" stroke="#222"/>`;
        svg += `<text x="${padding - 8}" y="${y + 4}" fill="#888" font-size="14" text-anchor="end">${v.toFixed(2)}</text>`;
    }
    for (let i = 0; i <= gridCountX; i++) {
        let x = padding + ((width - 2 * padding) * i) / gridCountX;
        let t = (maxT - minT) * (i / gridCountX) + minT;
        svg += `<line x1="${x}" y1="${padding}" x2="${x}" y2="${height - padding}" stroke="#222"/>`;
        svg += `<text x="${x}" y="${height - padding + 22}" fill="#888" font-size="14" text-anchor="middle">${t.toFixed(2)}</text>`;
    }
    Object.entries(channelsData).forEach(([ch, chData], idx) => {
        if (!chData.voltage || !chData.time || chData.voltage.length === 0) return;
        const color = chData.color || ['yellow', 'cyan', 'magenta', '#00aaff'][idx];
        let points = chData.time.map((t, i) => {
            let x = padding + ((t - minT) / ((maxT - minT) || 1)) * (width - 2 * padding);
            let y = padding + (height - 2 * padding) * (1 - (chData.voltage[i] - minV) / ((maxV - minV) || 1));
            return `${x},${y}`;
        }).join(' ');
        svg += `<polyline fill="none" stroke="${color}" stroke-width="2" points="${points}"/>`;
    });
    let legendX = width - padding - 120, legendY = padding;
    Object.entries(channelsData).forEach(([ch, chData], idx) => {
        const color = chData.color || ['yellow', 'cyan', 'magenta', '#00aaff'][idx];
        svg += `<rect x="${legendX}" y="${legendY + idx * 26}" width="22" height="10" fill="${color}" />`;
        svg += `<text x="${legendX + 30}" y="${legendY + idx * 26 + 10}" fill="#fff" font-size="16">${ch}</text>`;
    });
    svg += `</svg>`;
    const el = document.getElementById('oscilloscopeChartTest');
    if (el) el.innerHTML = svg;
}

function renderChannelInfoSVGTest(channelsData, triggerData) {
    const svgElem = document.getElementById('channelInfoSVGTest');
    if (!svgElem) return;
    const cardW = 260, cardH = 120, gap = 18;
    const nChannels = Object.keys(channelsData).length;
    const totalCards = nChannels + 1;
    const svgW = Math.max(totalCards * (cardW + gap) + gap, 900);
    const svgH = cardH + 20;
    svgElem.setAttribute('viewBox', `0 0 ${svgW} ${svgH}`);
    svgElem.setAttribute('width', '100%');
    svgElem.setAttribute('height', svgH);
    let svg = '';
    const trigX = gap, trigY = 10;
    svg += `
      <g>
        <rect x="${trigX}" y="${trigY}" width="${cardW}" height="${cardH}" rx="12" fill="#222" stroke="#ff9800" stroke-width="2.5"/>
        <text x="${trigX+18}" y="${trigY+32}" fill="#ff9800" font-size="22" font-family="monospace" font-weight="bold">Триггер</text>
        <text x="${trigX+cardW-18}" y="${trigY+32}" fill="#2ecc71" font-size="16" font-family="monospace" text-anchor="end">${triggerData.mode||'Auto'}</text>
        <text x="${trigX+18}" y="${trigY+60}" fill="#fff" font-size="16" font-family="monospace"><tspan fill="#00ccff">Уровень:</tspan> <tspan fill="#ff0">${triggerData.level!==undefined?triggerData.level:'--'} В</tspan></text>
        <text x="${trigX+18}" y="${trigY+84}" fill="#fff" font-size="16" font-family="monospace"><tspan fill="#00ccff">Источник:</tspan> <tspan fill="#0ff">${triggerData.source||'CH1'}</tspan></text>
        <text x="${trigX+18}" y="${trigY+108}" fill="#fff" font-size="16" font-family="monospace"><tspan fill="#00ccff">Slope:</tspan> <tspan fill="#0f0">${triggerData.slope||'Rising'}</tspan></text>
      </g>
    `;
    let idx = 0;
    Object.entries(channelsData).forEach(([ch, chData]) => {
        const x = gap + (cardW + gap) * (idx + 1);
        const y = trigY;
        const color = chData.color || ['yellow', 'cyan', 'magenta', '#00aaff'][idx];
        const settings = chData.settings || {};
        const isActive = settings.display === '1' || settings.display === 1 || settings.display === true;
        svg += `
          <g>
            <rect x="${x}" y="${y}" width="${cardW}" height="${cardH}" rx="12" fill="#222" stroke="${color}" stroke-width="2.5" opacity="${isActive?'1':'0.5'}"/>
            <text x="${x+18}" y="${y+32}" fill="${color}" font-size="22" font-family="monospace" font-weight="bold">${ch}</text>
            <text x="${x+cardW-18}" y="${y+32}" fill="${isActive?'#2ecc71':'#e74c3c'}" font-size="16" font-family="monospace" text-anchor="end">${isActive?'Активен':'Отключен'}</text>
            <text x="${x+18}" y="${y+60}" fill="#00ccff" font-size="16" font-family="monospace">Volts/Div: <tspan fill="#fff">${settings.volts_div??'--'} В</tspan></text>
            <text x="${x+18}" y="${y+80}" fill="#00ccff" font-size="16" font-family="monospace">Offset: <tspan fill="#fff">${settings.offset??'--'} В</tspan></text>
            <text x="${x+18}" y="${y+100}" fill="#00ccff" font-size="16" font-family="monospace">Coupling: <tspan fill="#fff">${settings.coupling??'--'}</tspan></text>
            <text x="${x+18}" y="${y+120}" fill="#00ccff" font-size="16" font-family="monospace">Display: <tspan fill="#fff">${isActive?'On':'Off'}</tspan></text>
          </g>
        `;
        idx++;
    });
    svgElem.innerHTML = svg;
}


function updateTriggerInfo(trigger) {
    let infoBlock = document.getElementById('oscilloscopeTriggerInfo');
    if (!infoBlock) {
        const parent = document.getElementById('oscilloscopeChannelControls');
        infoBlock = document.createElement('div');
        infoBlock.id = 'oscilloscopeTriggerInfo';
        infoBlock.className = 'mt-2 mb-2 p-2 bg-dark rounded border border-warning';
        if (parent) parent.parentElement.insertBefore(infoBlock, parent.nextSibling);
    }
    if (!trigger) {
        infoBlock.innerHTML = '<span class="text-warning">Нет данных о триггере</span>';
        return;
    }
    infoBlock.innerHTML = `
        <span style="color:#ff9800;font-weight:bold;">Триггер:</span>
        <span class="ms-3"><b>Уровень:</b>
            <input type="number" id="triggerLevelInput" style="width:80px" step="0.01" value="${trigger.level !== undefined ? trigger.level : ''}"> В
        </span>
        <span class="ms-3"><b>Режим:</b> <span style="color:#0ff;">${trigger.mode || '--'}</span></span>
        <span class="ms-3"><b>Источник:</b> <span style="color:#0ff;">${trigger.source || '--'}</span></span>
        <span class="ms-3"><b>Фронт:</b> <span style="color:#0f0;">${trigger.slope || '--'}</span></span>
    `;
    const input = document.getElementById('triggerLevelInput');
    if (input) {
        input.onchange = function() {
            const newLevel = parseFloat(input.value);
            if (!isNaN(newLevel) && websocket && websocket.readyState === WebSocket.OPEN) {
                websocket.send(JSON.stringify({
                    action: 'set_trigger',
                    trigger: { ...trigger, level: newLevel }
                }));
            }
        };
    }
}
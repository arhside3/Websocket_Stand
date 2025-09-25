const MAX_MULTIMETER_POINTS = 100;
let multimeterChart;
let multimeterHistoryChart;
let multimeterData = {
    timestamps: [],
    values: []
};

let lastMultimeterValue = {
    value: '--.--',
    unit: 'V',
    mode: 'DC',
    range_str: 'AUTO',
    measure_type: 'Вольтметр'
};

let lastMultimeterNumericValue = null;
let currentMultimeterMode = 'DC';
let multimeterTestData = { timestamps: [], values: [] };
let avgMultimeterChartData = { timestamps: [], values: [] };
let avgMultimeterChartElem = null;

function updateMultimeterData(data) {
    if (!measurementsActive) return;
    try {
        document.getElementById('multimeterValue').innerHTML = 
            data.value + ' <span id="multimeterUnit">' + data.unit + '</span>';
        document.getElementById('multimeterMode').textContent = data.mode || '';
        document.getElementById('multimeterRange').textContent = data.range_str || 'AUTO';
        document.getElementById('multimeterType').textContent = data.measure_type || '';
        
        let value = parseFloat(data.value);
        if (isNaN(value) || data.value === 'OL') {
            return;
        }
        
        const timestamp = data.timestamp ? new Date(data.timestamp) : new Date();
        multimeterData.timestamps.push(timestamp);
        multimeterData.values.push(value);
        
        while (multimeterData.timestamps.length > MAX_MULTIMETER_POINTS) {
            multimeterData.timestamps.shift();
            multimeterData.values.shift();
        }
        
        currentMultimeterMode = data.mode || 'DC';
        
        renderMultimeterSVG(multimeterData);
        if (multimeterChart && multimeterChart.data && multimeterChart.data.datasets && multimeterChart.data.datasets[0]) {
            let chartLabel = '';
            let unit = data.unit || 'V';
            
            switch(data.measure_type) {
                case 'Voltage':
                    chartLabel = `Напряжение, ${unit} (${currentMultimeterMode})`;
                    break;
                case 'Current':
                    chartLabel = `Ток, ${unit} (${currentMultimeterMode})`;
                    break;
                case 'Resistance':
                    chartLabel = `Сопротивление, ${unit}`;
                    break;
                case 'Temperature':
                    chartLabel = `Температура, ${unit}`;
                    break;
                case 'Frequency':
                    chartLabel = `Частота, ${unit}`;
                    break;
                case 'Capacitance':
                    chartLabel = `Емкость, ${unit}`;
                    break;
                case 'Diode Test':
                    chartLabel = `Тест диода, ${unit}`;
                    break;
                case 'Continuity':
                    chartLabel = `Прозвонка, ${unit}`;
                    break;
                case 'hFE':
                    chartLabel = `Коэффициент усиления транзистора`;
                    break;
                default:
                    chartLabel = `${data.measure_type}, ${unit} (${currentMultimeterMode})`;
            }
            
            multimeterChart.data.datasets[0].label = chartLabel;
            multimeterChart.update();
        }
        
        updateMultimeterColorIndicator(data);
        
    } catch (error) {
        console.error('Ошибка обновления данных мультиметра:', error);
    }
}

function updateMultimeterColorIndicator(data) {
    const valueElement = document.getElementById('multimeterValue');
    if (!valueElement) return;
    
    valueElement.classList.remove('voltage-normal', 'voltage-warning', 'voltage-danger',
                                'current-normal', 'current-warning', 'current-danger',
                                'resistance-normal', 'resistance-warning',
                                'temperature-normal', 'temperature-warning', 'temperature-danger',
                                'frequency-normal', 'frequency-warning',
                                'capacitance-normal', 'capacitance-warning');
    
    if (data.value === 'OL') {
        valueElement.classList.add('overload');
        return;
    }
    
    const value = parseFloat(data.value);
    if (isNaN(value)) return;
    
    switch(data.measure_type) {
        case 'Voltage':
            if (Math.abs(value) <= 12) {
                valueElement.classList.add('voltage-normal');
            } else if (Math.abs(value) <= 24) {
                valueElement.classList.add('voltage-warning');
            } else {
                valueElement.classList.add('voltage-danger');
            }
            break;
            
        case 'Current':
            if (Math.abs(value) <= 1) {
                valueElement.classList.add('current-normal');
            } else if (Math.abs(value) <= 5) {
                valueElement.classList.add('current-warning');
            } else {
                valueElement.classList.add('current-danger');
            }
            break;
            
        case 'Resistance':
            if (value > 0 && value < 1000000) {
                valueElement.classList.add('resistance-normal');
            } else {
                valueElement.classList.add('resistance-warning');
            }
            break;
            
        case 'Temperature':
            if (value >= -40 && value <= 80) {
                valueElement.classList.add('temperature-normal');
            } else if (value >= -60 && value <= 120) {
                valueElement.classList.add('temperature-warning');
            } else {
                valueElement.classList.add('temperature-danger');
            }
            break;
            
        case 'Frequency':
            if (value > 0 && value <= 1000000) {
                valueElement.classList.add('frequency-normal');
            } else {
                valueElement.classList.add('frequency-warning');
            }
            break;
            
        case 'Capacitance':
            if (value > 0 && value <= 1000000) {
                valueElement.classList.add('capacitance-normal');
            } else {
                valueElement.classList.add('capacitance-warning');
            }
            break;
    }
}

function initMultimeterChart(ctx) {
    const chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: `Напряжение, V (${currentMultimeterMode})`,
                data: [],
                borderColor: '#00ffcc',
                backgroundColor: 'rgba(0, 255, 204, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.3,
                pointRadius: 2,
                pointBackgroundColor: '#00ffcc'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: {
                duration: 300
            },
            interaction: {
                intersect: false,
                mode: 'index'
            },
            scales: {
                y: {
                    beginAtZero: false,
                    grid: {
                        display: true,
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: '#aaa',
                        maxTicksLimit: 8,
                        callback: function(value) {
                            return value.toFixed(3) + ' V';
                        }
                    }
                },
                x: {
                    grid: {
                        display: true,
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: '#aaa',
                        maxTicksLimit: 8,
                        maxRotation: 0,
                        callback: function(value, index, values) {
                            const date = new Date(this.getLabelForValue(value));
                            return date.toTimeString().substr(0, 8);
                        }
                    }
                }
            },
            plugins: {
                legend: { display: true },
                tooltip: {
                    enabled: true,
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleColor: '#fff',
                    bodyColor: '#00ffcc',
                    callbacks: {
                        label: function(context) {
                            return `Значение: ${context.parsed.y.toFixed(3)} V`;
                        }
                    }
                }
            }
        }
    });
    
    return chart;
}

function renderMultimeterSVG(data) {
    const width = 1500, height = 400, padding = 50, gridCountY = 4, gridCountX = 6;
    let svg = `<svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}" style="background:#111;display:block;">`;
    if (!data.timestamps || !data.values || data.values.length === 0) {
        svg += '</svg>';
        const el = document.getElementById('multimeterSVG');
        if (el) el.innerHTML = svg;
        return;
    }
    const minT = Math.min(...data.timestamps.map(t => new Date(t).getTime()));
    const maxT = Math.max(...data.timestamps.map(t => new Date(t).getTime()));
    const minV = Math.min(...data.values);
    const maxV = Math.max(...data.values);
    let padV = (maxV - minV) * 0.1 || 1;
    let minV2 = minV - padV, maxV2 = maxV + padV;
    for (let i = 0; i <= gridCountY; i++) {
        let y = padding + ((height - 2 * padding) * i) / gridCountY;
        let v = (maxV2 - minV2) * (1 - i / gridCountY) + minV2;
        svg += `<line x1="${padding}" y1="${y}" x2="${width - padding}" y2="${y}" stroke="#222"/>`;
        svg += `<text x="${padding - 8}" y="${y + 4}" fill="#888" font-size="13" text-anchor="end">${v.toFixed(2)}</text>`;
    }
    for (let i = 0; i <= gridCountX; i++) {
        let x = padding + ((width - 2 * padding) * i) / gridCountX;
        let t = (maxT - minT) * (i / gridCountX) + minT;
        let date = new Date(t);
        let label = date.toLocaleTimeString().slice(0,8);
        svg += `<line x1="${x}" y1="${padding}" x2="${x}" y2="${height - padding}" stroke="#222"/>`;
        svg += `<text x="${x}" y="${height - padding + 20}" fill="#888" font-size="13" text-anchor="middle">${label}</text>`;
    }
    let points = data.timestamps.map((t, i) => {
        let x = padding + ((new Date(t).getTime() - minT) / ((maxT - minT) || 1)) * (width-2*padding);
        let y = padding + (height - 2 * padding) * (1 - (data.values[i] - minV2) / ((maxV2 - minV2) || 1));
        return `${x},${y}`;
    }).join(' ');
    svg += `<polyline fill="none" stroke="#00ffcc" stroke-width="2" points="${points}"/>`;
    svg += `</svg>`;
    const el = document.getElementById('multimeterSVG');
    if (el) el.innerHTML = svg;
}

function updateMultimeterTestData(data) {
    const timestamp = data.timestamp ? new Date(data.timestamp) : new Date();
    const value = parseFloat(data.value);
    if (!isNaN(value)) {
        multimeterTestData.timestamps.push(timestamp);
        multimeterTestData.values.push(value);
    }
    const valueElem = document.getElementById('multimeterValueTest');
    const unitElem = document.getElementById('multimeterUnitTest');
    const bigElem = document.getElementById('multimeterValueTestBig');
    const modeElem = document.getElementById('multimeterModeTest');
    const rangeElem = document.getElementById('multimeterRangeTest');
    const typeElem = document.getElementById('multimeterTypeTest');
    renderMultimeterSVGTest(multimeterTestData);
    if (valueElem && unitElem) {
        valueElem.innerText = data.value + ' ';
        unitElem.innerText = data.unit;
    }
    if (bigElem) {
        bigElem.innerHTML = `<span style="font-size:2.5em;color:#00ffc0;">${data.value}</span> <span style="font-size:1.2em;color:#00ffc0;">${data.unit}</span>`;
    }
    if (modeElem && data.mode) modeElem.innerText = data.mode;
    if (rangeElem && data.range_str) rangeElem.innerText = data.range_str;
    if (typeElem && data.measure_type) typeElem.innerText = data.measure_type;
}

function renderMultimeterSVGTest(data) {
    const width = 1500, height = 400, padding = 50, gridCountY = 4, gridCountX = 6;
    let svg = `<svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}" style="background:#111;display:block;">`;
    if (!data.timestamps || !data.values || data.values.length === 0) {
        svg += '</svg>';
        const el = document.getElementById('multimeterChartTest');
        if (el) el.innerHTML = svg;
        return;
    }
    const minT = Math.min(...data.timestamps.map(t => new Date(t).getTime()));
    const maxT = Math.max(...data.timestamps.map(t => new Date(t).getTime()));
    const minV = Math.min(...data.values);
    const maxV = Math.max(...data.values);
    let padV = (maxV - minV) * 0.1 || 1;
    let minV2 = minV - padV, maxV2 = maxV + padV;
    for (let i = 0; i <= gridCountY; i++) {
        let y = padding + ((height - 2 * padding) * i) / gridCountY;
        let v = (maxV2 - minV2) * (1 - i / gridCountY) + minV2;
        svg += `<line x1="${padding}" y1="${y}" x2="${width - padding}" y2="${y}" stroke="#222"/>`;
        svg += `<text x="${padding - 8}" y="${y + 4}" fill="#888" font-size="13" text-anchor="end">${v.toFixed(2)}</text>`;
    }
    for (let i = 0; i <= gridCountX; i++) {
        let x = padding + ((width - 2 * padding) * i) / gridCountX;
        let t = (maxT - minT) * (i / gridCountX) + minT;
        let date = new Date(t);
        let label = date.toLocaleTimeString().slice(0,8);
        svg += `<line x1="${x}" y1="${padding}" x2="${x}" y2="${height - padding}" stroke="#222"/>`;
        svg += `<text x="${x}" y="${height - padding + 20}" fill="#888" font-size="13" text-anchor="middle">${label}</text>`;
    }
    let points = data.timestamps.map((t, i) => {
        let x = padding + ((new Date(t).getTime() - minT) / ((maxT - minT) || 1)) * (width-2*padding);
        let y = padding + (height - 2 * padding) * (1 - (data.values[i] - minV2) / ((maxV2 - minV2) || 1));
        return `${x},${y}`;
    }).join(' ');
    svg += `<polyline fill="none" stroke="#00ffcc" stroke-width="2" points="${points}"/>`;
    svg += `</svg>`;
    const el = document.getElementById('multimeterChartTest');
    if (el) el.innerHTML = svg;
}

async function loadMultimeterHistory() {
    try {
        const period = document.getElementById('multimeterHistoryPeriod')?.value || 'hour';
        const response = await fetch(`/history/multimeter?period=${period}`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (multimeterHistoryChart && data.timestamps && data.timestamps.length > 0) {
            multimeterHistoryChart.data.labels = data.timestamps;
            multimeterHistoryChart.data.datasets[0].data = data.values || [];
            multimeterHistoryChart.update();
        } else {
            console.warn('Нет данных для истории мультиметра');
        }
    } catch (error) {
        console.error('Ошибка при загрузке истории мультиметра:', error);
    }
}
function generateTestMultimeterHistory() {
    if (!multimeterHistoryChart) {
        console.warn('График истории мультиметра не инициализирован');
        return;
    }
    
    const now = new Date();
    const timestamps = [];
    const values = [];
    
    for (let i = 10; i >= 0; i--) {
        const time = new Date(now.getTime() - i * 60000);
        timestamps.push(time.toLocaleTimeString());
        values.push(Math.random() * 10 + 1);
    }
    
    multimeterHistoryChart.data.labels = timestamps;
    multimeterHistoryChart.data.datasets[0].data = values;
    multimeterHistoryChart.update();
}

async function loadAvgMultimeterChart(testNumber) {
    const valueElem = document.getElementById('avgMultimeterValue');
    if (!testNumber) {
        if (valueElem) valueElem.textContent = '--';
        return;
    }
    try {
        const resp = await fetch(`/tests/${testNumber}?type=multimeter&limit=1000`);
        if (!resp.ok) throw new Error('Ошибка загрузки данных');
        const result = await resp.json();
        let records = [];
        if (Array.isArray(result)) {
            records = result;
        } else if (result.data && Array.isArray(result.data)) {
            records = result.data;
        } else if (result.multimeter && Array.isArray(result.multimeter)) {
            records = result.multimeter;
        }
        if (!records.length) {
            if (valueElem) valueElem.textContent = '--';
            return;
        }

        const groupedData = {};
        records.forEach(record => {
            const unit = record.unit || 'V';
            if (!groupedData[unit]) {
                groupedData[unit] = {
                    values: [],
                    sum: 0,
                    count: 0
                };
            }
            const value = parseFloat(record.value);
            if (!isNaN(value)) {
                groupedData[unit].values.push(value);
                groupedData[unit].sum += value;
                groupedData[unit].count++;
            }
        });

        const avgText = [];
        Object.entries(groupedData).forEach(([unit, data]) => {
            if (data.count > 0) {
                const avg = data.sum / data.count;
                avgText.push(`${avg.toFixed(3)} ${unit}`);
            }
        });

        if (avgText.length > 0) {
            if (valueElem) valueElem.textContent = avgText.join(', ');
        } else {
            if (valueElem) valueElem.textContent = '--';
        }
    } catch (e) {
        console.error('Ошибка при загрузке данных мультиметра:', e);
        if (valueElem) valueElem.textContent = 'Ошибка';
    }
}

function renderTestMultimeterData(data) {
    const container = document.getElementById('testMultimeterData');
    if (!container) return;

    if (!data || data.length === 0) {
        container.innerHTML = '<p class="text-muted">Нет данных мультиметра</p>';
        return;
    }

    let html = '<h6>Данные мультиметра:</h6>';
    html += '<div class="table-responsive"><table class="table table-sm">';
    html += '<thead><tr><th>Время</th><th>Значение</th><th>Единица</th><th>Режим</th></tr></thead><tbody>';
    
    data.slice(0, 20).forEach(record => {
        html += `
            <tr>
                <td>${record.timestamp}</td>
                <td>${record.value}</td>
                <td>${record.unit}</td>
                <td>${record.mode}</td>
            </tr>
        `;
    });
    
    html += '</tbody></table></div>';
    html += `<small class="text-muted">Всего записей: ${data.length}</small>`;
    
    container.innerHTML = html;
}
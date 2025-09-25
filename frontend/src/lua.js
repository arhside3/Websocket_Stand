let luaTestActive = false;
let currentTestNumber = null;
let testsList = [];
let selectedTestNumber = null;
let testUpdateInterval = null;

function addToLuaConsoleTest(line) {
    const luaConsoleTest = document.getElementById('luaConsoleTest');
    if (luaConsoleTest) {
        luaConsoleTest.innerHTML += line + '<br>';
        luaConsoleTest.scrollTop = luaConsoleTest.scrollHeight;
    }
}

function updateTestProgress(percent) {
    const progressBar = document.getElementById('testProgressBar');
    if (!progressBar) return;
    progressBar.style.width = percent + '%';
    progressBar.textContent = percent + '%';
    progressBar.setAttribute('aria-valuenow', percent);
}

function addClearTestChartButton() {
    const chartElem = document.getElementById('multimeterChartTest');
    if (!chartElem) return;
    if (document.getElementById('clearTestChartBtn')) return;
    
    const btn = document.createElement('button');
    btn.id = 'clearTestChartBtn';
    btn.textContent = 'Очистить графики';
    btn.style.position = 'absolute';
    btn.style.top = '10px';
    btn.style.right = '10px';
    btn.style.zIndex = 10;
    btn.className = 'btn btn-sm btn-danger';
    btn.onclick = function() {
        multimeterTestData = { timestamps: [], values: [] };
        if (window.multimeterChartTest) {
            window.multimeterChartTest.data.labels = [];
            window.multimeterChartTest.data.datasets[0].data = [];
            window.multimeterChartTest.update();
        }
        
        oscilloscopeTestData = {
            timestamps: [],
            channels: {
                CH1: { values: [], active: true },
                CH2: { values: [], active: true },
                CH3: { values: [], active: true },
                CH4: { values: [], active: true }
            }
        };
        if (window.oscilloscopeChartTest) {
            window.oscilloscopeChartTest.data.datasets = [];
            window.oscilloscopeChartTest.update();
        }
        
        if (testUpdateInterval) {
            clearInterval(testUpdateInterval);
            testUpdateInterval = null;
        }
        
        const progressBar = document.getElementById('testProgressBar');
        if (progressBar) {
            progressBar.style.width = '0%';
            progressBar.textContent = '0%';
            progressBar.setAttribute('aria-valuenow', 0);
        }
    };
    
    if (chartElem.parentElement) {
        chartElem.parentElement.style.position = 'relative';
        chartElem.parentElement.appendChild(btn);
    }
}

function parseAndAddOscilloscopeTestData(line) {
    try {
        const obj = JSON.parse(line);
        if (obj.type === 'oscilloscope_test' && obj.channel && obj.time && obj.voltage) {
            let settings = obj.settings || {};
            if (typeof settings.display === 'undefined') settings.display = '0';
            oscilloscopeTestLiveData[obj.channel] = {
                time: obj.time,
                voltage: obj.voltage,
                color: obj.color || CHANNEL_COLORS[parseInt(obj.channel.slice(2)) - 1],
                settings: settings
            };
            updateOscilloscopeChartTestLive();
            return;
        }
        if (obj.type === 'trigger' && (obj.level !== undefined)) {
            window.oscilloscopeTestTrigger = {
                level: obj.level,
                mode: obj.mode || 'Auto',
                source: obj.source || 'CH1',
                slope: obj.slope || 'Rising'
            };
            updateOscilloscopeChartTestLive();
            return;
        }
    } catch (e) {
        const regex = /Сохранены данные канала (CH\d), среднее напряжение: ([\d.]+)В/;
        const match = line.match(regex);
        if (match) {
            const channel = match[1];
            const value = parseFloat(match[2]);
            if (!isNaN(value)) {
                if (!oscilloscopeTestLiveData[channel] || !Array.isArray(oscilloscopeTestLiveData[channel].time) || !Array.isArray(oscilloscopeTestLiveData[channel].voltage)) {
                    oscilloscopeTestLiveData[channel] = { time: [], voltage: [], settings: { display: '1' } };
                }
                const idx = oscilloscopeTestLiveData[channel].time.length;
                oscilloscopeTestLiveData[channel].time.push(idx);
                oscilloscopeTestLiveData[channel].voltage.push(value);
                updateOscilloscopeChartTestLive();
            }
        }
    }
}

function runLuaScript() {
    luaTestActive = true;
    multimeterTestData = { timestamps: [], values: [] };
    oscilloscopeTestData = {
        timestamps: [],
        channels: {
            CH1: { values: [], active: true },
            CH2: { values: [], active: true },
            CH3: { values: [], active: true },
            CH4: { values: [], active: true }
        }
    };
    oscilloscopeTestLiveData = { CH1: [], CH2: [], CH3: [], CH4: [], index: 0 };
    updateOscilloscopeChartTestLive();

    if (oscilloscopeChart) {
        oscilloscopeChart.data.datasets = [];
        oscilloscopeChart.update();
    }

    const luaConsoleTest = document.getElementById('luaConsoleTest');
    if (typeof oscilloscopeChart !== 'undefined' && oscilloscopeChart) {
        oscilloscopeChart.data.datasets = [];
        oscilloscopeChart.update();
    }
    if (luaConsoleTest) luaConsoleTest.innerHTML = '';

    if (testUpdateInterval) {
        clearInterval(testUpdateInterval);
        testUpdateInterval = null;
    }

    if (websocket && websocket.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify({
            action: 'run_lua',
            script: 'contrib/main.lua'
        }));
        updateTestProgress(100);
    } else {
        alert('Ошибка: WebSocket не подключен');
        luaTestActive = false;
    }
}

async function loadTestsList() {
    try {
        const response = await fetch('/tests');
        if (response.ok) {
            testsList = await response.json();
            renderTestsList();
        } else {
            console.error('Ошибка загрузки списка испытаний:', response.status);
        }
    } catch (error) {
        console.error('Ошибка загрузки списка испытаний:', error);
    }
}

function renderTestsList() {
    const testsContainer = document.getElementById('testsList');
    if (!testsContainer) return;

    if (testsList.length === 0) {
        testsContainer.innerHTML = '<p class="text-muted">Нет сохраненных испытаний</p>';
        return;
    }

    let html = '<div class="list-group">';
    testsList.forEach(test => {
        const isSelected = selectedTestNumber === test.number;
        const selectedClass = isSelected ? 'active' : '';
        html += `
            <div class="list-group-item list-group-item-action ${selectedClass}" 
                 onclick="selectTest(${test.number})" style="cursor: pointer;">
                <div class="d-flex w-100 justify-content-between">
                    <h6 class="mb-1">Испытание #${test.number}</h6>
                    <small>${test.record_count} записей</small>
                </div>
                <p classmb-1">Начало: ${test.start_time}</p>
                <small>Окончание: ${test.end_time}</small>
            </div>
        `;
    });
    html += '</div>';
    testsContainer.innerHTML = html;
}

async function selectTest(testNumber) {
    selectedTestNumber = testNumber;
    renderTestsList();
    await loadTestData(testNumber);
    loadAvgMultimeterChart(testNumber);
}

async function loadTestData(testNumber) {
    try {
        const oscResponse = await fetch(`/tests/${testNumber}?type=oscilloscope&limit=100`);
        if (oscResponse.ok) {
            const oscData = await oscResponse.json();
            if (!oscData.error) {
                renderTestOscilloscopeData(oscData.data);
            }
        }

        const multResponse = await fetch(`/tests/${testNumber}?type=multimeter&limit=100`);
        if (multResponse.ok) {
            const multData = await multResponse.json();
            if (!multData.error) {
                renderTestMultimeterData(multData.data);
            }
        }
    } catch (error) {
        console.error('Ошибка загрузки данных испытания:', error);
    }
}

function renderTestOscilloscopeData(data) {
    const container = document.getElementById('testOscilloscopeData');
    if (!container) return;

    if (!data || data.length === 0) {
        container.innerHTML = '<p class="text-muted">Нет данных осциллографа</p>';
        return;
    }

    const channelsData = {};
    data.forEach(record => {
        if (record.channel && record.time_data && record.voltage_data) {
            if (!channelsData[record.channel]) {
                channelsData[record.channel] = [];
            }
            try {
                const timeArray = decodeBase64ToFloat32Array(record.time_data);
                const voltageArray = decodeBase64ToFloat32Array(record.voltage_data);
                channelsData[record.channel].push({
                    timestamp: record.timestamp,
                    time: timeArray,
                    voltage: voltageArray
                });
            } catch (e) {
                console.error('Ошибка декодирования данных:', e);
            }
        }
    });

    let html = '<h6>Данные осциллографа:</h6>';
    Object.keys(channelsData).forEach(channel => {
        const channelData = channelsData[channel];
        if (channelData.length > 0) {
            const latest = channelData[channelData.length - 1];
            html += `
                <div class="mb-3">
                    <h6>${channel}</h6>
                    <div class="oscilloscope-svg-container">
                        ${renderOscilloscopeSVGTest({ [channel]: { time: latest.time, voltage: latest.voltage } })}
                    </div>
                    <small class="text-muted">Записей: ${channelData.length}</small>
                </div>
            `;
        }
    });

    container.innerHTML = html;
}
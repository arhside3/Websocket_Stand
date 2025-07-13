const WEBSOCKET_URL = 'ws://127.0.0.1:8767'; //const WEBSOCKET_URL = 'ws://10.34.10.76:8767/'; для сервера если нужно
const MAX_MULTIMETER_POINTS = 100;
const CHANNEL_COLORS = ['yellow', 'cyan', 'magenta', '#00aaff'];
const UPDATE_INTERVAL = 1000; 

let websocket;
let oscilloscopeChart;
let multimeterChart;
let oscilloHistoryChart;
let multimeterHistoryChart;
let multimeterData = {
    timestamps: [],
    values: []
};

let lastMultimeterValue = {
    value: '--.--',
    unit: 'В',
    mode: 'DC',
    range_str: 'AUTO',
    measure_type: 'Вольтметр'
};

let lastMultimeterNumericValue = null;

let lastChannelValues = {
    CH1: { value: null, time: null },
    CH2: { value: null, time: null },
    CH3: { value: null, time: null },
    CH4: { value: null, time: null }
};

let measurementsActive = true;

let currentPage = 1;
let totalPages = 1;
let currentPerPage = 10;

let dbCurrentPage = 1;
const dbPerPage = 50;
let dbTotalPages = 1;
let dbCurrentType = 'oscilloscope';

let luaTestActive = false;
let multimeterTestData = { timestamps: [], values: [] };

let oscilloscopeTestData = {
    timestamps: [],
    channels: {
        CH1: { values: [], active: true },
        CH2: { values: [], active: true },
        CH3: { values: [], active: true },
        CH4: { values: [], active: true }
    }
};

let testUpdateInterval = null;

let oscilloscopeTestLiveData = {
    CH1: [],
    CH2: [],
    CH3: [],
    CH4: [],
    index: 0
};

let currentMultimeterMode = 'DC';

let currentTestNumber = null;
let testsList = [];
let selectedTestNumber = null;

let dbSelectedTest = '';

async function updateDbTestSelect() {
    const select = document.getElementById('dbTestSelect');
    if (!select) return;
    let resp = await fetch('/tests');
    let tests = [];
    if (resp.ok) tests = await resp.json();
    let html = '<option value="">Рабочие таблицы</option>';
    tests.forEach(test => {
        html += `<option value="${test.number}">Испытание #${test.number}</option>`;
    });
    select.innerHTML = html;
    select.value = dbSelectedTest;
}

function requestOscilloscopeData() {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify({
            action: 'get_oscilloscope_data'
        }));
    }
}

function startPeriodicUpdates() {
    requestOscilloscopeData();
    requestMultimeterData();
    
    setInterval(() => {
        requestOscilloscopeData();
        requestMultimeterData();
    }, UPDATE_INTERVAL);
}

function requestMultimeterData() {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify({
            action: 'get_multimeter_data'
        }));
    }
}

function initWebSocket() {
    websocket = new WebSocket(WEBSOCKET_URL);
    
    websocket.onopen = function() {
        document.getElementById('statusIndicator').classList.add('connected');
        document.getElementById('statusIndicator').classList.remove('disconnected');
        document.getElementById('statusIndicator').title = 'Подключено';

        console.log('Запрашиваем данные мультиметра после подключения...');
        websocket.send(JSON.stringify({
            action: 'get_multimeter_data'
        }));
        
        setTimeout(() => {
            console.log('Запрашиваем данные осциллографа...');
            websocket.send(JSON.stringify({
                action: 'get_oscilloscope_data'
            }));
        }, 500);

        startPeriodicUpdates();
    };
    
    websocket.onclose = function() {
        document.getElementById('statusIndicator').classList.remove('connected');
        document.getElementById('statusIndicator').classList.add('disconnected');
        document.getElementById('statusIndicator').title = 'Соединение разорвано';
        
        setTimeout(initWebSocket, 5000);
    };
    
    websocket.onerror = function(error) {
        console.error('WebSocket error:', error);
    };
    
    websocket.onmessage = function(event) {
        console.log('WS message:', event.data);
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'oscilloscope') {
                parseAndAddOscilloscopeTestData(data.line);
            } else if (data.type === 'multimeter') {
                if (data.line) {
                    const regex = /\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\] ([\d.]+) В (DC|AC) AUTO \[Вольтметр\]/;
                    const match = data.line.match(regex);
                    if (match) {
                        const timestamp = match[1];
                        const value = match[2];
                        const mode = match[3];
                        updateMultimeterTestData({
                            value: value,
                            unit: 'В',
                            mode: mode,
                            range_str: 'AUTO',
                            measure_type: 'Вольтметр',
                            timestamp: timestamp
                        });
                    } else if (data.line.startsWith('[PROGRESS]')) {
                        const percent = parseInt(data.line.match(/\[PROGRESS\]\s*(\d+)%/)[1]);
                        updateTestProgress(percent);
                    } else {
                        addToLuaConsoleTest(data.line);
                    }
                } else if (data.data) {
                    updateMultimeterData(data.data);
                    updateMultimeterTestData(data.data);
                }
            } else if (data.channels || (data.time_base && data.channels)) {
                updateOscilloscopeData(data);
                if (luaTestActive) {
                    parseAndAddOscilloscopeTestData(data.line);
                }
            } else if (data.type === 'multimeter' && data.data) {
                updateMultimeterData(data.data);
                updateMultimeterTestData(data.data);
            } else if (data.time && data.voltage) {
                updateOscilloscopeData(data);
            } else if (data.type === 'lua_output') {
                if (data.line && data.line.startsWith('[PROGRESS]')) {
                    const percent = parseInt(data.line.match(/\[PROGRESS\]\s*(\d+)%/)[1]);
                    updateTestProgress(percent);
                } else {
                    addToLuaConsoleTest(data.line);
                    parseAndAddOscilloscopeTestData(data.line);
                }
            } else if (data.type === 'lua_status') {
                setTimeout(() => { luaTestActive = false; }, 1000);
                addToLuaConsoleTest(data.success ? '<span style="color:lime">Сценарий завершён успешно</span>' : '<span style="color:red">Ошибка выполнения сценария</span>');
                updateTestProgress(100);
            } else if (data.type === 'test_started') {
                currentTestNumber = data.test_number;
                addToLuaConsoleTest(`<span style="color:cyan">Начато испытание #${data.test_number}</span>`);
                loadTestsList();
            } else if (data.output) {
                const multimeterRegex = /\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\] ([\d.]+) В (DC|AC) AUTO \[Вольтметр\]/;
                const match = data.output.match(multimeterRegex);
                if (match) {
                    const timestamp = new Date(match[1]);
                    const value = parseFloat(match[2]);
                    const mode = match[3];
                    const multimeterData = {
                        value: value.toString(),
                        unit: 'В',
                        mode: mode,
                        range_str: 'AUTO',
                        measure_type: 'Вольтметр',
                        timestamp: timestamp
                    };
                    updateMultimeterData(multimeterData);
                }
            } else if (data.type === 'status' && data.data && data.data.status === 'measurements_stopped') {
                measurementsActive = false;
            } else if (data.type === 'status' && data.data && data.data.status === 'measurements_started') {
                measurementsActive = true;
            }
        } catch (error) {
            console.error('Ошибка обработки WebSocket сообщения:', error);
        }
    };
}

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

function parseMultimeterRawData(rawDataStr, defaultValue) {
    if (!rawDataStr) {
        return defaultValue;
    }
    
    try {
        const rawParts = rawDataStr.split(';');
        if (rawParts.length >= 1) {
            const rawValue = rawParts[0];
            if (rawValue.length > 0) {
                const valueStr = rawValue.replace(/^0+/, '');
                if (valueStr.length > 3) {
                    return parseFloat(valueStr.slice(0, -3) + '.' + valueStr.slice(-3));
                } else {
                    return parseFloat('0.' + valueStr.padStart(3, '0'));
                }
            }
        }
        return defaultValue;
    } catch (e) {
        console.error('Ошибка при парсинге raw_data:', e);
        return defaultValue;
    }
}

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
            multimeterChart.data.datasets[0].label = `Напряжение, В (${currentMultimeterMode})`;
            multimeterChart.update();
        }
    } catch (error) {
        console.error('Ошибка обновления данных мультиметра:', error);
    }
}

function initCharts() {
    console.log('Инициализация графиков...');
    
    const oscilloCtxElement = document.getElementById('oscilloscopeChart');
    if (oscilloCtxElement) {
        const oscilloCtx = oscilloCtxElement.getContext('2d');
        oscilloscopeChart = new Chart(oscilloCtx, {
            type: 'line',
            data: {
                datasets: []
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                interaction: {
                    mode: 'nearest',
                    axis: 'x',
                    intersect: false
                },
                scales: {
                    x: {
                        type: 'linear',
                        position: 'bottom',
                        title: {
                            display: true,
                            text: 'Time (s)',
                            color: '#fff'
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: '#fff'
                        }
                    },
                    y: {
                        title: {
                            display: true,
                            text: 'Voltage (V)',
                            color: '#fff'
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: '#fff'
                        }
                    }
                },
                plugins: {
                    legend: {
                        position: 'top',
                        labels: {
                            color: '#fff',
                            font: {
                                size: 12
                            }
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(0,0,0,0.7)',
                        bodyFont: {
                            size: 13
                        },
                        titleFont: {
                            size: 14,
                            weight: 'bold'
                        },
                        callbacks: {
                            label: function(context) {
                                return `${context.dataset.label}: ${context.parsed.y.toFixed(3)}V @ ${context.parsed.x.toFixed(3)}s`;
                            }
                        }
                    }
                }
            }
        });
    } else {
        console.warn('Элемент oscilloscopeChart не найден');
    }
    
    const multiCtxElement = document.getElementById('multimeterChart');
    if (multiCtxElement) {
        const multiCtx = multiCtxElement.getContext('2d');
        multiCtx.canvas.style.width = '100%';
        multiCtx.canvas.style.height = '300px';
        multiCtx.imageSmoothingEnabled = false;
        multimeterChart = initMultimeterChart(multiCtx);
    } else {
        console.warn('Элемент multimeterChart не найден');
    }
    
    const oscilloHistoryCtxElement = document.getElementById('oscilloHistoryChart');
    if (oscilloHistoryCtxElement) {
        const oscilloHistoryCtx = oscilloHistoryCtxElement.getContext('2d');
        oscilloHistoryChart = new Chart(oscilloHistoryCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Напряжение (В)',
                    data: [],
                    borderColor: 'yellow',
                    backgroundColor: 'rgba(255, 255, 0, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: '#aaa'
                        }
                    },
                    x: {
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: '#aaa'
                        }
                    }
                },
                plugins: {
                    legend: {
                        labels: {
                            color: '#eee'
                        }
                    }
                }
            }
        });
        
        const oscilloHistoryPeriodElement = document.getElementById('oscilloHistoryPeriod');
        if (oscilloHistoryPeriodElement) {
            oscilloHistoryPeriodElement.addEventListener('change', loadOscilloscopeHistory);
        }
    } else {
        console.warn('Элемент oscilloHistoryChart не найден');
    }
    
    const multiHistoryCtxElement = document.getElementById('multimeterHistoryChart');
    if (multiHistoryCtxElement) {
        const multiHistoryCtx = multiHistoryCtxElement.getContext('2d');
        multimeterHistoryChart = new Chart(multiHistoryCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Показания',
                    data: [],
                    borderColor: '#00ffcc',
                    backgroundColor: 'rgba(0, 255, 204, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: '#aaa'
                        }
                    },
                    x: {
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: '#aaa'
                        }
                    }
                },
                plugins: {
                    legend: {
                        labels: {
                            color: '#eee'
                        }
                    }
                }
            }
        });
        
        const multiHistoryPeriodElement = document.getElementById('multimeterHistoryPeriod');
        if (multiHistoryPeriodElement) {
            multiHistoryPeriodElement.addEventListener('change', loadMultimeterHistory);
        }
    } else {
        console.warn('Элемент multimeterHistoryChart не найден');
    }
    
    for (let i = 1; i <= 4; i++) {
        const toggleElement = document.getElementById(`ch${i}Toggle`);
        if (toggleElement) {
            toggleElement.addEventListener('change', function() {
                if (oscilloscopeChart && oscilloscopeChart.data.datasets[i-1]) {
                    oscilloscopeChart.data.datasets[i-1].hidden = !this.checked;
                    oscilloscopeChart.update();
                }
            });
        }
    }
    
    const databaseTab = document.getElementById('database-tab');
    if (databaseTab) {
        databaseTab.addEventListener('click', () => {
            currentPage = 1;
            loadDatabaseData();
        });
    }
    
    const historyTab = document.getElementById('history-tab');
    if (historyTab) {
        historyTab.addEventListener('click', () => {
            if (oscilloHistoryChart) {
                loadOscilloscopeHistory();
            }
            if (multimeterHistoryChart) {
                loadMultimeterHistory();
            }
        });
    }
    
    console.log('Инициализация графиков завершена');
}

function loadOscilloscopeHistory() {
    if (!oscilloHistoryChart) {
        console.warn('График истории осциллографа не инициализирован');
        return;
    }
    
    const period = document.getElementById('oscilloHistoryPeriod')?.value || 'hour';
    
    fetch(`/history/oscilloscope?period=${period}`)
        .then(response => response.json())
        .then(data => {
            if (data.timestamps && data.timestamps.length > 0) {
                oscilloHistoryChart.data.labels = data.timestamps;
                oscilloHistoryChart.data.datasets[0].data = data.voltages || [];
                oscilloHistoryChart.update();
            } else {
                console.log('Нет данных истории осциллографа, генерируем тестовые данные');
                generateTestOscilloscopeHistory();
            }
        })
        .catch(error => {
            console.error('Ошибка при загрузке истории осциллографа:', error);
            generateTestOscilloscopeHistory();
        });
}

function loadMultimeterHistory() {
    if (!multimeterHistoryChart) {
        console.warn('График истории мультиметра не инициализирован');
        return;
    }
    
    const period = document.getElementById('multimeterHistoryPeriod')?.value || 'hour';
    
    fetch(`/history/multimeter?period=${period}`)
        .then(response => response.json())
        .then(data => {
            if (data.timestamps && data.timestamps.length > 0) {
                multimeterHistoryChart.data.labels = data.timestamps;
                multimeterHistoryChart.data.datasets[0].data = data.values || [];
                multimeterHistoryChart.update();
            } else {
                console.log('Нет данных истории мультиметра, генерируем тестовые данные');
                generateTestMultimeterHistory();
            }
        })
        .catch(error => {
            console.error('Ошибка при загрузке истории мультиметра:', error);
            generateTestMultimeterHistory();
        });
}

function generateTestOscilloscopeHistory() {
    if (!oscilloHistoryChart) {
        console.warn('График истории осциллографа не инициализирован');
        return;
    }
    
    const now = new Date();
    const timestamps = [];
    const voltages = [];
    
    for (let i = 10; i >= 0; i--) {
        const time = new Date(now.getTime() - i * 60000);
        timestamps.push(time.toLocaleTimeString());
        voltages.push(Math.random() * 5 + 2);
    }
    
    oscilloHistoryChart.data.labels = timestamps;
    oscilloHistoryChart.data.datasets[0].data = voltages;
    oscilloHistoryChart.update();
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

function saveToDatabase(data) {
    try {
        fetch('/save_data', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Ошибка HTTP: ' + response.status);
            }
            return response.json();
        })
        .then(result => {
            console.log('Данные успешно сохранены в БД:', result);
        })
        .catch(error => {
            console.error('Ошибка при сохранении в БД:', error);
        });
    } catch (e) {
        console.error('Ошибка при сохранении в БД:', e);
    }
}

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

function initApp() {
    console.log('Инициализация приложения...');
    
    initWebSocket();
    
    initCharts();
    
    const stopOscBtn = document.getElementById('stopOscilloscopeBtn');
    const startOscBtn = document.getElementById('startOscilloscopeBtn');
    
    if (stopOscBtn) {
        stopOscBtn.addEventListener('click', function() {
            if (websocket && websocket.readyState === WebSocket.OPEN) {
                websocket.send(JSON.stringify({ action: 'stop_oscilloscope' }));
            }
        });
    }
    
    if (startOscBtn) {
        startOscBtn.addEventListener('click', function() {
            if (websocket && websocket.readyState === WebSocket.OPEN) {
                websocket.send(JSON.stringify({ action: 'start_oscilloscope' }));
            }
        });
    }
    
    const stopMultBtn = document.getElementById('stopMultimeterBtn');
    const startMultBtn = document.getElementById('startMultimeterBtn');
    
    if (stopMultBtn) {
        stopMultBtn.addEventListener('click', function() {
            if (websocket && websocket.readyState === WebSocket.OPEN) {
                websocket.send(JSON.stringify({ action: 'stop_multimeter' }));
            }
        });
    }
    
    if (startMultBtn) {
        startMultBtn.addEventListener('click', function() {
            if (websocket && websocket.readyState === WebSocket.OPEN) {
                websocket.send(JSON.stringify({ action: 'start_multimeter' }));
            }
        });
    }
    
    setTimeout(() => {
        requestLatestMultimeterData();
    }, 1000);

    const testsTab = document.getElementById('tests-tab');
    if (testsTab) {
        const runLuaBtn = document.createElement('button');
        runLuaBtn.id = 'runLuaBtn';
        runLuaBtn.className = 'btn btn-primary ms-2';
        runLuaBtn.innerHTML = '<i class="fas fa-play"></i> Запустить Lua скрипт';
        runLuaBtn.addEventListener('click', runLuaScript);
        const buttonContainer = document.querySelector('.col-auto');
        if (buttonContainer) {
            buttonContainer.appendChild(runLuaBtn);
        }
    }
    
    const runLuaBtnTest = document.getElementById('runLuaBtnTest');
    if (runLuaBtnTest) {
        runLuaBtnTest.addEventListener('click', runLuaScript);
    }
    
    loadTestsList();
}

function requestLatestMultimeterData() {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        console.log('Запрашиваем последние данные мультиметра...');
        websocket.send(JSON.stringify({
            action: 'get_multimeter_data'
        }));
    } else {
        console.warn('WebSocket не подключен, не могу запросить данные мультиметра');
        setTimeout(requestLatestMultimeterData, 2000);
    }
}

function initMultimeterChart(ctx) {
    const chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: `Напряжение, В (${currentMultimeterMode})`,
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
                            return value.toFixed(3) + ' В';
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
                            return `Значение: ${context.parsed.y.toFixed(3)} В`;
                        }
                    }
                }
            }
        }
    });
    
    return chart;
}

function setActiveDbTab(type) {
    const oscilloTab = document.getElementById('oscillo-db-tab');
    const multiTab = document.getElementById('multi-db-tab');
    if (type === 'oscilloscope') {
        oscilloTab.classList.add('active');
        multiTab.classList.remove('active');
    } else {
        multiTab.classList.add('active');
        oscilloTab.classList.remove('active');
    }
}

function toggleDataView(type) {
    dbCurrentType = type;
    dbCurrentPage = 1;
    setActiveDbTab(type);
    document.getElementById('oscilloscopeData').style.display = (type === 'oscilloscope') ? 'block' : 'none';
    document.getElementById('multimeterData').style.display = (type === 'multimeter') ? 'block' : 'none';
    loadDatabaseData();
}

function renderDbPagination() {
    const pag = document.getElementById('dbPagination');
    pag.innerHTML = '';
    const prevLi = document.createElement('li');
    prevLi.className = 'page-item' + (dbCurrentPage === 1 ? ' disabled' : '');
    const prevBtn = document.createElement('button');
    prevBtn.className = 'page-link';
    prevBtn.innerHTML = '&laquo;';
    prevBtn.onclick = () => { if (dbCurrentPage > 1) { dbCurrentPage--; loadDatabaseData(); } };
    prevLi.appendChild(prevBtn);
    pag.appendChild(prevLi);
    const infoLi = document.createElement('li');
    infoLi.className = 'page-item disabled';
    const infoSpan = document.createElement('span');
    infoSpan.className = 'page-link';
    infoSpan.textContent = `${dbCurrentPage} / ${dbTotalPages}`;
    infoLi.appendChild(infoSpan);
    pag.appendChild(infoLi);
    const nextLi = document.createElement('li');
    nextLi.className = 'page-item' + (dbCurrentPage === dbTotalPages ? ' disabled' : '');
    const nextBtn = document.createElement('button');
    nextBtn.className = 'page-link';
    nextBtn.innerHTML = '&raquo;';
    nextBtn.onclick = () => { if (dbCurrentPage < dbTotalPages) { dbCurrentPage++; loadDatabaseData(); } };
    nextLi.appendChild(nextBtn);
    pag.appendChild(nextLi);
}

async function fetchChannelHistory(channel, limit = 1) {
    try {
        const resp = await fetch(`/db/oscilloscope_history?channel=${channel}&limit=${limit}`);
        if (!resp.ok) return null;
        return await resp.json();
    } catch (e) {
        return null;
    }
}

async function loadDatabaseData() {
    let endpoint;
    if (dbSelectedTest) {
        endpoint = `/tests/${dbSelectedTest}?type=${dbCurrentType}&limit=${dbPerPage}&page=${dbCurrentPage}`;
    } else {
        endpoint = dbCurrentType === 'oscilloscope'
            ? `/db/oscilloscope?page=${dbCurrentPage}&per_page=${dbPerPage}`
            : `/db/multimeter?page=${dbCurrentPage}&per_page=${dbPerPage}`;
    }
    try {
        const response = await fetch(endpoint);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const result = await response.json();
        if (!result || (typeof result !== 'object')) {
            throw new Error('Неверный формат ответа от сервера');
        }
        let data, total, totalPages;
        if (Array.isArray(result)) {
            data = result;
            total = result.length;
            totalPages = 1;
        } else if (result && result.data && Array.isArray(result.data)) {
            data = result.data;
            total = result.total || 0;
            totalPages = result.total_pages || 1;
        } else if (result && (result.oscilloscope || result.multimeter)) {
            if (dbCurrentType === 'oscilloscope' && Array.isArray(result.oscilloscope)) {
                data = result.oscilloscope;
                total = result.total || data.length;
                totalPages = result.total_pages || 1;
            } else if (dbCurrentType === 'multimeter' && Array.isArray(result.multimeter)) {
                data = result.multimeter;
                total = result.total || data.length;
                totalPages = result.total_pages || 1;
            } else {
                data = [];
                total = 0;
                totalPages = 1;
            }
        } else {
            console.error('Неизвестный формат ответа:', result);
            throw new Error('Неверная структура данных от сервера');
        }
        dbTotalPages = totalPages || 1;
        const tableBody = document.querySelector(dbCurrentType === 'oscilloscope' ? '#oscilloscopeData tbody' : '#multimeterData tbody');
        if (!tableBody) {
            throw new Error('Элемент таблицы не найден');
        }
        tableBody.innerHTML = '';
        if (dbCurrentType === 'oscilloscope') {
            for (const item of data) {
                const row = document.createElement('tr');
                const idCell = document.createElement('td');
                idCell.textContent = item.id || '';
                row.appendChild(idCell);
                const tsCell = document.createElement('td');
                tsCell.textContent = item.timestamp || '';
                row.appendChild(tsCell);
                const chCell = document.createElement('td');
                chCell.textContent = item.channel || '';
                row.appendChild(chCell);
                const svgCell = document.createElement('td');
                svgCell.className = 'graph-col';
                if (item.channel) {
                    fetchChannelHistory(item.channel, 1).then(hist => {
                        if (hist && hist.time && hist.voltage && hist.time.length > 0) {
                            svgCell.innerHTML = renderMiniOscilloscopeSVG(hist.time, hist.voltage, 1500, 60, item.channel);
                        } else {
                            svgCell.textContent = 'Нет данных';
                        }
                    }).catch(() => {
                        svgCell.textContent = 'Ошибка';
                    });
                } else {
                    svgCell.textContent = 'Нет данных';
                }
                row.appendChild(svgCell);
                tableBody.appendChild(row);
            }
        } else {
            data.forEach(item => {
                const row = document.createElement('tr');
                const idCell = document.createElement('td');
                idCell.textContent = item.id || '';
                row.appendChild(idCell);
                const tsCell = document.createElement('td');
                tsCell.textContent = item.timestamp || '';
                row.appendChild(tsCell);
                const valueCell = document.createElement('td');
                valueCell.textContent = item.value || '';
                row.appendChild(valueCell);
                const rawCell = document.createElement('td');
                rawCell.textContent = item.raw_data ? JSON.stringify(item.raw_data) : '';
                row.appendChild(rawCell);
                tableBody.appendChild(row);
            });
        }
        const dataCount = document.getElementById('dataCount');
        if (dataCount) {
            dataCount.textContent = `Всего записей: ${total}`;
        }
        renderDbPagination();
    } catch (error) {
        console.error('Ошибка при загрузке данных:', error);
        const tableBody = document.querySelector(dbCurrentType === 'oscilloscope' ? '#oscilloscopeData tbody' : '#multimeterData tbody');
        if (tableBody) {
            const colspan = dbCurrentType === 'oscilloscope' ? 4 : 4;
            tableBody.innerHTML = `<tr><td colspan="${colspan}" class="text-center text-danger">Ошибка при загрузке данных: ${error.message}</td></tr>`;
        }
        const dataCount = document.getElementById('dataCount');
        if (dataCount) {
            dataCount.textContent = 'Ошибка загрузки';
        }
    }
}

function decodeBase64ToFloat32Array(base64) {
    if (!base64) return [];
    const binary = atob(base64);
    const len = binary.length / 4;
    const arr = new Float32Array(len);
    for (let i = 0; i < len; i++) {
        arr[i] = new DataView(
            new Uint8Array([
                binary.charCodeAt(i*4),
                binary.charCodeAt(i*4+1),
                binary.charCodeAt(i*4+2),
                binary.charCodeAt(i*4+3)
            ]).buffer
        ).getFloat32(0, true);
    }
    return arr;
}

function renderMiniOscilloscopeSVG(timeArr, voltArr, width=1000, height=60, channelName='') {
    if (!timeArr.length || !voltArr.length) return '';
    let minT = Math.min(...timeArr), maxT = Math.max(...timeArr);
    let minV = Math.min(...voltArr), maxV = Math.max(...voltArr);
    if (minT === maxT) maxT += 1;
    if (minV === maxV) maxV += 1;
    let color = '#00ffcc';
    if (channelName === 'CH1') color = 'yellow';
    else if (channelName === 'CH2') color = 'cyan';
    else if (channelName === 'CH3') color = 'magenta';
    else if (channelName === 'CH4') color = '#00aaff';
    const paddingX = 40;
    let points = timeArr.map((t, i) => {
        let x = paddingX + ((t - minT) / (maxT - minT)) * (width - 2 * paddingX);
        let y = height - 2 - ((voltArr[i] - minV) / (maxV - minV)) * (height-4);
        return `${x},${y}`;
    }).join(' ');
    let label = channelName ? `<text x="${width/2}" y="${height-2}" fill="#fff" font-size="11" text-anchor="middle">${channelName}</text>` : '';
    return `<svg width="100%" height="${height}" viewBox="0 0 ${width} ${height}" style="background:#222;border-radius:3px;display:block;"><polyline fill="none" stroke="${color}" stroke-width="3" points="${points}"/>${label}</svg>`;
}

document.addEventListener('DOMContentLoaded', function() {
    initApp();
    setActiveDbTab('oscilloscope');
    dbCurrentPage = 1;
    dbCurrentType = 'oscilloscope';
    loadDatabaseData();
    updateDbTestSelect();
    document.getElementById('dbTestSelect').addEventListener('change', function() {
        dbSelectedTest = this.value;
        dbCurrentPage = 1;
        loadDatabaseData();
    });
});

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
    if (luaConsoleTest) luaConsoleTest.innerHTML = '';

    if (testUpdateInterval) {
        clearInterval(testUpdateInterval);
        testUpdateInterval = null;
    }

    if (websocket && websocket.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify({
            action: 'run_lua',
            script: 'main.lua'
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
                <p class="mb-1">Начало: ${test.start_time}</p>
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
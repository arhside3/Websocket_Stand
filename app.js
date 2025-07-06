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
    renderChannelInfoBlock('channelInfo', data.channels);
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
        renderMultimeterSVG(multimeterData);
    } catch (error) {
        console.error('Ошибка обновления данных мультиметра:', error);
    }
}

function initCharts() {
    const oscilloCtxElement = document.getElementById('oscilloscopeChart');
    const multiCtxElement = document.getElementById('multimeterChart');
    const oscilloHistoryCtxElement = document.getElementById('oscilloHistoryChart');
    const multiHistoryCtxElement = document.getElementById('multimeterHistoryChart');
    
    if (!oscilloCtxElement || !multiCtxElement || !oscilloHistoryCtxElement || !multiHistoryCtxElement) {
        console.error('Ошибка: Не найдены один или несколько элементов canvas для графиков');
        return;
    }

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
    
    const multiCtx = multiCtxElement.getContext('2d');
    
    multiCtx.canvas.style.width = '100%';
    multiCtx.canvas.style.height = '300px';
    multiCtx.imageSmoothingEnabled = false;
    
    multimeterChart = initMultimeterChart(multiCtx);
    
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

    const oscilloHistoryPeriodElement = document.getElementById('oscilloHistoryPeriod');
    if (oscilloHistoryPeriodElement) {
        oscilloHistoryPeriodElement.addEventListener('change', loadOscilloscopeHistory);
    }
    
    const multimeterHistoryPeriodElement = document.getElementById('multimeterHistoryPeriod');
    if (multimeterHistoryPeriodElement) {
        multimeterHistoryPeriodElement.addEventListener('change', loadMultimeterHistory);
    }

    multimeterData = {
        timestamps: [],
        values: []
    };

    const multiTestCtxElement = document.getElementById('multimeterChartTest');
    if (multiTestCtxElement) {
        const multiTestCtx = multiTestCtxElement.getContext('2d');
        window.multimeterChartTest = initMultimeterChart(multiTestCtx);
    }

    const oscilloTestCtxElement = document.getElementById('oscilloscopeChartTest');
    if (oscilloTestCtxElement) {
        console.log('Initializing oscilloscopeChartTest...');
        const oscilloTestCtx = oscilloTestCtxElement.getContext('2d');
        window.oscilloscopeChartTest = new Chart(oscilloTestCtx, {
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
                },
                scales: {
                    x: {
                        type: 'linear',
                        title: {
                            display: true,
                            text: 'Время (с)',
                            color: '#fff',
                            font: {
                                size: 14,
                                weight: 'bold'
                            }
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: '#fff',
                            font: {
                                size: 12
                            }
                        }
                    },
                    y: {
                        title: {
                            display: true,
                            text: 'Напряжение (В)',
                            color: '#fff',
                            font: {
                                size: 14,
                                weight: 'bold'
                            }
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: '#fff',
                            font: {
                                size: 12
                            }
                        }
                    }
                }
            }
        });
        console.log('oscilloscopeChartTest initialized successfully');
    } else {
        console.error('oscilloscopeChartTest canvas element not found!');
    }

    addClearTestChartButton();
}

function loadOscilloscopeHistory() {
    const period = document.getElementById('oscilloHistoryPeriod').value;
    
    fetch(`/history/oscilloscope?period=${period}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Ошибка HTTP: ' + response.status);
            }
            return response.json();
        })
        .then(data => {
            if (!data.timestamps || data.timestamps.length === 0) {
                generateTestOscilloscopeHistory();
                return;
            }
            
            oscilloHistoryChart.data.labels = data.timestamps;
            oscilloHistoryChart.data.datasets[0].data = data.voltages;
            oscilloHistoryChart.update();
        })
        .catch(error => {
            console.error('Ошибка при загрузке истории осциллографа:', error);
            generateTestOscilloscopeHistory();
        });
}

function loadMultimeterHistory() {
    const period = document.getElementById('multimeterHistoryPeriod').value;
    
    fetch(`/history/multimeter?period=${period}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Ошибка HTTP: ' + response.status);
            }
            return response.json();
        })
        .then(data => {
            if (!data.timestamps || data.timestamps.length === 0) {
                console.log('Нет данных мультиметра в БД за указанный период');
                multimeterHistoryChart.data.labels = [];
                multimeterHistoryChart.data.datasets[0].data = [];
                multimeterHistoryChart.update();
                return;
            }
            
            multimeterHistoryChart.data.labels = data.timestamps;
            multimeterHistoryChart.data.datasets[0].data = data.values;
            multimeterHistoryChart.update();
        })
        .catch(error => {
            console.error('Ошибка при загрузке истории мультиметра:', error);
            multimeterHistoryChart.data.labels = [];
            multimeterHistoryChart.data.datasets[0].data = [];
            multimeterHistoryChart.update();
        });
}

function generateTestOscilloscopeHistory() {
    const period = document.getElementById('oscilloHistoryPeriod').value;
    const points = period === 'hour' ? 60 : period === 'day' ? 24 : 7;
    
    const timestamps = [];
    const voltages = [];
    
    for (let i = 0; i < points; i++) {
        const date = new Date();
        date.setMinutes(date.getMinutes() - (period === 'hour' ? i : 0));
        date.setHours(date.getHours() - (period === 'day' ? i : 0));
        date.setDate(date.getDate() - (period === 'week' ? i : 0));
        
        timestamps.push(period === 'hour' ? 
            date.toTimeString().substr(0, 5) : 
            date.toLocaleDateString() + ' ' + date.toTimeString().substr(0, 5));
        
        voltages.push(Math.random() * 5);
    }
    
    oscilloHistoryChart.data.labels = timestamps.reverse();
    oscilloHistoryChart.data.datasets[0].data = voltages.reverse();
    oscilloHistoryChart.update();
}

function generateTestMultimeterHistory() {
    const period = document.getElementById('multimeterHistoryPeriod').value;
    const points = period === 'hour' ? 60 : period === 'day' ? 24 : 7;
    
    const timestamps = [];
    const values = [];
    
    for (let i = 0; i < points; i++) {
        const date = new Date();
        date.setMinutes(date.getMinutes() - (period === 'hour' ? i : 0));
        date.setHours(date.getHours() - (period === 'day' ? i : 0));
        date.setDate(date.getDate() - (period === 'week' ? i : 0));
        
        timestamps.push(period === 'hour' ? 
            date.toTimeString().substr(0, 5) : 
            date.toLocaleDateString() + ' ' + date.toTimeString().substr(0, 5));
        
        values.push(12 + Math.random() * 2);
    }
    
    multimeterHistoryChart.data.labels = timestamps.reverse();
    multimeterHistoryChart.data.datasets[0].data = values.reverse();
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
    initWebSocket();
    initCharts();
    
    loadOscilloscopeHistory();
    loadMultimeterHistory();
    
    document.getElementById('database-tab').addEventListener('click', () => {
        currentPage = 1;
        loadDatabaseData();
    });
    
    document.getElementById('history-tab').addEventListener('click', () => {
        loadOscilloscopeHistory();
        loadMultimeterHistory();
    });

    const multimeterContainer = document.getElementById('multimeterCard');
    if (multimeterContainer) {
        if (!document.getElementById('refreshMultimeterBtn')) {
            const refreshBtn = document.createElement('button');
            refreshBtn.id = 'refreshMultimeterBtn';
            refreshBtn.className = 'btn btn-sm btn-outline-info ml-2';
            refreshBtn.innerHTML = '<i class="fas fa-sync"></i> Обновить';
            refreshBtn.style.position = 'absolute';
            refreshBtn.style.right = '10px';
            refreshBtn.style.top = '10px';
            
            refreshBtn.addEventListener('click', function() {
                console.log('Принудительное обновление данных мультиметра');
                requestLatestMultimeterData();
            });
            
            
            refreshBtn.addEventListener('dblclick', function() {
                console.log('Сброс графика мультиметра');
                multimeterData = {
                    timestamps: [],
                    values: []
                };
                
                if (multimeterChart) {
                    multimeterChart.data.labels = [];
                    multimeterChart.data.datasets[0].data = [];
                    multimeterChart.update();
                }
                
                requestLatestMultimeterData();
            });
            
            multimeterContainer.style.position = 'relative';
            multimeterContainer.appendChild(refreshBtn);
        }
    }
    
    setTimeout(() => {
        requestLatestMultimeterData();
    }, 1000);

    const stopBtn = document.getElementById('stopMeasurementsBtn');
    if (stopBtn) {
        stopBtn.addEventListener('click', function() {
            if (websocket && websocket.readyState === WebSocket.OPEN) {
                websocket.send(JSON.stringify({ action: 'stop_measurements' }));
            }
        });
    }
    
    const startBtn = document.getElementById('startMeasurementsBtn');
    if (startBtn) {
        startBtn.addEventListener('click', function() {
            if (websocket && websocket.readyState === WebSocket.OPEN) {
                websocket.send(JSON.stringify({ action: 'start_measurements' }));
            }
            measurementsActive = true;
        });
    }

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
                label: 'Напряжение, В',
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

function updateChannelValues() {
    const channelValuesContainer = document.getElementById('channelValues');
    if (!channelValuesContainer) {
        const container = document.createElement('div');
        container.id = 'channelValues';
        container.className = 'channel-values mt-3';
        container.style.cssText = 'display: flex; justify-content: space-around; padding: 10px; background: #222; border-radius: 5px; margin: 10px;';
        
        const oscilloscopeElement = document.querySelector('.oscilloscope');
        if (oscilloscopeElement) {
            oscilloscopeElement.appendChild(container);
        }
    }
    
    const container = document.getElementById('channelValues');
    if (!container) return;
    
    container.innerHTML = '';
    
    for (const [channelName, data] of Object.entries(lastChannelValues)) {
        if (data.value !== null) {
            const channelDiv = document.createElement('div');
            channelDiv.className = 'channel-value';
            const opacity = data.active ? '1' : '0.5';
            channelDiv.style.cssText = `
                color: ${CHANNEL_COLORS[parseInt(channelName.slice(2)) - 1]}; 
                font-family: monospace; 
                font-size: 1.2em; 
                padding: 5px;
                opacity: ${opacity};
            `;
            channelDiv.innerHTML = `${channelName}: ${data.value.toFixed(3)} В ${data.active ? '' : '(отключен)'}`;
            container.appendChild(channelDiv);
        }
    }
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

async function loadDatabaseData() {
    let endpoint = dbCurrentType === 'oscilloscope'
        ? `/db/oscilloscope?page=${dbCurrentPage}&per_page=${dbPerPage}`
        : `/db/multimeter?page=${dbCurrentPage}&per_page=${dbPerPage}`;
    try {
        const response = await fetch(endpoint);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const result = await response.json();
        let data, total, totalPages;
        if (Array.isArray(result)) {
            data = result;
            total = result.length;
            totalPages = 1;
        } else if (result && result.data) {
            data = result.data;
            total = result.total;
            totalPages = result.total_pages;
        } else {
            console.error('Неизвестный формат ответа:', result);
            return;
        }
        dbTotalPages = totalPages || 1;
        const tableBody = document.querySelector(dbCurrentType === 'oscilloscope' ? '#oscilloscopeData tbody' : '#multimeterData tbody');
        tableBody.innerHTML = '';
        data.forEach(item => {
            const row = document.createElement('tr');
            Object.values(item).forEach(value => {
                const cell = document.createElement('td');
                cell.textContent = value !== null ? value : '';
                row.appendChild(cell);
            });
            tableBody.appendChild(row);
        });
        const dataCount = document.getElementById('dataCount');
        if (dataCount) {
            dataCount.textContent = `Всего записей: ${total}`;
        }
        renderDbPagination();
    } catch (error) {
        console.error('Ошибка при загрузке данных:', error);
        const tableBody = document.querySelector(dbCurrentType === 'oscilloscope' ? '#oscilloscopeData tbody' : '#multimeterData tbody');
        if (tableBody) {
            tableBody.innerHTML = `<tr><td colspan="5" class="text-center text-danger">Ошибка при загрузке данных: ${error.message}</td></tr>`;
        }
    }
}

document.addEventListener('DOMContentLoaded', function() {
    initApp();
    setActiveDbTab('oscilloscope');
    dbCurrentPage = 1;
    dbCurrentType = 'oscilloscope';
    loadDatabaseData();
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
    // SVG-график для испытаний
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
    // SVG-график для испытаний
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
    renderChannelInfoBlock('channelInfoTest', channelsBlock);
}

// SVG для испытаний (осциллограф)
function renderOscilloscopeSVGTest(channelsData) {
    const width = 2700, height = 800, padding = 60, gridCountY = 6, gridCountX = 10;
    let svg = `<svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}" style="background:#000;display:block;">`;
    // 1. Найти общий min/max по времени и напряжению
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
    // 2. Сетка и подписи
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
    // 3. Графики каналов
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
    // 4. Легенда
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

// SVG для испытаний (мультиметр)
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
    // Сетка и подписи
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
    // График
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

// === SVG ГРАФИКИ ===
function renderOscilloscopeSVG(channelsData) {
    const width = 2700, height = 1000, padding = 60, gridCountY = 6, gridCountX = 10;
    let svg = `<svg viewBox="0 0 ${width} ${height}" width="100%" height="${height}" style="background:#000;display:block;">`;
    // 1. Найти общий min/max по времени и напряжению
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
    // Добавим небольшой отступ
    let padV = (maxV - minV) * 0.1 || 1;
    minV -= padV; maxV += padV;
    // 2. Сетка и подписи
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
    // 3. Графики каналов
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
    // 4. Легенда
    let legendX = width - padding - 120, legendY = padding;
    Object.entries(channelsData).forEach(([ch, chData], idx) => {
        const color = chData.color || ['yellow', 'cyan', 'magenta', '#00aaff'][idx];
        svg += `<rect x="${legendX}" y="${legendY + idx * 26}" width="22" height="10" fill="${color}" />`;
        svg += `<text x="${legendX + 30}" y="${legendY + idx * 26 + 10}" fill="#fff" font-size="16">${ch}</text>`;
    });
    svg += `</svg>`;
    document.getElementById('oscilloscopeSVG').innerHTML = svg;
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
    // Сетка и подписи
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
    // График
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

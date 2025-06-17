const WEBSOCKET_URL = 'ws://127.0.0.1:8767';
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

// Для отслеживания последнего значения мультиметра
let lastMultimeterNumericValue = null;

// Добавляем отслеживание последних значений каналов
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

// Функция для запроса данных от осциллографа
function requestOscilloscopeData() {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify({
            action: 'get_oscilloscope_data'
        }));
    }
}

function startPeriodicUpdates() {
    // Запрашиваем данные от осциллографа и мультиметра
    requestOscilloscopeData();
    requestMultimeterData();
    
    // Устанавливаем интервал обновления
    setInterval(() => {
        requestOscilloscopeData();
        requestMultimeterData();
    }, UPDATE_INTERVAL);
}

// Функция для запроса данных от мультиметра
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
        // appendToConsole('> Соединение установлено');

        // Запрашиваем данные сразу после подключения
        console.log('Запрашиваем данные мультиметра после подключения...');
        websocket.send(JSON.stringify({
            action: 'get_multimeter_data'
        }));
        
        // Даем время на получение данных мультиметра и затем запрашиваем данные осциллографа
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
        // appendToConsole('> Соединение разорвано');
        
        setTimeout(initWebSocket, 5000);
    };
    
    websocket.onerror = function(error) {
        // appendToConsole('> Ошибка: ' + error.message);
        console.error('WebSocket error:', error);
    };
    
    websocket.onmessage = function(event) {
        console.log('WS message:', event.data);
        try {
            const data = JSON.parse(event.data);
            
            if (data.channels || (data.time_base && data.channels)) {
                console.log('Received oscilloscope data:', data);
                // Обновляем график в обычном режиме
                updateOscilloscopeData(data);
                // Если активен Lua-тест, обновляем и тестовый график
                if (luaTestActive) {
                    updateOscilloscopeTestData(data);
                }
            }
            else if (data.type === 'multimeter' && data.data) {
                updateMultimeterData(data.data);
                updateMultimeterTestData(data.data);
            }
            else if (data.time && data.voltage) {
                // Обновляем график в обычном режиме
                updateOscilloscopeData(data);
            }
            else if (data.type === 'lua_output') {
                addToLuaConsoleTest(data.line);
            }
            else if (data.type === 'lua_status') {
                setTimeout(() => { luaTestActive = false; }, 1000); // задержка 1 секунда
                addToLuaConsoleTest(data.success ? '<span style="color:lime">Сценарий завершён успешно</span>' : '<span style="color:red">Ошибка выполнения сценария</span>');
            }
            else if (data.output) {
                // Проверяем, содержит ли вывод данные мультиметра
                const multimeterRegex = /\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\] ([\d.]+) В (DC|AC) AUTO \[Вольтметр\]/;
                const match = data.output.match(multimeterRegex);
                
                if (match) {
                    const timestamp = new Date(match[1]);
                    const value = parseFloat(match[2]);
                    const mode = match[3];
                    
                    // Создаем объект с данными мультиметра
                    const multimeterData = {
                        value: value.toString(),
                        unit: 'В',
                        mode: mode,
                        range_str: 'AUTO',
                        measure_type: 'Вольтметр',
                        timestamp: timestamp
                    };
                    
                    // Обновляем график напрямую
                    updateMultimeterData(multimeterData);
                }
            }
            else if (data.type === 'status' && data.data && data.data.status === 'measurements_stopped') {
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
    console.log('updateOscilloscopeData called', data);
    if (!oscilloscopeChart || !measurementsActive) return;
    
    // Handle both new and legacy data formats
    const oscilloscopeData = data.type === 'oscilloscope_data' ? data.data : data;
    
    oscilloscopeChart.data.datasets = [];
    
    if (oscilloscopeData.channels) {
        // Process each channel's data
        for (const [channelName, channelData] of Object.entries(oscilloscopeData.channels)) {
            if (channelData.voltage && channelData.voltage.length > 0) {
                const channelNumber = parseInt(channelName.slice(2)) - 1;
                const color = channelData.color || CHANNEL_COLORS[channelNumber];
                
                oscilloscopeChart.data.datasets.push({
                    label: channelName,
                    data: channelData.time.map((t, i) => ({ x: t, y: channelData.voltage[i] })),
                    borderColor: color,
                    backgroundColor: 'transparent',
                    borderWidth: 2,
                    pointRadius: 0,
                    tension: 0.1
                });
                
                // Update channel info if available
                if (channelData.settings) {
                    updateChannelInfo(channelName, channelData.settings);
                }
            }
        }
    }
    
    // Update chart scales if time base is available
    if (oscilloscopeData.time_base) {
        const timeScale = oscilloscopeData.time_base * 6; // 6 divisions
        oscilloscopeChart.options.scales.x.min = -timeScale;
        oscilloscopeChart.options.scales.x.max = timeScale;
    }
    
    // Update trigger level if available
    if (oscilloscopeData.trigger_level !== undefined) {
        updateTriggerLevel(oscilloscopeData.trigger_level);
    }
    
    oscilloscopeChart.update('none');
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

// Добавляем функцию для парсинга raw_data мультиметра
function parseMultimeterRawData(rawDataStr, defaultValue) {
    if (!rawDataStr) {
        return defaultValue;
    }
    
    try {
        // Формат raw_data: "00432;806" - первая часть это основное значение
        const rawParts = rawDataStr.split(';');
        if (rawParts.length >= 1) {
            const rawValue = rawParts[0];
            if (rawValue.length > 0) {
                // Удаляем ведущие нули и добавляем десятичную точку в правильное место
                const valueStr = rawValue.replace(/^0+/, ''); // Удаляем ведущие нули
                if (valueStr.length > 3) {
                    // Вставляем десятичную точку в правильное место
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

// Высокопроизводительная функция обновления графика мультиметра
function updateMultimeterData(data) {
    console.log('updateMultimeterData called', data);
    if (!measurementsActive) return;
    try {
        // 1. Обновляем DOM элементы
        document.getElementById('multimeterValue').innerHTML = 
            data.value + ' <span id="multimeterUnit">' + data.unit + '</span>';
        document.getElementById('multimeterMode').textContent = data.mode || '';
        document.getElementById('multimeterRange').textContent = data.range_str || 'AUTO';
        document.getElementById('multimeterType').textContent = data.measure_type || '';
        
        // 2. Преобразуем значение в число
        let value = parseFloat(data.value);
        if (isNaN(value) || data.value === 'OL') {
            console.warn('Некорректное значение мультиметра:', data.value);
            return;
        }
        
        // 3. Добавляем новую точку данных
        const timestamp = data.timestamp ? new Date(data.timestamp) : new Date();
        
        multimeterData.timestamps.push(timestamp);
        multimeterData.values.push(value);
        
        // 4. Ограничиваем количество точек
        while (multimeterData.timestamps.length > MAX_MULTIMETER_POINTS) {
            multimeterData.timestamps.shift();
            multimeterData.values.shift();
        }
        
        // 5. Обновляем график
        if (multimeterChart) {
            // Обновляем метки времени и данные
            multimeterChart.data.labels = multimeterData.timestamps;
            multimeterChart.data.datasets[0].data = multimeterData.values.map((v, i) => ({
                x: multimeterData.timestamps[i],
                y: v
            }));
            
            // Устанавливаем диапазон осей
            const minValue = Math.min(...multimeterData.values);
            const maxValue = Math.max(...multimeterData.values);
            const padding = Math.max((maxValue - minValue) * 0.1, 0.1); // Минимальный отступ 0.1В
            
            multimeterChart.options.scales.y.min = Math.max(0, minValue - padding); // Не опускаем ниже 0 для вольтметра
            multimeterChart.options.scales.y.max = maxValue + padding;
            
            // Обновляем заголовок графика
            multimeterChart.options.plugins.title = {
                display: true,
                text: `Измерения мультиметра (${data.mode} ${data.measure_type})`,
                color: '#fff',
                font: {
                    size: 14,
                    weight: 'bold'
                }
            };
            
            // Обновляем график с анимацией
            multimeterChart.update();
        }
    } catch (error) {
        console.error('Ошибка обновления данных мультиметра:', error);
    }
}

function initCharts() {
    // Инициализация графиков
    const oscilloCtxElement = document.getElementById('oscilloscopeChart');
    const multiCtxElement = document.getElementById('multimeterChart');
    const oscilloHistoryCtxElement = document.getElementById('oscilloHistoryChart');
    const multiHistoryCtxElement = document.getElementById('multimeterHistoryChart');
    
    if (!oscilloCtxElement || !multiCtxElement || !oscilloHistoryCtxElement || !multiHistoryCtxElement) {
        console.error('Ошибка: Не найдены один или несколько элементов canvas для графиков');
        return;
    }

    // Инициализация графика осциллографа
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
    
    // Инициализация оптимизированного графика мультиметра
    const multiCtx = multiCtxElement.getContext('2d');
    
    // Настройка canvas для лучшей производительности
    multiCtx.canvas.style.width = '100%';
    multiCtx.canvas.style.height = '300px';
    multiCtx.imageSmoothingEnabled = false; // Отключение сглаживания для увеличения производительности
    
    // Создаем высокопроизводительный график
    multimeterChart = initMultimeterChart(multiCtx);
    
    // Инициализация остальных графиков
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

    // Начальная настройка данных мультиметра
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
                // Очищаем график вместо генерации тестовых данных
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
            // Очищаем график при ошибке
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

function updateOscilloscopeTestData(data) {
    console.log('updateOscilloscopeTestData called with data:', data);
    if (!data.channels) {
        console.warn('No channels data in updateOscilloscopeTestData');
        return;
    }
    
    // Загружаем данные из БД для тестового графика
    fetch('/history/oscilloscope?period=test')
        .then(response => response.json())
        .then(dbData => {
            if (!dbData || !dbData.timestamps || dbData.timestamps.length === 0) {
                console.warn('No data from database for test chart');
                return;
            }

            // Обновляем данные для тестового графика
            oscilloscopeTestData.timestamps = dbData.timestamps;
            oscilloscopeTestData.channels = {
                CH1: { values: [], active: true },
                CH2: { values: [], active: true },
                CH3: { values: [], active: true },
                CH4: { values: [], active: true }
            };

            // Заполняем данные каналов из БД
            dbData.channels.forEach(channelData => {
                const channelName = channelData.name;
                if (oscilloscopeTestData.channels[channelName]) {
                    oscilloscopeTestData.channels[channelName].values = channelData.values;
                    oscilloscopeTestData.channels[channelName].active = true;
                }
            });

            // Обновляем график
            if (window.oscilloscopeChartTest) {
                console.log('Updating oscilloscopeChartTest with DB data...');
                const chart = window.oscilloscopeChartTest;
                chart.data.datasets = [];

                for (const [channelName, channelData] of Object.entries(oscilloscopeTestData.channels)) {
                    if (channelData.values.length > 0) {
                        const channelNumber = parseInt(channelName.slice(2)) - 1;
                        const dataset = {
                            label: channelName,
                            data: channelData.values.map((v, i) => ({
                                x: new Date(oscilloscopeTestData.timestamps[i]),
                                y: v
                            })),
                            borderColor: CHANNEL_COLORS[channelNumber],
                            backgroundColor: 'transparent',
                            borderWidth: 2,
                            pointRadius: 0,
                            hidden: !channelData.active
                        };
                        chart.data.datasets.push(dataset);
                        console.log(`Added dataset for ${channelName}:`, dataset);
                    }
                }

                chart.update();
                console.log('oscilloscopeChartTest updated successfully with DB data');
            }
        })
        .catch(error => {
            console.error('Error loading test data from database:', error);
        });
}

// Обновляем функцию runLuaScript, чтобы она загружала данные из БД
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
    
    // Очищаем график осциллографа
    if (oscilloscopeChart) {
        oscilloscopeChart.data.datasets = [];
        oscilloscopeChart.update();
    }
    
    const luaConsoleTest = document.getElementById('luaConsoleTest');
    if (luaConsoleTest) luaConsoleTest.innerHTML = '';
    
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        console.log('Запуск Lua скрипта...');
        websocket.send(JSON.stringify({
            action: 'run_lua',
            script: 'main.lua'
        }));

        // Загружаем данные из БД для тестового графика
        fetch('/history/oscilloscope?period=test')
            .then(response => response.json())
            .then(data => {
                if (data && data.timestamps && data.timestamps.length > 0) {
                    updateOscilloscopeTestData(data);
                }
            })
            .catch(error => {
                console.error('Error loading test data:', error);
            });
    } else {
        console.error('WebSocket не подключен');
        alert('Ошибка: WebSocket не подключен');
        luaTestActive = false;
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

    // Добавляем кнопку обновления мультиметра если её нет
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
            
            // При двойном клике - сбрасываем график
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
            
            // Добавляем кнопку в верхний правый угол карточки мультиметра
            multimeterContainer.style.position = 'relative';
            multimeterContainer.appendChild(refreshBtn);
        }
    }
    
    // Запрашиваем текущие данные мультиметра при загрузке
    setTimeout(() => {
        requestLatestMultimeterData();
    }, 1000);

    // Кнопка остановки измерений
    const stopBtn = document.getElementById('stopMeasurementsBtn');
    if (stopBtn) {
        stopBtn.addEventListener('click', function() {
            if (websocket && websocket.readyState === WebSocket.OPEN) {
                websocket.send(JSON.stringify({ action: 'stop_measurements' }));
            }
        });
    }
    // Кнопка старта измерений
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
        // Добавляем кнопку после кнопок управления измерениями
        const buttonContainer = document.querySelector('.col-auto');
        if (buttonContainer) {
            buttonContainer.appendChild(runLuaBtn);
        }
    }
}

// Функция для запроса последних данных мультиметра
function requestLatestMultimeterData() {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        console.log('Запрашиваем последние данные мультиметра...');
        websocket.send(JSON.stringify({
            action: 'get_multimeter_data'
        }));
    } else {
        console.warn('WebSocket не подключен, не могу запросить данные мультиметра');
        // Пробуем через 2 секунды снова
        setTimeout(requestLatestMultimeterData, 2000);
    }
}

// Функция для инициализации графика мультиметра с оптимальной производительностью
function initMultimeterChart(ctx) {
    // Оптимизация для максимальной производительности
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
                fill: true,  // Включаем заливку для лучшей визуализации
                tension: 0.3,   // Небольшое сглаживание для красоты
                pointRadius: 2,  // Маленькие точки для отслеживания измерений
                pointBackgroundColor: '#00ffcc'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: {
                duration: 300  // Плавное обновление
            },
            interaction: {
                intersect: false,
                mode: 'index'
            },
            scales: {
                y: {
                    beginAtZero: false,
                    grid: {
                        display: true,  // Включаем сетку
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: '#aaa',
                        maxTicksLimit: 8,  // Увеличиваем количество делений
                        callback: function(value) {
                            return value.toFixed(3) + ' В';  // Форматируем значения
                        }
                    }
                },
                x: {
                    grid: {
                        display: true,  // Включаем сетку
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: '#aaa',
                        maxTicksLimit: 8,
                        maxRotation: 0,
                        callback: function(value, index, values) {
                            const date = new Date(this.getLabelForValue(value));
                            return date.toTimeString().substr(0, 8);  // Форматируем время
                        }
                    }
                }
            },
            plugins: {
                legend: { display: true },  // Показываем легенду
                tooltip: {
                    enabled: true,  // Включаем подсказки
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

// Функция для обновления отображения значений каналов
function updateChannelValues() {
    const channelValuesContainer = document.getElementById('channelValues');
    if (!channelValuesContainer) {
        // Создаем контейнер, если его нет
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
            const opacity = data.active ? '1' : '0.5'; // Уменьшаем прозрачность для неактивных каналов
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
    // Prev
    const prevLi = document.createElement('li');
    prevLi.className = 'page-item' + (dbCurrentPage === 1 ? ' disabled' : '');
    const prevBtn = document.createElement('button');
    prevBtn.className = 'page-link';
    prevBtn.innerHTML = '&laquo;';
    prevBtn.onclick = () => { if (dbCurrentPage > 1) { dbCurrentPage--; loadDatabaseData(); } };
    prevLi.appendChild(prevBtn);
    pag.appendChild(prevLi);
    // Page info
    const infoLi = document.createElement('li');
    infoLi.className = 'page-item disabled';
    const infoSpan = document.createElement('span');
    infoSpan.className = 'page-link';
    infoSpan.textContent = `${dbCurrentPage} / ${dbTotalPages}`;
    infoLi.appendChild(infoSpan);
    pag.appendChild(infoLi);
    // Next
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
        // Обновляем таблицу
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
        // Счетчик
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
    // Сразу активируем правильный таб и первую страницу
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
    const chartElem = document.getElementById('multimeterChartTest');

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
    if (!chartElem) return;
    if (window.multimeterChartTest) {
        const chart = window.multimeterChartTest;
        chart.data.labels = multimeterTestData.timestamps;
        chart.data.datasets[0].data = multimeterTestData.values.map((v, i) => ({ x: multimeterTestData.timestamps[i], y: v }));
        if (multimeterTestData.values.length > 0) {
            const minValue = Math.min(...multimeterTestData.values);
            const maxValue = Math.max(...multimeterTestData.values);
            const padding = Math.max((maxValue - minValue) * 0.1, 0.1);
            chart.options.scales.y.min = Math.max(0, minValue - padding);
            chart.options.scales.y.max = maxValue + padding;
        }
        chart.options.plugins.title = {
            display: true,
            text: `Измерения мультиметра (${data.mode} ${data.measure_type})`,
            color: '#fff',
            font: { size: 14, weight: 'bold' }
        };
        chart.update();
    }
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
        // Clear multimeter data
        multimeterTestData = { timestamps: [], values: [] };
        if (window.multimeterChartTest) {
            window.multimeterChartTest.data.labels = [];
            window.multimeterChartTest.data.datasets[0].data = [];
            window.multimeterChartTest.update();
        }
        
        // Clear oscilloscope data
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
    };
    
    if (chartElem.parentElement) {
        chartElem.parentElement.style.position = 'relative';
        chartElem.parentElement.appendChild(btn);
    }
}
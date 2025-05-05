const WEBSOCKET_URL = 'ws://localhost:8765';
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


document.getElementById('runLuaBtn').addEventListener('click', function() {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify({
            action: 'run_lua',
            script: 'main.lua'
        }));
        
        appendToConsole('> Запуск Lua-сценария...');
    } else {
        appendToConsole('> Ошибка: WebSocket не подключен');
    }
});

function appendToConsole(message) {
    const console = document.getElementById('luaConsole');
    console.innerHTML += message + '<br>';
    console.scrollTop = console.scrollHeight;
}

function initWebSocket() {
    websocket = new WebSocket(WEBSOCKET_URL);
    
    websocket.onopen = function() {
        document.getElementById('statusIndicator').classList.add('connected');
        document.getElementById('statusIndicator').classList.remove('disconnected');
        document.getElementById('statusIndicator').title = 'Подключено';
        appendToConsole('> Соединение установлено');
    };
    
    websocket.onclose = function() {
        document.getElementById('statusIndicator').classList.remove('connected');
        document.getElementById('statusIndicator').classList.add('disconnected');
        document.getElementById('statusIndicator').title = 'Соединение разорвано';
        appendToConsole('> Соединение разорвано');
        
        setTimeout(initWebSocket, 5000);
    };
    
    websocket.onerror = function(error) {
        appendToConsole('> Ошибка: ' + error.message);
    };
    
    websocket.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            
            if (data.time && data.voltage) {
                updateOscilloscopeData(data);
                saveToDatabase({
                    type: 'oscilloscope',
                    data: data
                });
            } else if (data.value !== undefined) {
                updateMultimeterData(data);
                saveToDatabase({
                    type: 'multimeter',
                    data: data
                });
            } else if (data.output) {
                appendToConsole('> ' + data.output);
                
                const multimeterRegex = /\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\] ([\d.]+) В DC AUTO \[Вольтметр\]/;
                const match = data.output.match(multimeterRegex);
                
                if (match) {
                    const value = match[2];
                    const timestamp = new Date();
                    
                    lastMultimeterValue = {
                        value: value,
                        unit: 'В',
                        mode: 'DC',
                        range_str: 'AUTO',
                        measure_type: 'Вольтметр'
                    };
                    
                    updateMultimeterData(lastMultimeterValue);
                    
                    multimeterData.timestamps.push(timestamp);
                    multimeterData.values.push(parseFloat(value));
                    
                    if (multimeterData.timestamps.length > MAX_MULTIMETER_POINTS) {
                        multimeterData.timestamps.shift();
                        multimeterData.values.shift();
                    }
                    
                    if (multimeterChart) {
                        multimeterChart.data.labels = multimeterData.timestamps.map(t => 
                            t.toTimeString().substr(0, 8));
                        multimeterChart.data.datasets[0].data = multimeterData.values;
                        multimeterChart.update();
                    }
                    
                    saveToDatabase({
                        type: 'multimeter',
                        data: {
                            value: value,
                            unit: 'В',
                            mode: 'DC',
                            range_str: 'AUTO',
                            measure_type: 'Вольтметр',
                            timestamp: timestamp.toLocaleString('ru-RU', {
                                year: 'numeric',
                                month: '2-digit',
                                day: '2-digit',
                                hour: '2-digit',
                                minute: '2-digit',
                                second: '2-digit',
                                fractionalSecondDigits: 3
                            }).replace(',', '')
                        }
                    });
                }
            }
        } catch (e) {
            console.error('Ошибка при обработке сообщения:', e);
        }
    };
}

function updateOscilloscopeData(data) {
    if (!oscilloscopeChart) return;
    
    if (Array.isArray(data.voltage[0])) {
        for (let i = 0; i < data.voltage.length; i++) {
            if (document.getElementById(`ch${i+1}Toggle`).checked) {
                oscilloscopeChart.data.datasets[i].data = data.voltage[i].map((v, idx) => ({
                    x: data.time[idx],
                    y: v
                }));
            }
        }
    } else {
        oscilloscopeChart.data.datasets[0].data = data.voltage.map((v, idx) => ({
            x: data.time[idx],
            y: v
        }));
    }
    
    oscilloscopeChart.update();
}

function updateMultimeterData(data) {
    document.getElementById('multimeterValue').innerHTML = 
        data.value + ' <span id="multimeterUnit">' + data.unit + '</span>';
    document.getElementById('multimeterMode').textContent = data.mode || '';
    document.getElementById('multimeterRange').textContent = data.range_str || 'AUTO';
    document.getElementById('multimeterType').textContent = data.measure_type || '';
    
    const timestamp = new Date();
    let value = data.value;
    
    if (value === 'OL') {
        value = multimeterData.values.length > 0 ? 
            Math.max(...multimeterData.values.filter(v => !isNaN(v))) * 1.2 : 1000;
    } else {
        value = parseFloat(value);
    }
    
    multimeterData.timestamps.push(timestamp);
    multimeterData.values.push(value);
    
    if (multimeterData.timestamps.length > MAX_MULTIMETER_POINTS) {
        multimeterData.timestamps.shift();
        multimeterData.values.shift();
    }
    
    if (multimeterChart) {
        multimeterChart.data.labels = multimeterData.timestamps.map(t => 
            t.toTimeString().substr(0, 8));
        multimeterChart.data.datasets[0].data = multimeterData.values;
        multimeterChart.update();
    }
}

function initCharts() {

    const oscilloCtx = document.getElementById('oscilloscopeChart').getContext('2d');
    oscilloscopeChart = new Chart(oscilloCtx, {
        type: 'line',
        data: {
            datasets: Array(4).fill().map((_, i) => ({
                label: `Канал ${i+1}`,
                data: [],
                borderColor: CHANNEL_COLORS[i],
                borderWidth: 2,
                pointRadius: 0,
                tension: 0.1,
                fill: false
            }))
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            scales: {
                x: {
                    type: 'linear',
                    position: 'bottom',
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)'
                    },
                    ticks: {
                        color: '#aaa'
                    }
                },
                y: {
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
    
    const multiCtx = document.getElementById('multimeterChart').getContext('2d');
    multimeterChart = new Chart(multiCtx, {
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
                    beginAtZero: true,
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
                        color: '#aaa',
                        maxRotation: 0,
                        autoSkip: true,
                        maxTicksLimit: 10
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
    
    const oscilloHistoryCtx = document.getElementById('oscilloHistoryChart').getContext('2d');
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
    
    const multiHistoryCtx = document.getElementById('multimeterHistoryChart').getContext('2d');
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
        document.getElementById(`ch${i}Toggle`).addEventListener('change', function() {
            oscilloscopeChart.data.datasets[i-1].hidden = !this.checked;
            oscilloscopeChart.update();
        });
    }
    

    document.getElementById('oscilloHistoryPeriod').addEventListener('change', loadOscilloscopeHistory);
    document.getElementById('multimeterHistoryPeriod').addEventListener('change', loadMultimeterHistory);
}


function loadOscilloscopeHistory() {
    const period = document.getElementById('oscilloHistoryPeriod').value;
    
    fetch(`/history/oscilloscope?period=${period}`)
        .then(response => response.json())
        .then(data => {
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
        .then(response => response.json())
        .then(data => {
            multimeterHistoryChart.data.labels = data.timestamps;
            multimeterHistoryChart.data.datasets[0].data = data.values;
            multimeterHistoryChart.update();
        })
        .catch(error => {
            console.error('Ошибка при загрузке истории мультиметра:', error);
            generateTestMultimeterHistory();
        });
}

function loadOscilloscopeDB() {
    fetch('/db/oscilloscope')
        .then(response => response.json())
        .then(data => {
            const tbody = document.querySelector('#oscilloscopeDataTable tbody');
            tbody.innerHTML = '';
            
            data.forEach(row => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${row.id}</td>
                    <td>${row.timestamp}</td>
                    <td>${row.channel}</td>
                    <td>${row.voltage}</td>
                    <td>${row.frequency}</td>
                `;
                tbody.appendChild(tr);
            });
        })
        .catch(error => {
            console.error('Ошибка при загрузке данных осциллографа из БД:', error);
            generateTestOscilloscopeDB();
        });
}

function loadMultimeterDB() {
    fetch('/db/multimeter')
        .then(response => response.json())
        .then(data => {
            const tbody = document.querySelector('#multimeterDataTable tbody');
            tbody.innerHTML = '';
            
            data.forEach(row => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${row.id}</td>
                    <td>${row.timestamp}</td>
                    <td>${row.value}</td>
                    <td>${row.unit}</td>
                    <td>${row.mode}</td>
                    <td>${row.range_str}</td>
                    <td>${row.measure_type}</td>
                `;
                tbody.appendChild(tr);
            });
        })
        .catch(error => {
            console.error('Ошибка при загрузке данных мультиметра из БД:', error);
            generateTestMultimeterDB();
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

function generateTestOscilloscopeDB() {
    const tbody = document.querySelector('#oscilloscopeDataTable tbody');
    tbody.innerHTML = '';
    
    for (let i = 1; i <= 10; i++) {
        const date = new Date();
        date.setMinutes(date.getMinutes() - i);
        
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${i}</td>
            <td>${date.toLocaleDateString()} ${date.toTimeString().substr(0, 8)}</td>
            <td>CH1</td>
            <td>${(Math.random() * 5).toFixed(2)}</td>
            <td>${(Math.random() * 1000 + 50).toFixed(2)}</td>
        `;
        tbody.appendChild(tr);
    }
}

function generateTestMultimeterDB() {
    const tbody = document.querySelector('#multimeterDataTable tbody');
    tbody.innerHTML = '';
    
    for (let i = 1; i <= 10; i++) {
        const date = new Date();
        date.setMinutes(date.getMinutes() - i);
        
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${i}</td>
            <td>${date.toLocaleDateString()} ${date.toTimeString().substr(0, 8)}</td>
            <td>${(Math.random() * 20).toFixed(3)}</td>
            <td>В</td>
            <td>DC</td>
            <td>AUTO</td>
            <td>Вольтметр</td>
        `;
        tbody.appendChild(tr);
    }
}

function saveToDatabase(data) {
    fetch('/save_data', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data)
    })
    .catch(error => console.error('Ошибка при сохранении в БД:', error));
}
function initApp() {

    initWebSocket();
    initCharts();
    
    loadOscilloscopeHistory();
    loadMultimeterHistory();
    

    document.getElementById('database-tab').addEventListener('click', () => {
        loadOscilloscopeDB();
        loadMultimeterDB();
    });
    
    document.getElementById('history-tab').addEventListener('click', () => {
        loadOscilloscopeHistory();
        loadMultimeterHistory();
    });
}

document.addEventListener('DOMContentLoaded', initApp);
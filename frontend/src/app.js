const WEBSOCKET_URL = 'ws://127.0.0.1:8767';
const UPDATE_INTERVAL = 1000; 

let websocket;
let measurementsActive = true;
let currentPage = 1;
let totalPages = 1;
let currentPerPage = 10;
let dbCurrentPage = 1;
const dbPerPage = 50;
let dbTotalPages = 1;
let dbCurrentType = 'oscilloscope';
let dbSelectedTest = '';
window.oscilloscopeChart = null;
window.multimeterChart = null;
window.multimeterHistoryChart = null;
window.oscilloHistoryChart = null;

function initWebSocket() {
    websocket = new WebSocket(WEBSOCKET_URL);
    
    websocket.onopen = function() {
        document.getElementById('statusIndicator').classList.add('connected');
        document.getElementById('statusIndicator').classList.remove('disconnected');
        document.getElementById('statusIndicator').title = 'Подключено';

        websocket.send(JSON.stringify({
            action: 'get_multimeter_data'
        }));
        
        setTimeout(() => {
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
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'oscilloscope') {
                parseAndAddOscilloscopeTestData(data.line);
            } else if (data.type === 'multimeter') {
                if (data.line) {
                    const regex = /\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\] ([\d.]+) V (DC|AC) AUTO \[Вольтметр\]/;
                    const match = data.line.match(regex);
                    if (match) {
                        const timestamp = match[1];
                        const value = match[2];
                        const mode = match[3];
                        updateMultimeterTestData({
                            value: value,
                            unit: 'V',
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
                const multimeterRegex = /\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\] ([\d.]+) V (DC|AC) AUTO \[Вольтметр\]/;
                const match = data.output.match(multimeterRegex);
                if (match) {
                    const timestamp = new Date(match[1]);
                    const value = parseFloat(match[2]);
                    const mode = match[3];
                    const multimeterData = {
                        value: value.toString(),
                        unit: 'V',
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

function requestOscilloscopeData() {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify({
            action: 'get_oscilloscope_data'
        }));
    }
}

function requestMultimeterData() {
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify({
            action: 'get_multimeter_data'
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

function initCharts() {
    console.log('Инициализация графиков...');

    const oscilloCtxElement = document.getElementById('oscilloscopeChart');
    if (oscilloCtxElement) {
        const oscilloCtx = oscilloCtxElement.getContext('2d');
        window.oscilloscopeChart = new Chart(oscilloCtx, {
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
        // Предполагается, что функция initMultimeterChart есть у вас в коде
        if (typeof initMultimeterChart === "function") {
            window.multimeterChart = initMultimeterChart(multiCtx);
        } else {
            console.warn('Функция initMultimeterChart не определена');
        }
    } else {
        console.warn('Элемент multimeterChart не найден');
    }

    const oscilloHistoryCtxElement = document.getElementById('oscilloHistoryChart');
    if (oscilloHistoryCtxElement) {
        const oscilloHistoryCtx = oscilloHistoryCtxElement.getContext('2d');
        window.oscilloHistoryChart = new Chart(oscilloHistoryCtx, {
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
    } else {
        console.warn('Элемент oscilloHistoryChart не найден');
    }

    const multiHistoryCtxElement = document.getElementById('multimeterHistoryChart');
    if (multiHistoryCtxElement) {
        const multiHistoryCtx = multiHistoryCtxElement.getContext('2d');
        window.multimeterHistoryChart = new Chart(multiHistoryCtx, {
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
    } else {
        console.warn('Элемент multimeterHistoryChart не найден');
    }

    for (let i = 1; i <= 4; i++) {
        const toggleElement = document.getElementById(`ch${i}Toggle`);
        if (toggleElement) {
            toggleElement.addEventListener('change', function() {
                if (window.oscilloscopeChart && window.oscilloscopeChart.data.datasets[i-1]) {
                    window.oscilloscopeChart.data.datasets[i-1].hidden = !this.checked;
                    window.oscilloscopeChart.update();
                }
            });
        }
    }

    const historyTab = document.getElementById('history-tab');
    if (historyTab) {
        historyTab.addEventListener('click', () => {
            console.log('Вкладка История активирована: здесь необходимо вызвать загрузку данных с сервера');

        });
    }

    const databaseTab = document.getElementById('database-tab');
    if (databaseTab) {
        databaseTab.addEventListener('click', () => {
            loadDatabaseData();
        });
    }

    console.log('Инициализация графиков завершена');
}


function initApp() {
    initWebSocket();
    initCharts();
    
    if (selectedTestNumber) {
        loadAvgMultimeterChart(selectedTestNumber);
    }
    
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
        websocket.send(JSON.stringify({
            action: 'get_multimeter_data'
        }));
    } else {
        setTimeout(requestLatestMultimeterData, 2000);
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
        if (document.getElementById('avgMultimeterChart')) {
            loadAvgMultimeterChart(this.value);
        }
    });
});
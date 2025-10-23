class SvgGauge {
  constructor(container, options) {
    this.container = container;
    this.minValue = options.minValue ?? 0;
    this.maxValue = options.maxValue ?? 100;
    this.unit = options.unit ?? '';
    this.title = options.title ?? 'Gauge';
    this.tickCount = options.tickCount ?? 10;
    this.dangerThreshold = options.dangerThreshold ?? this.maxValue * 0.85;
    this.warningThreshold = options.warningThreshold ?? this.maxValue * 0.7;
    this.colors = options.colors ?? {
      primary: '#448aff',
      danger: '#ff5252',
      warning: '#ffb142',
      success: '#4caf50',
      text: '#e0f7fa'
    };
    this.value = this.minValue;
    this.id = options.id ?? 'gauge';

    this._createGauge();
  }

  _createGauge() {
    this.container.innerHTML = `
      <div class="gauge-container" id="${this.id}">
        <div class="gauge-title">
          <svg class="gauge-icon" viewBox="0 0 24 24">${this._getIconPath()}</svg>
          <h2>${this.title}</h2>
        </div>
        <svg class="gauge-svg" viewBox="0 0 280 280" aria-label="${this.title}" role="img">
          <circle cx="140" cy="140" r="130" fill="url(#bgGradient)" filter="url(#shadow)" />
          <!-- Цветные зоны -->
          <path class="zone-normal" />
          <path class="zone-warning" />
          <path class="zone-danger" />
          <g class="ticks"></g>
          <!-- Стрелка, начинающаяся в центре круга -->
          <line class="needle" x1="140" y1="140" x2="140" y2="15" />
          <circle cx="140" cy="140" r="15" fill="url(#centerGradient)" stroke="#e0e0e0" stroke-width="1"/>
          <circle cx="140" cy="140" r="6" fill="#212121" />
          <text class="value-display" x="140" y="190" text-anchor="middle" fill="${this.colors.text}" font-size="32" font-weight="700" font-family="'Segoe UI', Tahoma, Geneva, Verdana, sans-serif" style="filter: drop-shadow(0 0 4px #448aff); user-select:none;"></text>
          <text class="unit-display" x="140" y="215" text-anchor="middle" fill="${this.colors.text}" font-size="18" font-family="'Segoe UI', Tahoma, Geneva, Verdana, sans-serif" opacity="0.7">${this.unit}</text>
          <text class="min-label" x="45" y="245" fill="#b2ebf2" font-size="14">${this.minValue}</text>
          <text class="max-label" x="235" y="245" fill="#b2ebf2" font-size="14" text-anchor="end">${this.maxValue}</text>
        </svg>
        <div class="min-max">
          <span>MIN: ${this.minValue}</span>
          <span>MAX: ${this.maxValue}</span>
        </div>
        <div class="status"><span class="led"></span><span class="status-text">НОРМАЛЬНЫЙ РЕЖИМ</span></div>
      </div>
    `;

    const svgElem = this.container.querySelector('svg.gauge-svg');
    const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
    defs.innerHTML = `
      <radialGradient id="bgGradient" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stop-color="#2c3b61"/>
        <stop offset="100%" stop-color="#1a243a"/>
      </radialGradient>
      <radialGradient id="centerGradient" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stop-color="#f5f5f5"/>
        <stop offset="100%" stop-color="#9e9e9e"/>
      </radialGradient>
      <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%" >
          <feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#000000" flood-opacity="0.7"/>
      </filter>
    `;
    svgElem.prepend(defs);

    this.svg = svgElem;
    this.needle = this.svg.querySelector('.needle');
    this.valueText = this.svg.querySelector('.value-display');
    this.statusText = this.container.querySelector('.status-text');
    this.statusLed = this.container.querySelector('.led');
    this.zonesNormal = this.svg.querySelector('.zone-normal');
    this.zonesWarning = this.svg.querySelector('.zone-warning');
    this.zonesDanger = this.svg.querySelector('.zone-danger');
    this.ticksGroup = this.svg.querySelector('.ticks');

    this._drawZones();
    this._drawTicks();
    this._updateNeedle(this.value);
  }

  _drawZones() {
    const startAngle = 135;
    const totalAngle = 270;
    const range = this.maxValue - this.minValue;

    const polarToCartesian = (cx, cy, radius, angleDegrees) => {
      const angleRadians = (angleDegrees - 90) * Math.PI / 180.0;
      return {
        x: cx + radius * Math.cos(angleRadians),
        y: cy + radius * Math.sin(angleRadians)
      };
    };

    const arcPath = (startAng, endAng, radius) => {
      const start = polarToCartesian(140, 140, radius, endAng);
      const end = polarToCartesian(140, 140, radius, startAng);
      const largeArcFlag = (endAng - startAng) <= 180 ? 0 : 1;
      return `M ${start.x} ${start.y} A ${radius} ${radius} 0 ${largeArcFlag} 0 ${end.x} ${end.y}`;
    };

    const dangerStartAng = startAngle + totalAngle * ((this.dangerThreshold - this.minValue) / range);
    const warningStartAng = startAngle + totalAngle * ((this.warningThreshold - this.minValue) / range);
    const endAng = startAngle + totalAngle;

    const radius = 120;

    this.zonesNormal.setAttribute('d', arcPath(startAngle, warningStartAng, radius));
    this.zonesWarning.setAttribute('d', arcPath(warningStartAng, dangerStartAng, radius));
    this.zonesDanger.setAttribute('d', arcPath(dangerStartAng, endAng, radius));
  }

  _drawTicks() {
    this.ticksGroup.innerHTML = '';
    const totalAngle = 270;
    const startAngle = 135;
    const minorTickLength = 8;
    const majorTickLength = 16;
    const ticksCount = this.tickCount;
    const range = this.maxValue - this.minValue;

    for (let i = 0; i <= ticksCount; i++) {
      const angle = startAngle + (totalAngle / ticksCount) * i;
      const largeTick = (i % 2 === 0);
      const tickLength = largeTick ? majorTickLength : minorTickLength;

      const outer = this._polarToCartesian(140, 140, 130, angle);
      const inner = this._polarToCartesian(140, 140, 130 - tickLength, angle);

      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute('x1', outer.x);
      line.setAttribute('y1', outer.y);
      line.setAttribute('x2', inner.x);
      line.setAttribute('y2', inner.y);
      line.setAttribute('stroke', '#a0bfff');
      line.setAttribute('stroke-width', largeTick ? '3' : '1.5');
      line.setAttribute('stroke-linecap', 'round');
      this.ticksGroup.appendChild(line);

      if (largeTick) {
        const labelPos = this._polarToCartesian(140, 140, 100, angle);
        const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
        text.setAttribute('x', labelPos.x);
        text.setAttribute('y', labelPos.y + 6);
        text.setAttribute('fill', '#c2d1ff');
        text.setAttribute('font-size', '14');
        text.setAttribute('text-anchor', 'middle');
        text.setAttribute('font-weight', '600');
        text.setAttribute('font-family', "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif");
        let displayVal = this.minValue + (range / ticksCount) * i;
        if (this.maxValue > 1000) displayVal = Math.round(displayVal / 1000) + 'k';
        else displayVal = Math.round(displayVal);
        text.textContent = displayVal;
        this.ticksGroup.appendChild(text);
      }
    }
  }

  _polarToCartesian(cx, cy, radius, angleInDegrees) {
    const angleInRadians = (angleInDegrees - 90) * Math.PI / 180.0;
    return {
      x: cx + (radius * Math.cos(angleInRadians)),
      y: cy + (radius * Math.sin(angleInRadians))
    };
  }

  _updateNeedle(value) {
    if (value < this.minValue) value = this.minValue;
    if (value > this.maxValue) value = this.maxValue;
    this.value = value;
    const range = this.maxValue - this.minValue;
    const totalAngle = 270;
    const startAngle = 135;

    const angle = startAngle + (value - this.minValue) / range * totalAngle;
    this.needle.style.transform = `rotate(${angle}deg)`;

    this.valueText.textContent = Math.round(value).toLocaleString();
    if (value >= this.dangerThreshold) {
      this.valueText.style.fill = this.colors.danger;
      this.valueText.style.filter = `drop-shadow(0 0 7px ${this.colors.danger})`;
      this.statusLed.style.backgroundColor = this.colors.danger;
      this.statusLed.style.boxShadow = `0 0 7px ${this.colors.danger}`;
      this.statusText.textContent = 'ОПАСНЫЙ РЕЖИМ';
    } else if (value >= this.warningThreshold) {
      this.valueText.style.fill = this.colors.warning;
      this.valueText.style.filter = `drop-shadow(0 0 7px ${this.colors.warning})`;
      this.statusLed.style.backgroundColor = this.colors.warning;
      this.statusLed.style.boxShadow = `0 0 7px ${this.colors.warning}`;
      this.statusText.textContent = 'ВЫСОКАЯ НАГРУЗКА';
    } else {
      this.valueText.style.fill = this.colors.text;
      this.valueText.style.filter = `drop-shadow(0 0 7px ${this.colors.primary})`;
      this.statusLed.style.backgroundColor = '#4caf50';
      this.statusLed.style.boxShadow = `0 0 7px #4caf50`;
      this.statusText.textContent = 'НОРМАЛЬНЫЙ РЕЖИМ';
    }
  }

  setValue(value) {
    this._updateNeedle(value);
  }

  _getIconPath() {
    return this.iconPath ?? `<path d="M13,2.05V5.08C16.39,5.57 19,8.47 19,12C19,12.9 18.82,13.75 18.5,14.54L21.12,16.07C21.68,14.83 22,13.45 22,12C22,6.82 18.05,2.55 13,2.05M12,19A7,7 0 0,1 5,12C5,8.47 7.61,5.57 11,5.08V2.05C5.94,2.55 2,6.81 2,12A10,10 0 0,0 12,22C15.3,22 18.23,20.39 20.05,17.91L17.45,16.38C16.17,18 14.21,19 12,19Z" />`;
  }
}

const icons = {
  rpm: `<path d="M13,2.05V5.08C16.39,5.57 19,8.47 19,12C19,12.9 18.82,13.75 18.5,14.54L21.12,16.07C21.68,14.83 22,13.45 22,12C22,6.82 18.05,2.55 13,2.05M12,19A7,7 0 0,1 5,12C5,8.47 7.61,5.57 11,5.08V2.05C5.94,2.55 2,6.81 2,12A10,10 0 0,0 12,22C15.3,22 18.23,20.39 20.05,17.91L17.45,16.38C16.17,18 14.21,19 12,19Z" />`,
  pressure: `<path d="M12 2C10.34 2 9 3.34 9 5v5.59c-.59-.36-1.07-.82-1.39-1.37-.52-.91-1.87-1.06-2.7-.23-.88.87-.23 2.23.62 2.7.72.38 1.39.69 2.11.98V19.5h2v-2.95c-.72-.23-1.55-.57-2.3-1.12-1.08-.79-1.61-2.48-1.05-3.9.42-1.06 1.53-1.92 2.98-1.92 1.82 0 3.3 1.5 3.3 3.32 0 1.26-.7 2.56-1.52 3.17-.72.53-1.41.75-2.12 1.09V20h2v-1.76c1-.3 1.97-.65 2.76-1.23.94-.74 1.52-2.07 1.52-3.32 0-2.37-2.08-4.3-4.61-4.3z"/>`,
  temperature: `<path d="M7 11a5 5 0 1 1 6 0v6a2 2 0 1 1-6 0v-6z" />`,
  thrust: `<path d="M12 2L15 8h-6l3-6zm0 20c-4.41 0-8-1.79-8-4v-3h16v3c0 2.21-3.59 4-8 4z" />`
};

function createGaugeWithIcon(containerId, options) {
  options.id = containerId;
  options.iconPath = options.iconPath || icons.rpm;
  const container = document.createElement('div');
  document.getElementById('dashboard').appendChild(container);
  return new SvgGauge(container, options);
}

// // Создаем все датчики
// const rpmGauge = createGaugeWithIcon('rpmGauge', {
//   minValue: 0, maxValue: 8000, unit: 'об/мин', tickCount: 16,
//   dangerThreshold: 6500, warningThreshold: 5000,
//   colors: { primary:'#448aff', danger:'#ff5252', warning:'#ffb142', success:'#4caf50', text:'#e0f7fa' },
//   title: 'Обороты двигателя',
//   iconPath: icons.rpm
// });

// const advanceGauge = createGaugeWithIcon('advanceGauge', {
//   minValue: 0, maxValue: 40, unit: 'град.', tickCount: 10,
//   dangerThreshold: 32, warningThreshold: 28,
//   colors: { primary:'#00bcd4', danger:'#ff5252', warning:'#ffb142', success:'#4caf50', text:'#e0f7fa' },
//   title: 'Угол опережения',
//   iconPath: icons.temperature
// });

// const dross = createGaugeWithIcon('drossGauge', {
//   minValue: 0, maxValue: 100, unit: '%', tickCount: 10,
//   dangerThreshold: 90, warningThreshold: 75,
//   colors: { primary:'#66bb6a', danger:'#d32f2f', warning:'#fbc02d', success:'#388e3c', text:'#e0f7fa' },
//   title: 'Положение дросселя',
//   iconPath: icons.thrust
// });

const thrust1 = createGaugeWithIcon('thrustGauge1', {
  minValue: 0, maxValue: 100, unit: 'кг', tickCount: 10,
  dangerThreshold: 90, warningThreshold: 75,
  colors: { primary:'#66bb6a', danger:'#d32f2f', warning:'#fbc02d', success:'#388e3c', text:'#e0f7fa' },
  title: 'Тяга',
  iconPath: icons.thrust
});

const temp600_1 = createGaugeWithIcon('temp600Gauge1', {
  minValue: 0, maxValue: 600, unit: '°C', tickCount: 12,
  dangerThreshold: 550, warningThreshold: 500,
  colors: { primary:'#ff7043', danger:'#b71c1c', warning:'#ffb300', success:'#2e7d32', text:'#e0f7fa' },
  title: 'Температура 600-1',
  iconPath: icons.temperature
});

const temp600_2 = createGaugeWithIcon('temp600Gauge2', {
  minValue: 0, maxValue: 600, unit: '°C', tickCount: 12,
  dangerThreshold: 550, warningThreshold: 500,
  colors: { primary:'#ff7043', danger:'#b71c1c', warning:'#ffb300', success:'#2e7d32', text:'#e0f7fa' },
  title: 'Температура 600-2',
  iconPath: icons.temperature
});

const tempNormal1 = createGaugeWithIcon('tempNormalGauge1', {
  minValue: 0, maxValue: 150, unit: '°C', tickCount: 10,
  dangerThreshold: 130, warningThreshold: 110,
  colors: { primary:'#29b6f6', danger:'#c62828', warning:'#ffa000', success:'#4caf50', text:'#e0f7fa' },
  title: 'Температура нормал 1',
  iconPath: icons.temperature
});

const tempNormal2 = createGaugeWithIcon('tempNormalGauge2', {
  minValue: 0, maxValue: 150, unit: '°C', tickCount: 10,
  dangerThreshold: 130, warningThreshold: 110,
  colors: { primary:'#29b6f6', danger:'#c62828', warning:'#ffa000', success:'#4caf50', text:'#e0f7fa' },
  title: 'Температура нормал 2',
  iconPath: icons.temperature
});

// const pressure1 = createGaugeWithIcon('pressureGauge1', {
//   minValue: 0, maxValue: 10, unit: 'бар', tickCount: 10,
//   dangerThreshold: 8.5, warningThreshold: 7,
//   colors: { primary:'#2196f3', danger:'#d32f2f', warning:'#fbc02d', success:'#388e3c', text:'#e0f7fa' },
//   title: 'Давление 1',
//   iconPath: icons.pressure
// });

// const pressure2 = createGaugeWithIcon('pressureGauge2', {
//   minValue: 0, maxValue: 10, unit: 'бар', tickCount: 10,
//   dangerThreshold: 8.5, warningThreshold: 7,
//   colors: { primary:'#2196f3', danger:'#d32f2f', warning:'#fbc02d', success:'#388e3c', text:'#e0f7fa' },
//   title: 'Давление 2',
//   iconPath: icons.pressure
// });

// const delayGauge = createGaugeWithIcon('delayGauge', {
//   minValue: 0, maxValue: 12, unit: 'V', tickCount: 12,
//   dangerThreshold: 10, warningThreshold: 7,
//   colors: { primary:'#ff4081', danger:'#ff5252', warning:'#ffb142', success:'#4caf50', text:'#e0f7fa' },
//   title: 'Питание',
//   iconPath: icons.temperature
// });

// const thrust2 = createGaugeWithIcon('thrustGauge2', {
//   minValue: 0, maxValue: 200, unit: 'Hv', tickCount: 10,
//   dangerThreshold: 90, warningThreshold: 75,
//   colors: { primary:'#66bb6a', danger:'#d32f2f', warning:'#fbc02d', success:'#388e3c', text:'#e0f7fa' },
//   title: 'Напряжение Hv',
//   iconPath: icons.thrust
// });

let ws = null;
let isConnected = false;
let reconnectAttempts = 0;
const maxReconnectAttempts = 10;
let lastDataTime = 0;

function connectWebSocket() {
  console.log('Attempting to connect to WebSocket...');
  
  try {
    ws = new WebSocket('ws://127.0.0.1:8767');
    
    ws.onopen = function() {
      console.log('WebSocket connected to ws://127.0.0.1:8767');
      isConnected = true;
      reconnectAttempts = 0;
      
      setTimeout(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({
            action: 'start_measurements'
          }));
          console.log('Sent start_measurements request');
        }
      }, 1000);
    };
    
    ws.onmessage = function(event) {
      try {
        const data = JSON.parse(event.data);
        console.log('WebSocket data received:', data);
        
        if (data.type === 'sensor_data') {
          lastDataTime = Date.now();
          console.log('Sensor data received:', data.data);
          updateGauges(data.data);
        } else if (data.type === 'status') {
          console.log('Status update:', data.data);
        } else if (data.type === 'multimeter') {
          console.log('Multimeter data:', data.data);
        }
      } catch (e) {
        console.error('Error parsing WebSocket message:', e);
      }
    };
    
    ws.onclose = function(event) {
      console.log('WebSocket disconnected. Code:', event.code, 'Reason:', event.reason);
      isConnected = false;
      
      if (reconnectAttempts < maxReconnectAttempts) {
        reconnectAttempts++;
        const delay = Math.min(1000 * reconnectAttempts, 10000); // Экспоненциальная задержка
        console.log(`Reconnecting in ${delay}ms (attempt ${reconnectAttempts}/${maxReconnectAttempts})`);
        setTimeout(connectWebSocket, delay);
      } else {
        console.error('Max reconnection attempts reached');
      }
    };
    
    ws.onerror = function(error) {
      console.error('WebSocket error:', error);
      isConnected = false;
    };
  } catch (error) {
    console.error('Error creating WebSocket:', error);
    isConnected = false;
  }
}

function updateGauges(sensorData) {
  console.log('Updating gauges with:', sensorData);
  
  if (sensorData.temp600_1 !== undefined) {
    console.log(`Setting temp600_1 to: ${sensorData.temp600_1}`);
    temp600_1.setValue(sensorData.temp600_1);
  }
  if (sensorData.temp600_2 !== undefined) {
    console.log(`Setting temp600_2 to: ${sensorData.temp600_2}`);
    temp600_2.setValue(sensorData.temp600_2);
  }
  if (sensorData.tempNormal1 !== undefined) {
    console.log(`Setting tempNormal1 to: ${sensorData.tempNormal1}`);
    tempNormal1.setValue(sensorData.tempNormal1);
  }
  if (sensorData.tempNormal2 !== undefined) {
    console.log(`Setting tempNormal2 to: ${sensorData.tempNormal2}`);
    tempNormal2.setValue(sensorData.tempNormal2);
  }
  if (sensorData.thrust1 !== undefined) {
    console.log(`Setting thrust1 to: ${sensorData.thrust1}`);
    thrust1.setValue(sensorData.thrust1);
  }
  
  console.log('Gauges updated with real data');
}

function checkConnectionStatus() {
  const now = Date.now();
  if (isConnected && now - lastDataTime > 10000) {
    console.log('No data received for 10 seconds');
  }
  
  requestAnimationFrame(checkConnectionStatus);
}

function requestData() {
  if (isConnected && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      action: 'get_uart_data'
    }));
    console.log('Requested UART data');
  }
}

document.addEventListener('DOMContentLoaded', function() {
  connectWebSocket();
  checkConnectionStatus();
  
  setInterval(requestData, 1000);
});
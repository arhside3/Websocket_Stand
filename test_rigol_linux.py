import numpy as np
import matplotlib.pyplot as plt
import time
import asyncio
import websockets
import json
import sys
import pyvisa
import os
from time import sleep
from collections import deque

WEBSOCKET_URI = "ws://localhost:8765"
VISA_RESOURCE = 'USB0::6833::1230::DS1ZC263402178::0::INSTR'

# --- НАСТРОЙКИ КАНАЛОВ ---
CHANNELS = [1, 2, 3, 4]  # Можно указать, какие каналы отображать (например, [1,2] или [1,2,3,4])
CHANNEL_COLORS = ['b', 'g', 'r', 'm']  # Цвета для каналов

# Цвета каналов как на Rigol
RIGOL_COLORS = ['#ffff00', '#00ffff', '#ff00ff', '#00aaff']  # CH1: yellow, CH2: cyan, CH3: magenta, CH4: light blue

# Буферы для хранения истории данных для режима непрерывной развертки
class SignalHistory:
    def __init__(self, max_points=10000):
        self.time_history = deque(maxlen=max_points)
        self.voltage_history = deque(maxlen=max_points)
        self.base_time = 0  # Базовое время для непрерывной шкалы
        self.sweep_duration = 0.024  # Продолжительность развертки в секундах (12 делений по 2мс)
    
    def add_data(self, time_data, voltage_data):
        if time_data is None or voltage_data is None or len(time_data) == 0 or len(voltage_data) == 0:
            return
            
        # Корректируем временные метки относительно непрерывной шкалы
        adjusted_time = [t + self.base_time for t in time_data]
        
        # Добавляем новые данные в историю
        self.time_history.extend(adjusted_time)
        self.voltage_history.extend(voltage_data)
        
        # Обновляем базовое время для следующего кадра
        last_time = adjusted_time[-1] if adjusted_time else self.base_time
        self.base_time = last_time + time_data[1] - time_data[0] if len(time_data) > 1 else last_time + 0.00002
        
        # Если буфер истории заполнен, сдвигаем базовое время, чтобы не было больших значений
        if len(self.time_history) >= self.time_history.maxlen * 0.9:
            min_time = self.time_history[0]
            time_shift = min_time + self.sweep_duration / 2
            self.time_history = deque([t - time_shift for t in self.time_history], maxlen=self.time_history.maxlen)
            self.base_time -= time_shift
    
    def get_data(self):
        return np.array(self.time_history), np.array(self.voltage_history)
    
    def clear(self):
        self.time_history.clear()
        self.voltage_history.clear()
        self.base_time = 0

# Глобальные буферы для каждого канала
signal_histories = {}

async def send_data_to_server(time_data, voltage_data):
    try:
        async with websockets.connect(WEBSOCKET_URI) as websocket:
            data = {
                'time': time_data.tolist(),
                'voltage': voltage_data.tolist()
            }
            message = json.dumps(data)
            await websocket.send(message)
            print("Данные отправлены на сервер.")
    except Exception as e:
        print(f"Ошибка отправки данных на сервер: {e}")

def plot_waveform(time_data, voltage_data, line=None):
    if line is None:
        # Создаем новый график
        plt.ion()  # Включаем интерактивный режим
        fig = plt.figure(figsize=(12, 6))
        ax = fig.add_subplot(111)
        line, = ax.plot(time_data, voltage_data, 'b-', linewidth=2)
        ax.set_title('Сигнал с осциллографа (режим реального времени)')
        ax.set_xlabel('Время (с)')
        ax.set_ylabel('Напряжение (В)')
        ax.grid(True)
        plt.tight_layout()
        plt.show(block=False)  # Показываем график сразу, не блокируя выполнение
    else:
        # Обновляем существующий график
        line.set_ydata(voltage_data)
        line.set_xdata(time_data)
        plt.gca().relim()
        plt.gca().autoscale_view()
    
    plt.draw()
    plt.pause(0.001)  # Небольшая пауза для обновления графика
    
    return line

def get_waveform_data(scope, channel):
    try:
        # Настраиваем параметры получения данных для выбранного канала
        scope.write(f":WAV:SOUR CHAN{channel}")
        scope.write(":WAV:MODE RAW")
        scope.write(":WAV:FORM BYTE")
        
        # Получаем преамбулу как бинарные данные
        scope.write(":WAV:PRE?")
        preamble_raw = scope.read_raw()
        
        # Декодируем преамбулу, игнорируя проблемные символы
        try:
            preamble = preamble_raw.decode('ascii', errors='ignore')
            preamble_parts = preamble.strip().split(',')
            if len(preamble_parts) >= 10:
                y_increment = float(preamble_parts[7])
                y_origin = float(preamble_parts[8])
                y_reference = 127  # Фиксированное значение для BYTE формата
                x_increment = float(preamble_parts[4])
                x_origin = float(preamble_parts[5])
                # --- ОТЛАДКА: выводим параметры ---
                print(f"CH{channel} PREAMBLE: {preamble}")
                print(f"CH{channel} y_increment={y_increment}, y_origin={y_origin}, y_reference={y_reference}, x_increment={x_increment}, x_origin={x_origin}")
            else:
                raise ValueError("Неверный формат преамбулы")
        except Exception as e:
            print(f"Ошибка при обработке преамбулы: {e}")
            y_increment = 0.4
            y_origin = 0
            y_reference = 127
            x_increment = 1e-6
            x_origin = -6e-4
        
        # Получаем данные осциллограммы
        scope.write(":WAV:DATA?")
        raw_data = scope.read_raw()
        
        if raw_data.startswith(b'#'):
            header_length = 2 + int(raw_data[1:2])
            data_length = int(raw_data[2:header_length])
            data = raw_data[header_length:header_length + data_length]
            waveform_data = np.frombuffer(data, dtype=np.uint8)
            if len(waveform_data) > 0:
                voltage_data = (waveform_data - y_reference) * y_increment + y_origin
                time_data = np.arange(len(voltage_data)) * x_increment + x_origin
                return time_data, voltage_data
            else:
                print(f"ПУСТЫЕ ДАННЫЕ для CH{channel}")
                raise ValueError("Не получены данные от осциллографа")
        else:
            print(f"Неверный формат данных от осциллографа для CH{channel}")
            raise ValueError("Неверный формат данных от осциллографа")
    except Exception as e:
        print(f"Ошибка получения данных с CH{channel}: {e}")
        return None, None

def draw_scope_overlay(ax, scope, active_channels):
    # Очищаем старые тексты
    [t.remove() for t in ax.texts]
    # Сбор параметров
    disp = get_display_params(scope)
    timeb = get_timebase_params(scope)
    trig = get_trigger_params(scope)
    ch_params = [get_channel_params(scope, ch) for ch in active_channels]
    # Формируем текст для вывода (безопасно через .get)
    overlay = []
    overlay.append(f"Display: {disp.get('Type','')}  Grid: {disp.get('Grid','')}  Bright: {disp.get('Brightness','')}")
    overlay.append(f"TimeBase: {timeb.get('Scale','')}  Offset: {timeb.get('Offset','')}  Mode: {timeb.get('Time Base','')}")
    overlay.append(f"Trigger: {trig.get('Mode','')} {trig.get('Type','')} {trig.get('Source','')} {trig.get('Level','')}V {trig.get('Slope','')} {trig.get('Status','')}")
    for idx, chp in enumerate(ch_params):
        overlay.append(f"CH{active_channels[idx]}: Scale {chp.get('Scale','')} Offset {chp.get('Offset','')} Probe {chp.get('Probe','')} Coupling {chp.get('Coupling','')} Unit {chp.get('Unit','')} BWLimit {chp.get('BW Limit','')} Invert {chp.get('Invert','')}")
    # Рисуем текст на графике (сверху)
    for i, line in enumerate(overlay):
        ax.text(1.01, 1.0 - i*0.07, line, transform=ax.transAxes, fontsize=9, va='top', ha='left', color='yellow', backgroundcolor='black')

def plot_waveforms(time_datas, voltage_datas, lines=None, ax=None, scope=None, active_channels=None):
    # --- Новый блок: вычисляем общий масштаб по Y для всех каналов ---
    y_min, y_max = None, None
    for v in voltage_datas:
        if v is not None and len(v) > 0:
            vmin, vmax = np.min(v), np.max(v)
            if y_min is None or vmin < y_min:
                y_min = vmin
            if y_max is None or vmax > y_max:
                y_max = vmax
    # Добавим небольшой запас
    if y_min is not None and y_max is not None:
        y_pad = (y_max - y_min) * 0.1 if (y_max - y_min) > 0 else 1
        y_min -= y_pad
        y_max += y_pad

    if lines is None or ax is None:
        plt.ion()
        fig = plt.figure(figsize=(12, 6))
        fig.patch.set_facecolor('black')
        ax = fig.add_subplot(111)
        ax.set_facecolor('black')
        lines = []
        for idx, (t, v) in enumerate(zip(time_datas, voltage_datas)):
            color = RIGOL_COLORS[idx % len(RIGOL_COLORS)]
            line, = ax.plot(t, v, color=color, linewidth=2.5, label=f'CH{active_channels[idx]}')
            lines.append(line)
        ax.set_title(' ', color='white')
        ax.set_xlabel('')
        ax.set_ylabel('')
        ax.grid(color='white', linewidth=1, alpha=0.3)
        ax.set_xticklabels([])
        ax.set_yticklabels([])
        ax.tick_params(axis='both', which='both', length=0, color='white')
        for idx, ch in enumerate(active_channels):
            fig.text(0.13 + idx*0.13, 0.08, f' {ch} ', color='black', backgroundcolor=RIGOL_COLORS[idx % len(RIGOL_COLORS)], fontsize=13, fontweight='bold', ha='center', va='center', bbox=dict(facecolor=RIGOL_COLORS[idx % len(RIGOL_COLORS)], edgecolor='none', boxstyle='round,pad=0.3'))
        plt.tight_layout(rect=[0,0.12,0.85,1])
        if y_min is not None and y_max is not None:
            ax.set_ylim(y_min, y_max)
        plt.show(block=False)
    else:
        for idx, (line, t, v) in enumerate(zip(lines, time_datas, voltage_datas)):
            line.set_xdata(t)
            line.set_ydata(v)
        if y_min is not None and y_max is not None:
            ax.set_ylim(y_min, y_max)
        ax.relim()
        ax.autoscale_view(scalex=True, scaley=False)
    # Overlay справа — только параметры активного канала
    if scope is not None and active_channels is not None:
        [t.remove() for t in ax.texts]
        chp = get_channel_params(scope, active_channels[0])
        overlay = [
            f"Связь: {chp.get('Coupling','')}",
            f"Огр.Полос: {chp.get('BW Limit','')}",
            f"Пробник: {chp.get('Probe','')}",
            f"Инверт: {chp.get('Invert','')}",
            f"В/дел: {chp.get('Volts/Div','')}",
            f"Ед.изм: {chp.get('Unit','')}",
        ]
        for i, line in enumerate(overlay):
            ax.text(1.01, 0.95 - i*0.12, line, transform=ax.transAxes, fontsize=13, va='top', ha='left', color='cyan', backgroundcolor='black', fontweight='bold')
    plt.draw()
    plt.pause(0.001)
    return lines, ax

def get_active_channels(scope, max_channels=4):
    active = []
    for ch in range(1, max_channels+1):
        try:
            resp = scope.query(f":CHAN{ch}:DISP?").strip()
            if resp in ('1', 'ON', 'on'):
                active.append(ch)
        except Exception as e:
            print(f"Ошибка при опросе CH{ch}: {e}")
    return active

def get_channel_params(scope, ch):
    params = {}
    try:
        params['Scale'] = scope.query(f':CHAN{ch}:SCAL?').strip()
        params['Offset'] = scope.query(f':CHAN{ch}:OFFS?').strip()
        params['Range'] = scope.query(f':CHAN{ch}:RANG?').strip()
        params['Delay'] = scope.query(f':CHAN{ch}:DELay?').strip()
        params['Coupling'] = scope.query(f':CHAN{ch}:COUP?').strip()
        params['BW Limit'] = scope.query(f':CHAN{ch}:BWL?').strip()
        params['Probe'] = scope.query(f':CHAN{ch}:PROB?').strip()
        params['Invert'] = scope.query(f':CHAN{ch}:INV?').strip()
        params['Volts/Div'] = scope.query(f':CHAN{ch}:VDIV?').strip() if hasattr(scope, 'query') else ''
        params['Unit'] = scope.query(f':CHAN{ch}:UNIT?').strip()
        params['Label'] = scope.query(f':CHAN{ch}:LAB?').strip()
    except Exception as e:
        params['error'] = str(e)
    return params

def get_trigger_params(scope):
    params = {}
    try:
        params['Status'] = scope.query(':TRIG:STAT?').strip()
        params['Mode'] = scope.query(':TRIG:MODE?').strip()
        params['Type'] = scope.query(':TRIG:TYPE?').strip()
        params['Source'] = scope.query(':TRIG:EDGE:SOUR?').strip()
        params['Level'] = scope.query(':TRIG:EDGE:LEV?').strip()
        params['Slope'] = scope.query(':TRIG:EDGE:SLOP?').strip()
        params['Coupling'] = scope.query(':TRIG:EDGE:COUP?').strip()
        params['Holdoff'] = scope.query(':TRIG:HOLD?').strip()
        params['NoiseRej'] = scope.query(':TRIG:NOIS?').strip()
    except Exception as e:
        params['error'] = str(e)
    return params

def get_timebase_params(scope):
    params = {}
    try:
        params['Time Base'] = scope.query(':TIM:MODE?').strip()
        params['Delayed'] = scope.query(':TIM:DEL:STAT?').strip()
        params['Scale'] = scope.query(':TIM:SCAL?').strip()
        params['Offset'] = scope.query(':TIM:OFFS?').strip()
    except Exception as e:
        params['error'] = str(e)
    return params

def get_display_params(scope):
    params = {}
    try:
        params['Type'] = scope.query(':DISP:TYPE?').strip()
        params['Persist Time'] = scope.query(':DISP:PERS?').strip()
        params['Intensity'] = scope.query(':DISP:INT?').strip()
        params['Grid'] = scope.query(':DISP:GRID?').strip()
        params['Brightness'] = scope.query(':DISP:BRIG?').strip()
    except Exception as e:
        params['error'] = str(e)
    return params

def smooth_data(data, window_size=5):
    """Сглаживание данных с помощью скользящего среднего"""
    if len(data) < window_size:
        return data
    
    # Используем np.convolve для скользящего среднего
    window = np.ones(window_size) / window_size
    smoothed = np.convolve(data, window, mode='same')
    # Копируем исходные значения на краях (для избегания краевых эффектов)
    smoothed[:window_size//2] = data[:window_size//2]
    smoothed[-window_size//2:] = data[-window_size//2:]
    return smoothed

def main():
    try:
        rm = pyvisa.ResourceManager('@py')
        print("Доступные ресурсы:", rm.list_resources())
        scope = rm.open_resource(VISA_RESOURCE)
        print(f"Подключено к осциллографу: {scope.query('*IDN?')}")
        try:
            active_channels = get_active_channels(scope)
            print(f"Активные каналы: {active_channels}")
            if not active_channels:
                print("Нет активных каналов! Включите хотя бы один канал на осциллографе.")
                return
            print("Нажмите Ctrl+C для остановки...")
            # Инициализация графика
            time_datas, voltage_datas = [], []
            for ch in active_channels:
                t, v = get_waveform_data(scope, ch)
                # Одинаковое сглаживание для всех каналов (если нужно)
                # v = smooth_data(v, window_size=5)
                time_datas.append(t)
                voltage_datas.append(v)
            lines, ax = plot_waveforms(time_datas, voltage_datas, None, None, scope, active_channels)
            # Основной цикл: real-time график + overlay
            last_overlay_update = time.time()
            while True:
                try:
                    time_datas, voltage_datas = [], []
                    for ch in active_channels:
                        t, v = get_waveform_data(scope, ch)
                        # v = smooth_data(v, window_size=5)
                        time_datas.append(t)
                        voltage_datas.append(v)
                    # Обновляем только линии (без overlay)
                    lines, ax = plot_waveforms(time_datas, voltage_datas, lines, ax, None, None)
                    # Overlay обновляем раз в 1 сек
                    if time.time() - last_overlay_update > 1.0:
                        draw_scope_overlay(ax, scope, active_channels)
                        plt.draw()
                        last_overlay_update = time.time()
                    plt.pause(0.001)
                    time.sleep(0.05)
                except Exception as e:
                    print(f"Ошибка в цикле измерений: {e}")
                    time.sleep(0.2)
                    continue
        except KeyboardInterrupt:
            print("\nТест остановлен пользователем")
        finally:
            scope.close()
            print("Соединение с осциллографом закрыто.")
    except Exception as e:
        print(f"Ошибка в main: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

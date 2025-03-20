import pyvisa
import numpy as np
import matplotlib.pyplot as plt
import time
import asyncio
import websockets
import json
import argparse

WEBSOCKET_URI = "ws://localhost:8765"

# Парсинг аргументов командной строки
parser = argparse.ArgumentParser(description="Управление осциллографом")
parser.add_argument("--channel", type=int, default=1, help="Номер канала (1-4)")
parser.add_argument("--volts_per_div", type=float, default=1.0, help="Вольт на деление")
parser.add_argument("--time_per_div", type=str, default="100us", help="Время на деление")
parser.add_argument("--trigger_level", type=float, default=1.0, help="Уровень триггера (В)")
args = parser.parse_args()

def connect_to_oscilloscope(resource_manager, resource_string):
    try:
        oscilloscope = resource_manager.open_resource(resource_string)
        print(f"Подключено к осциллографу: {oscilloscope.query('*IDN?')}")
        return oscilloscope
    except pyvisa.errors.VisaIOError as e:
        print(f"Ошибка подключения к осциллографу: {e}")
        return None

def setup_oscilloscope(oscilloscope, channel, volts_per_div, time_per_div, trigger_level):
    try:
        oscilloscope.write(f':CHAN{channel}:DISP ON') 
        oscilloscope.write(f':CHAN{channel}:VOLT/DIV {volts_per_div:.2f}')  
        oscilloscope.write(f':TIM:SCAL {time_per_div}')  
        oscilloscope.write(':TIM:MODE NORM')
        oscilloscope.write(':TRIG:MODE EDGE')
        oscilloscope.write(f':TRIG:EDGE:SOUR CHAN{channel}')
        oscilloscope.write(':TRIG:EDGE:SLOP POS')
        oscilloscope.write(f':TRIG:LEV {trigger_level:.2f}')  
        print("Осциллограф настроен.")
    except pyvisa.errors.VisaIOError as e:
        print(f"Ошибка настройки осциллографа: {e}")

def get_waveform_data(oscilloscope, channel):
    try:
        oscilloscope.write(f':WAV:SOUR CHAN{channel}')
        oscilloscope.write(':WAV:MODE RAW')
        oscilloscope.write(':WAV:FORM BYTE')

        preamble = oscilloscope.query(':WAV:PRE?')
        print("Преамбула:", preamble)

        preamble_values = preamble.split(',')
        y_increment = float(preamble_values[7])
        y_origin = float(preamble_values[8])
        x_increment = float(preamble_values[4])
        x_origin = float(preamble_values[5])

        oscilloscope.write(':WAV:DATA?')
        raw_data = oscilloscope.read_raw()

        waveform_data = np.frombuffer(raw_data[11:], dtype=np.uint8)
        voltage_data = (waveform_data - y_origin) * y_increment
        time_data = np.arange(0, len(voltage_data) * x_increment, x_increment) + x_origin

        return time_data, voltage_data
    except pyvisa.errors.VisaIOError as e:
        print(f"Ошибка получения данных: {e}")
        return None, None

async def send_data_to_server(time_data, voltage_data):
    try:
        async with websockets.connect(WEBSOCKET_URI) as websocket:
            amplitude = np.max(voltage_data) - np.min(voltage_data)
            mean_voltage = np.mean(voltage_data)
            rms_voltage = np.sqrt(np.mean(voltage_data**2))
            max_voltage = np.max(voltage_data)
            min_voltage = np.min(voltage_data)
            frequency = 1 / (time_data[1] - time_data[0])  
            period = 1 / frequency
            overshoot = np.max(voltage_data) - max_voltage  

            data = {
                'time': time_data.tolist(),
                'voltage': voltage_data.tolist(),
                'amplitude': amplitude,
                'mean_voltage': mean_voltage,
                'rms_voltage': rms_voltage,
                'max_voltage': max_voltage,
                'min_voltage': min_voltage,
                'frequency': frequency,
                'period': period,
                'overshoot': overshoot
            }
            message = json.dumps(data)
            await websocket.send(message)
            print("Данные отправлены на сервер.")
    except Exception as e:
        print(f"Ошибка отправки данных на сервер: {e}")

def plot_waveform(time_data, voltage_data):
    plt.figure(figsize=(10, 6))
    plt.plot(time_data, voltage_data)
    plt.title('Сигнал с осциллографа')
    plt.xlabel('Время (с)')
    plt.ylabel('Напряжение (В)')
    plt.grid()
    plt.show()

def main():
    rm = pyvisa.ResourceManager()
    print("Доступные ресурсы:", rm.list_resources())

    resource_string = 'USB::0x1AB1::0x04CE::DS1ZC263402178::INSTR'
    oscilloscope = connect_to_oscilloscope(rm, resource_string)

    if oscilloscope:
        setup_oscilloscope(oscilloscope, args.channel, args.volts_per_div, args.time_per_div, args.trigger_level)

        time.sleep(2)  
        time_data, voltage_data = get_waveform_data(oscilloscope, args.channel)

        if time_data is not None and voltage_data is not None:
            asyncio.run(send_data_to_server(time_data, voltage_data))
            plot_waveform(time_data, voltage_data)  
        else:
            print("Нет данных для отправки на сервер.")

        oscilloscope.close()
        print("Соединение с осциллографом закрыто.")
    else:
        print("Не удалось подключиться к осциллографу.")

if __name__ == "__main__":
    main()

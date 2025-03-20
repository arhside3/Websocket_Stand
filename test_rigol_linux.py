import pyvisa
import numpy as np
import matplotlib.pyplot as plt
import time
import asyncio
import websockets
import json

WEBSOCKET_URI = "ws://localhost:8765"


def connect_to_oscilloscope(resource_manager, resource_string):
    try:
        oscilloscope = resource_manager.open_resource(resource_string)
        print(f"Подключено к осциллографу: {oscilloscope.query('*IDN?')}")
        return oscilloscope
    except pyvisa.errors.VisaIOError as e:
        print(f"Ошибка подключения к осциллографу: {e}")
        return None

def setup_oscilloscope(oscilloscope, channel=1, volts_per_div=1.0, time_per_div='100us'):
    try:

        oscilloscope.write(f':CHAN{channel}:DISP ON') 
        oscilloscope.write(f':CHAN{channel}:VOLT/DIV {volts_per_div}')

        oscilloscope.write(f':TIM:SCAL {time_per_div}')
        oscilloscope.write(':TIM:MODE NORM')


        oscilloscope.write(':TRIG:MODE EDGE')
        oscilloscope.write(f':TRIG:EDGE:SOUR CHAN{channel}')
        oscilloscope.write(':TRIG:EDGE:SLOP POS')
        oscilloscope.write(':TRIG:LEV 1.0')

        print("Осциллограф настроен.")
    except pyvisa.errors.VisaIOError as e:
        print(f"Ошибка настройки осциллографа: {e}")

def get_waveform_data(oscilloscope, channel=1):
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

            data = {
                'time': time_data.tolist(),
                'voltage': voltage_data.tolist()
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
        setup_oscilloscope(oscilloscope, channel=1, volts_per_div=0.5, time_per_div='100us')

        time.sleep(2)  # Даем время осциллографу захватить сигнал
        time_data, voltage_data = get_waveform_data(oscilloscope, channel=1)

        if time_data is not None and voltage_data is not None:
            asyncio.run(send_data_to_server(time_data, voltage_data))
            plot_waveform(time_data, voltage_data)  # Построение графика сигнала 
            
        else:
            print("Нет данных для отправки на сервер.")

        # Закрытие соединения с осциллографом 
        oscilloscope.close()
        print("Соединение с осциллографом закрыто.")
    else:
        print("Не удалось подключиться к осциллографу.")

if __name__ == "__main__":
    main()

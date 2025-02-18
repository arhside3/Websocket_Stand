import pyvisa
import numpy as np
import matplotlib.pyplot as plt
import time
import asyncio
import websockets
import json

# WebSocket settings
WEBSOCKET_URI = "ws://localhost:8765"

# Функция для подключения к осциллографу
def connect_to_oscilloscope(resource_manager, resource_string):
    try:
        oscilloscope = resource_manager.open_resource(resource_string)
        print(f"Подключено к осциллографу: {oscilloscope.query('*IDN?')}")
        return oscilloscope
    except pyvisa.errors.VisaIOError as e:
        print(f"Ошибка подключения к осциллографу: {e}")
        return None

# Функция для настройки осциллографа
def setup_oscilloscope(oscilloscope, channel=1, volts_per_div=1.0, time_per_div='100us'):
    try:
        # Настройка канала
        oscilloscope.write(f':CHAN{channel}:DISP ON')  # Включаем отображение канала
        oscilloscope.write(f':CHAN{channel}:VOLT/DIV {volts_per_div}')  # Устанавливаем вольты на деление

        # Настройка временной базы
        oscilloscope.write(f':TIM:SCAL {time_per_div}')  # Устанавливаем время на деление
        oscilloscope.write(':TIM:MODE NORM')  # Устанавливаем режим временной развертки

        # Настройка триггера
        oscilloscope.write(':TRIG:MODE EDGE')  # Устанавливаем режим триггера EDGE
        oscilloscope.write(f':TRIG:EDGE:SOUR CHAN{channel}')  # Устанавливаем источник триггера на канал
        oscilloscope.write(':TRIG:EDGE:SLOP POS')  # Устанавливаем положительный фронт триггера
        oscilloscope.write(':TRIG:LEV 1.0')  # Устанавливаем уровень триггера

        print("Осциллограф настроен.")
    except pyvisa.errors.VisaIOError as e:
        print(f"Ошибка настройки осциллографа: {e}")

# Функция для получения данных с осциллографа
def get_waveform_data(oscilloscope, channel=1):
    try:
        # Подготовка к получению данных
        oscilloscope.write(f':WAV:SOUR CHAN{channel}')  # Устанавливаем источник данных на указанный канал
        oscilloscope.write(':WAV:MODE RAW')  # Устанавливаем режим данных RAW
        oscilloscope.write(':WAV:FORM BYTE')  # Устанавливаем формат данных BYTE

        # Запрашиваем преамбулу
        preamble = oscilloscope.query(':WAV:PRE?')
        print("Преамбула:", preamble)

        # Извлекаем значения из преамбулы
        preamble_values = preamble.split(',')
        y_increment = float(preamble_values[7])
        y_origin = float(preamble_values[8])
        x_increment = float(preamble_values[4])
        x_origin = float(preamble_values[5])

        # Запрашиваем данные
        oscilloscope.write(':WAV:DATA?')

        # Читаем данные в виде строки
        raw_data = oscilloscope.read_raw()

        # Преобразуем данные в массив NumPy
        waveform_data = np.frombuffer(raw_data[11:], dtype=np.uint8)  # Отбрасываем заголовок

        # Преобразование данных в напряжение
        voltage_data = (waveform_data - y_origin) * y_increment

        # Временные метки для оси X
        time_data = np.arange(0, len(voltage_data) * x_increment, x_increment) + x_origin

        return time_data, voltage_data
    except pyvisa.errors.VisaIOError as e:
        print(f"Ошибка получения данных: {e}")
        return None, None

# Функция для отправки данных на WebSocket сервер
async def send_data_to_server(time_data, voltage_data):
    try:
        async with websockets.connect(WEBSOCKET_URI) as websocket:
            # Формируем JSON сообщение с данными
            data = {
                'time': time_data.tolist(),  # Преобразуем в список для JSON
                'voltage': voltage_data.tolist()  # Преобразуем в список для JSON
            }

            # Преобразуем в JSON строку
            message = json.dumps(data)

            # Отправляем сообщение на сервер
            await websocket.send(message)
            print("Данные отправлены на сервер.")

    except Exception as e:
        print(f"Ошибка отправки данных на сервер: {e}")

# Функция для отображения графика сигнала
def plot_waveform(time_data, voltage_data):
    plt.figure(figsize=(10, 6))
    plt.plot(time_data, voltage_data)
    plt.title('Сигнал с осциллографа')
    plt.xlabel('Время (с)')
    plt.ylabel('Напряжение (В)')
    plt.grid()
    plt.show()

# Основная функция
def main():
    # Инициализация ResourceManager
    rm = pyvisa.ResourceManager()
    print("Доступные ресурсы:", rm.list_resources())

    resource_string = 'USB0::0x1AB1::0x04CE::DS1ZC263402178::INSTR'

    # Подключение к осциллографу
    oscilloscope = connect_to_oscilloscope(rm, resource_string)

    if oscilloscope:
        # Настройка осциллографа
        setup_oscilloscope(oscilloscope, channel=1, volts_per_div=0.5, time_per_div='100us')

        # Получение данных
        time.sleep(2)  # Даем время осциллографу захватить сигнал
        time_data, voltage_data = get_waveform_data(oscilloscope, channel=1)

        # Отправка данных на сервер и построение графика 
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

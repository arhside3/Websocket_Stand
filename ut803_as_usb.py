import serial
import time

# Настройки последовательного порта
PORT = '/dev/ttyUSB0'  # Замените на ваш порт (например, COM3 на Windows)
BAUD_RATE = 19200
TIMEOUT = 1

# Функция для декодирования пакета
def decode_packet(packet):
    """
    Декодирует пакет данных от мультиметра.
    Предполагается, что пакет имеет длину 22 байта.
    """
    if len(packet) != 22:
        return None  # Пропускаем пакеты неправильной длины

    # Проверяем маркеры начала и конца пакета
    if packet[0] != 0xB0 or packet[-1] != 0x8A:
        return None  # Пропускаем пакеты с неправильными маркерами

    # Извлекаем данные (пример для ASCII-кодировки)
    value = packet[1:4].decode('ascii', errors='ignore')  # Значение измерения
    unit = packet[4]  # Единица измерения (например, вольты, амперы)
    # Дополнительные данные (если нужно)
    additional_data = packet[5:-2]

    return {
        'value': value,
        'unit': unit,
        'additional_data': additional_data.hex()
    }

# Основная функция
def main():
    # Открываем последовательный порт
    try:
        ser = serial.Serial(PORT, BAUD_RATE, timeout=TIMEOUT)
        print(f"Подключено к {PORT} на скорости {BAUD_RATE} бод.")
    except serial.SerialException as e:
        print(f"Ошибка подключения к порту: {e}")
        return

    try:
        while True:
            # Читаем пакет данных (22 байта)
            packet = ser.read(22)
            if packet:
                # Декодируем пакет
                decoded_data = decode_packet(packet)
                if decoded_data:
                    print(f"Значение: {decoded_data['value']}, "
                          f"Единица: {decoded_data['unit']}, "
                          f"Дополнительные данные: {decoded_data['additional_data']}")
                else:
                    print(f"Получен некорректный пакет: {packet.hex()}")
            else:
                print("Ожидание данных...")

            # Пауза между чтениями
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("Программа завершена пользователем.")
    finally:
        ser.close()
        print("Последовательный порт закрыт.")

# Запуск программы
if __name__ == "__main__":
    main()
import serial
import time

COM_PORT = 'ttyUSB0'
BAUD_RATE = 19200
TIMEOUT = 1

try:
    ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=TIMEOUT)
    print(f"Подключено к {COM_PORT} на скорости {BAUD_RATE} бод.")
except serial.SerialException as e:
    print(f"Ошибка подключения к {COM_PORT}: {e}")
    exit()

try:
    while True:
        if ser.in_waiting > 0:
            data = ser.read(ser.in_waiting)
            print(f"Полученные данные: {data.hex()}")
        time.sleep(0.1)
except KeyboardInterrupt:
    print("Программа завершена пользователем.")
finally:
    ser.close()
    print("Соединение с COM-портом закрыто.")
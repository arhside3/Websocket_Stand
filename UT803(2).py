import serial
import serial.tools.list_ports
import time

TARGET_VID = "067B"
TARGET_PID = "2303"

def find_com_port(vid, pid):
    """
    Находит COM-порт по VID и PID.
    """
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if vid.lower() in port.hwid.lower() and pid.lower() in port.hwid.lower():
            return port.device
    return None

com_port = find_com_port(TARGET_VID, TARGET_PID)
if com_port is None:
    print(f"Устройство с VID={TARGET_VID} и PID={TARGET_PID} не найдено.")
    exit()

print(f"Найдено устройство на порту: {com_port}")

BAUD_RATE = 19200
TIMEOUT = 1

# Инициализация COM-порта
try:
    ser = serial.Serial(com_port, BAUD_RATE, timeout=TIMEOUT)
    print(f"Подключено к {com_port} на скорости {BAUD_RATE} бод.")
except serial.SerialException as e:
    print(f"Ошибка подключения к {com_port}: {e}")
    exit()

try:
    while True:
        print("Ожидание данных...")
        if ser.in_waiting > 0:
            print("Данные обнаружены!")
            data = ser.read(ser.in_waiting)
            print(f"Полученные данные: {data.hex()}")
        time.sleep(0.1)
except KeyboardInterrupt:
    print("Программа завершена пользователем.")
except Exception as e:
    print(f"Ошибка: {e}")
finally:
    ser.close()
    print("Соединение с COM-портом закрыто.")
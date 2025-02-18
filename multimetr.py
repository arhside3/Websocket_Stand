import asyncio
import websockets
import base64
import serial
import time

SERIAL_PORT = 'COM1'  # Измените на ваш реальный порт
BAUD_RATE = 9600

async def send_data_to_multimeter():
    """Запрос данных с мультиметра UNI-T UT803."""
    with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1) as ser:
        time.sleep(2)  # Ждем установления соединения
        
        # Включаем режим RS232 (если необходимо)
        ser.write(b'RS232\r\n')  # Замените на реальную команду для активации RS232
        time.sleep(1)

        # Отправляем команду на запрос текущих измерений
        ser.write(b'MEASURE?\r\n')  # Попробуйте разные команды, если эта не работает

        time.sleep(0.5)  # Задержка перед чтением ответа

        # Читаем ответ от мультиметра
        response = ser.readline().decode().strip()  # Читаем строку и декодируем ее
        return response

async def send_binary_data():
    url = "ws://localhost:8765"

    async with websockets.connect(url) as websocket:
        for _ in range(10):
            # Получаем данные с мультиметра
            multimeter_data = await send_data_to_multimeter()
            print(f"Данные с мультиметра: {multimeter_data}")

            if multimeter_data:
                # Кодируем и отправляем данные через WebSocket
                encoded_data = base64.b64encode(multimeter_data.encode('utf-8')).decode('utf-8')
                print(f"Отправка данных на WebSocket: {encoded_data}")
                await websocket.send(encoded_data)
            else:
                print("Нет данных для отправки.")

            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(send_binary_data())

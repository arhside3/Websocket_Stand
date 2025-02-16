import asyncio
import websockets
import base64
import numpy as np
import zlib

def calculate_checksum(data):
    """Вычисляет контрольную сумму с использованием zlib.crc32."""
    checksum = zlib.crc32(data) & 0xffffffff
    return checksum.to_bytes(4, 'big')

async def send_binary_data():
    url = "ws://localhost:8765"

    async with websockets.connect(url) as websocket:
        for _ in range(10):
            binary_data = np.random.randint(1, 101, size=64).astype(np.uint8).tobytes()
            checksum = calculate_checksum(binary_data)
            data_with_checksum = binary_data + checksum

            encoded_data = base64.b64encode(data_with_checksum).decode('utf-8')
            print(f"Отправка данных: {encoded_data}")
            print("Отправляемые данные:", binary_data)
            print("Контрольная сумма:", checksum)
            print(f"Отправляемые данные (длина): {len(data_with_checksum)}")

            await websocket.send(encoded_data)

            response = await websocket.recv()
            decoded_response = base64.b64decode(response)

            print(f"Декодированные данные (длина): {len(decoded_response)}")

            if len(decoded_response) == 68:
                received_data = decoded_response[:-4]
                received_checksum = decoded_response[-4:]

                expected_checksum = calculate_checksum(received_data)
                if expected_checksum == received_checksum:
                    decoded_numbers = list(received_data)
                    print("Правильные данные с сервера:", decoded_numbers)
                else:
                    print("Ошибка: контрольная сумма не совпадает.")
            else:
                print("Сломанные данные с сервера")

            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(send_binary_data())

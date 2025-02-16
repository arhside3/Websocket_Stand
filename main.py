import asyncio
import websockets
import base64
from sqlalchemy import create_engine, Column, Integer, LargeBinary
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import zlib

DATABASE_URL = 'sqlite:///my_database.db'
TABLE_NAME = 'raw_data'

engine = create_engine(DATABASE_URL, echo=False)
Base = declarative_base()

class RawData(Base):
    __tablename__ = TABLE_NAME
    id = Column(Integer, primary_key=True)
    data = Column(LargeBinary)

Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)

def calculate_checksum(data):
    """Вычисляет контрольную сумму с использованием zlib.crc32."""
    checksum = zlib.crc32(data) & 0xffffffff  # Получаем 32-битное значение
    return checksum.to_bytes(4, 'big')  # Возвращаем контрольную сумму в виде 4 байтов

async def handle_websocket(websocket):
    print(f"Пользователь подключился: {websocket.remote_address}")
    session = Session()
    try:
        async for message in websocket:
            try:
                decoded_data = base64.b64decode(message)
                print("Декодированные данные:", decoded_data)
                print(f"Декодированные данные (длина): {len(decoded_data)}")

                if len(decoded_data) == 68:  # 64 байта данных + 4 байта контрольной суммы
                    received_data = decoded_data[:-4]  # Извлекаем данные
                    received_checksum = decoded_data[-4:]  # Извлекаем контрольную сумму

                    expected_checksum = calculate_checksum(received_data)
                    if expected_checksum == received_checksum:
                        raw_data = RawData(data=received_data)
                        session.add(raw_data)
                        session.commit()
                        print("Данные сохранились в базу данных")

                        await websocket.send(base64.b64encode(decoded_data).decode('utf-8'))
                    else:
                        print("Ошибка: контрольная сумма не совпадает.")
                else:
                    print("Ошибка: некорректная длина данных.")

            except Exception as e:
                session.rollback()
                print(f"Ошибка декодировки данных: {e}")
            finally:
                pass

    except websockets.exceptions.ConnectionClosedError:
        print("Произошел Дисконект")
    except Exception as e:
        print(f"Описание ошибки: {e}")
    finally:
        session.close()
        print(f"Произошел Дисконект: {websocket.remote_address}")

# Запуск WebSocket-сервера
async def main():
    print("Создание таблицы(если ее нету)...")
    print("WebSocket server started at ws://localhost:8765")
    async with websockets.serve(handle_websocket, 'localhost', 8765):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())

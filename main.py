import asyncio
import websockets
import json
from sqlalchemy import create_engine, Column, Integer, LargeBinary, Float, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.sqlite import JSON

DATABASE_URL = 'sqlite:///my_database.db'
TABLE_NAME = 'waveform_data'

engine = create_engine(DATABASE_URL, echo=False)
Base = declarative_base()

class WaveformData(Base):
    __tablename__ = TABLE_NAME
    id = Column(Integer, primary_key=True)
    time_data = Column(JSON)  # Use JSON type for lists of numbers
    voltage_data = Column(JSON) # Use JSON type for lists of numbers

Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

async def handle_websocket(websocket):
    print(f"Пользователь подключился: {websocket.remote_address}")
    session = Session()
    try:
        async for message in websocket:
            try:
                data = json.loads(message)  # Parse JSON message
                print("Полученные данные:", data)

                # Extract time and voltage data
                time_data = data.get('time')
                voltage_data = data.get('voltage')

                # Check if the data is valid
                if time_data is not None and voltage_data is not None:
                    # Create a new WaveformData object
                    waveform_data = WaveformData(time_data=time_data, voltage_data=voltage_data)
                    session.add(waveform_data)
                    session.commit()
                    print("Данные сохранены в базу данных")
                else:
                    print("Ошибка: Некорректный формат данных.")

            except json.JSONDecodeError as e:
                session.rollback()
                print(f"Ошибка декодирования JSON: {e}")
            except Exception as e:
                session.rollback()
                print(f"Ошибка обработки данных: {e}")
            finally:
                pass

    except websockets.exceptions.ConnectionClosedError:
        print("Произошел Дисконнект")
    except Exception as e:
        print(f"Описание ошибки: {e}")
    finally:
        session.close()
        print(f"Произошел Дисконнект: {websocket.remote_address}")

# Запуск WebSocket-сервера
async def main():
    print("Создание таблицы(если ее нету)...")
    print("WebSocket server started at ws://localhost:8765")
    async with websockets.serve(handle_websocket, 'localhost', 8765):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())

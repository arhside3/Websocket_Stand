import asyncio
import websockets
import json
import numpy as np
from sqlalchemy import create_engine, Column, Integer, JSON, Float
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
    time_data = Column(JSON)
    voltage_data = Column(JSON)
    amplitude = Column(Float)
    mean_voltage = Column(Float)
    rms_voltage = Column(Float)
    max_voltage = Column(Float)
    min_voltage = Column(Float)
    frequency = Column(Float)
    phase_shift = Column(Float)
    period = Column(Float)
    overshoot = Column(Float)

Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

async def handle_websocket(websocket):
    print(f"Пользователь подключился: {websocket.remote_address}")
    session = Session()
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                print("Полученные данные:", data)

                time_data = np.array(data.get('time'))
                voltage_data = np.array(data.get('voltage'))

                if time_data is not None and voltage_data is not None:
                    amplitude = np.max(voltage_data) - np.min(voltage_data)
                    mean_voltage = np.mean(voltage_data)
                    rms_voltage = np.sqrt(np.mean(voltage_data**2))
                    max_voltage = np.max(voltage_data)
                    min_voltage = np.min(voltage_data)
                    frequency = 1 / (time_data[1] - time_data[0])
                    period = 1 / frequency
                    overshoot = np.max(voltage_data) - max_voltage

                    phase_shift = 0

                    waveform_data = WaveformData(
                        time_data=data.get('time'),
                        voltage_data=data.get('voltage'),
                        amplitude=amplitude,
                        mean_voltage=mean_voltage,
                        rms_voltage=rms_voltage,
                        max_voltage=max_voltage,
                        min_voltage=min_voltage,
                        frequency=frequency,
                        phase_shift=phase_shift,
                        period=period,
                        overshoot=overshoot
                    )
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

async def main():
    print("Создание таблицы(если ее нету)...")
    print("WebSocket server started at ws://localhost:8765")
    async with websockets.serve(handle_websocket, 'localhost', 8765):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())

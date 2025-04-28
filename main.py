import asyncio
import websockets
import json
import numpy as np
from sqlalchemy import create_engine, Column, Integer, JSON, Float, String, DateTime, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.sqlite import JSON
from datetime import datetime

DATABASE_URL = 'sqlite:///my_database.db'

engine = create_engine(DATABASE_URL, echo=False)
Base = declarative_base()

class OscilloscopeData(Base):
    __tablename__ = 'осциллограф'
    id = Column(Integer, primary_key=True)
    timestamp = Column(String)
    channel = Column(String)
    voltage = Column(Float)
    frequency = Column(Float)
    raw_data = Column(JSON)


class MultimeterData(Base):
    __tablename__ = 'мультиметр'
    id = Column(Integer, primary_key=True)
    timestamp = Column(String)
    value = Column(String)  
    unit = Column(String)
    mode = Column(String)
    range_str = Column(String)
    measure_type = Column(String)
    raw_data = Column(JSON)


def setup_database():
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS multimeter_data"))
        conn.execute(text("DROP TABLE IF EXISTS oscilloscope_data"))
        conn.execute(text("DROP TABLE IF EXISTS waveform_data"))
        conn.commit()
    

    Base.metadata.create_all(engine)

setup_database()
Session = sessionmaker(bind=engine)


measurement_counter = 0
expected_measurements = 0

async def handle_websocket(websocket):
    print(f"Client connected: {websocket.remote_address}")
    session = Session()
    global measurement_counter, expected_measurements
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                print("Received data:", data)
                
                if "expected_measurements" in data:
                    expected_measurements = data["expected_measurements"]
                    measurement_counter = 0  
                    print(f"Expected measurements set to: {expected_measurements}")
                    continue
                
                current_time = datetime.now()
                timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                
                if 'time' in data and 'voltage' in data:
                    oscilloscope_data = OscilloscopeData(
                        timestamp=timestamp,
                        channel="CH1",  
                        voltage=round(np.mean(data['voltage']), 2),
                        frequency=round(1.0 / (data['time'][1] - data['time'][0]) if len(data['time']) > 1 else 0, 2),
                        raw_data=data
                    )
                    session.add(oscilloscope_data)
                    session.commit()
                    print(f"Saved oscilloscope data")
                else:
                    value_str = data.get('value', '0')
                    if value_str == "OL":
                        value = "OL"  
                    else:

                        value = value_str
                    
                    multimeter_data = MultimeterData(
                        timestamp=timestamp,
                        value=value,  
                        unit=data.get('unit', ''),
                        mode=data.get('mode', ''),
                        range_str=data.get('range_str', ''),
                        measure_type=data.get('measure_type', ''),
                        raw_data=data
                    )
                    session.add(multimeter_data)
                    session.commit()
                    
                    measurement_counter += 1
                    print(f"Saved multimeter data. Measurement {measurement_counter} of {expected_measurements}")
                    
                    if expected_measurements > 0 and measurement_counter >= expected_measurements:
                        print(f"Достигнуто ожидаемое количество измерений: {expected_measurements}")
                        await websocket.send(json.dumps({"status": "complete", "count": measurement_counter}))
                
            except json.JSONDecodeError as e:
                session.rollback()
                print(f"JSON decode error: {e}")
            except Exception as e:
                session.rollback()
                print(f"Error processing data: {e}")
                
    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected")
    except Exception as e:
        print(f"Error handling websocket: {e}")
    finally:
        session.close()
        print(f"Client disconnected: {websocket.remote_address}")

async def main():
    print("WebSocket server started at ws://localhost:8765")
    async with websockets.serve(handle_websocket, 'localhost', 8765):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())

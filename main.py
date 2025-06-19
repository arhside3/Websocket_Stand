import asyncio
import websockets
import json
import numpy as np
import pyvisa
import threading
import os
import sys
from sqlalchemy import create_engine, Column, Integer, JSON, Float, String, DateTime, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.dialects.sqlite import JSON
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import locale
import traceback
import time
import serial
import hid
from serial.tools import list_ports
import subprocess
import signal
import concurrent.futures
from concurrent.futures import ProcessPoolExecutor
import re

if sys.platform.startswith('win'):
    locale.setlocale(locale.LC_ALL, 'Russian_Russia.UTF-8')
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

DATABASE_URL = 'sqlite:///my_database.db'
WEBSOCKET_PORT = 8767
HTTP_PORT = 8080

oscilloscope_lock = threading.Lock()
no_save_oscilloscope = True

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

is_data_collection_active = False

is_multimeter_collection_active = False

session_lock = asyncio.Lock()

async_engine = create_engine(DATABASE_URL, echo=False, future=True)
async_session = sessionmaker(bind=async_engine, expire_on_commit=False)

class MultimeterMeasurement:
    def __init__(self, value, unit, mode, range_str, measure_type, raw_data, timestamp):
        self.value = value
        self.unit = unit
        self.mode = mode
        self.range_str = range_str
        self.measure_type = measure_type
        self.raw_data = raw_data
        self.timestamp = timestamp

def save_oscilloscope_data(data, force_save=False):
    """Сохраняет данные осциллографа в базу данных, если нужно"""
    global is_data_collection_active
    if not is_data_collection_active and not force_save:
        return True
        
    session = Session()
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        if data.get('channels'):
            for channel_name, channel_data in data['channels'].items():
                if 'voltage' in channel_data and 'time' in channel_data:
                    db_record = OscilloscopeData(
                        timestamp=timestamp,
                        channel=channel_name,
                        voltage=float(np.mean(channel_data['voltage'])),
                        frequency=0.0,
                        raw_data=channel_data
                    )
                    session.add(db_record)
        elif 'voltage' in data and 'time' in data:
            voltages = data['voltage']
            if isinstance(voltages, list) and len(voltages) > 0:
                if isinstance(voltages[0], list):
                    for i, voltage_arr in enumerate(voltages):
                        db_record = OscilloscopeData(
                            timestamp=timestamp,
                            channel=f"CH{i+1}",
                            voltage=float(np.mean(voltage_arr)),
                            frequency=0.0,
                            raw_data=data
                        )
                        session.add(db_record)
                else:
                    db_record = OscilloscopeData(
                        timestamp=timestamp,
                        channel="CH1",
                        voltage=float(np.mean(voltages)),
                        frequency=0.0,
                        raw_data=data
                    )
                    session.add(db_record)
        session.commit()
        print("Данные осциллографа сохранены в БД")
        return True
    except Exception as e:
        session.rollback()
        print(f"Ошибка сохранения данных осциллографа в БД: {e}")
        traceback.print_exc()
        return False
    finally:
        session.close()

def save_multimeter_data(data, force_save=False):
    """Сохраняет данные мультиметра в базу данных"""
    return True

def get_oscilloscope_data_from_db(limit=100):
    """Возвращает последние данные осциллографа из БД"""
    session = Session()
    try:
        results = session.query(OscilloscopeData).order_by(OscilloscopeData.id.desc()).limit(limit).all()
        
        data = []
        for row in results:
            data.append({
                'id': row.id,
                'timestamp': row.timestamp,
                'channel': row.channel,
                'voltage': row.voltage,
                'frequency': row.frequency
            })
        
        return data
    except Exception as e:
        print(f"Ошибка получения данных осциллографа из БД: {e}")
        traceback.print_exc()
        return []
    finally:
        session.close()

def get_multimeter_data_from_db(limit=100):
    """Возвращает последние данные мультиметра из БД"""
    session = Session()
    try:
        results = session.query(MultimeterData).order_by(MultimeterData.id.desc()).limit(limit).all()
        
        data = []
        for row in results:
            data.append({
                'id': row.id,
                'timestamp': row.timestamp,
                'value': row.value,
                'unit': row.unit,
                'mode': row.mode,
                'range_str': row.range_str,
                'measure_type': row.measure_type
            })
        
        return data
    except Exception as e:
        print(f"Ошибка получения данных мультиметра из БД: {e}")
        traceback.print_exc()
        return []
    finally:
        session.close()

def get_oscilloscope_history(period='hour'):
    session = Session()
    try:
        now = datetime.now()
        if period == 'test':
            results = session.query(OscilloscopeData).order_by(OscilloscopeData.id.desc()).limit(10).all()
            
            if not results:
                print("Нет данных осциллографа в БД для тестового графика, генерируем тестовые данные")
                timestamps = []
                test_channels = {
                    "CH1": {"name": "CH1", "values": []},
                    "CH2": {"name": "CH2", "values": []},
                    "CH3": {"name": "CH3", "values": []},
                    "CH4": {"name": "CH4", "values": []}
                }
                
                phase_shift = np.random.random() * np.pi
                amplitude_shift = np.random.random() * 0.5 + 0.75
                
                for i in range(10):
                    timestamp = (now - timedelta(seconds=i*5)).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    timestamps.append(timestamp)
                    
                    test_channels["CH1"]["values"].append(
                        3.0 * amplitude_shift * np.sin(i/3.0 + phase_shift) + 3.0 + np.random.random() * 0.2 - 0.1
                    )
                    
                    test_channels["CH2"]["values"].append(
                        2.0 * amplitude_shift * np.cos(i/2.0 + phase_shift) + 2.0 + np.random.random() * 0.2 - 0.1
                    )
                    
                    test_channels["CH3"]["values"].append(
                        (i % 5) * 0.5 * amplitude_shift + 1.0 + np.random.random() * 0.1 - 0.05
                    )
                    
                    test_channels["CH4"]["values"].append(
                        4.0 if (i + int(phase_shift * 5)) % 4 < 2 else 1.0 + np.random.random() * 0.2 - 0.1
                    )
                
                return {
                    'timestamps': list(reversed(timestamps)),
                    'channels': list(test_channels.values())
                }
            
            timestamps = []
            channels = {}
            for row in reversed(results):
                timestamps.append(row.timestamp)
                if row.channel not in channels:
                    channels[row.channel] = {
                        'name': row.channel,
                        'values': []
                    }
                channels[row.channel]['values'].append(row.voltage)
            return {
                'timestamps': timestamps,
                'channels': list(channels.values())
            }
        else:
            if period == 'hour':
                start_time = now - timedelta(hours=1)
            elif period == 'day':
                start_time = now - timedelta(days=1)
            elif period == 'week':
                start_time = now - timedelta(weeks=1)
            else:
                start_time = now - timedelta(hours=1)
            start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
            results = session.query(OscilloscopeData).filter(OscilloscopeData.timestamp >= start_time_str).order_by(OscilloscopeData.id.asc()).all()
            timestamps = []
            voltages = []
            for row in results:
                timestamps.append(row.timestamp)
                voltages.append(row.voltage)
            return {
                    'timestamps': timestamps,
                    'voltages': voltages
            }
    except Exception as e:
            print(f"Ошибка получения истории осциллографа: {e}")
            return {'timestamps': [], 'voltages': []}
    finally:
        session.close()

def get_multimeter_history(period='hour'):
    """Возвращает исторические данные мультиметра для графика"""
    session = Session()
    try:
        now = datetime.now()
        if period == 'hour':
            start_time = now - timedelta(hours=1)
        elif period == 'day':
            start_time = now - timedelta(days=1)
        elif period == 'week':
            start_time = now - timedelta(weeks=1)
        else:
            start_time = now - timedelta(hours=1)

        start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")

        results = session.query(MultimeterData)\
            .filter(MultimeterData.timestamp >= start_time_str)\
            .order_by(MultimeterData.timestamp.asc())\
            .all()

        timestamps = []
        values = []
        raw_data_list = []
        
        for row in results:
            try:
                value = float(row.value) if row.value != 'OL' else None
                if value is not None:
                    timestamps.append(row.timestamp)
                    values.append(value)
                    raw_data_list.append(row.raw_data if row.raw_data else None)
            except (ValueError, TypeError):
                continue
        
        if not timestamps:
            print("Нет данных мультиметра в БД за указанный период")
            return {'timestamps': [], 'values': [], 'raw_data': []}
            
        print(f"Получено {len(timestamps)} точек данных мультиметра из БД")
        return {
            'timestamps': timestamps,
            'values': values,
            'raw_data': raw_data_list
        }
    except Exception as e:
        print(f"Ошибка получения истории мультиметра: {e}")
        traceback.print_exc()
        return {'timestamps': [], 'values': [], 'raw_data': []}
    finally:
        session.close()

active_websockets = set()

class OscilloscopeVisualizer:
    def __init__(self):
        self.rm = None
        self.oscilloscope = None
        self.active_channels = []
        self.running = True
        self.connected = False
        
        self.channel_colors = {1: 'yellow', 2: 'cyan', 3: 'magenta', 4: '#00aaff'}

    def connect_to_oscilloscope(self):
        try:
            if self.oscilloscope is not None:
                try:
                    idn = self.oscilloscope.query("*IDN?")
                    if idn:
                        self.connected = True
                        return True
                except Exception:
                    try:
                        self.oscilloscope.close()
                    except Exception:
                        pass
                    self.oscilloscope = None
                    self.connected = False
                    
            self.rm = pyvisa.ResourceManager('@py')
                
            resources = self.rm.list_resources()
            print("Доступные устройства:", resources)
            
            rigol_address = None
            for resource in resources:
                if 'USB' in resource and ('DS1' in resource or 'DS2' in resource):
                    rigol_address = resource
                    break
            
            if rigol_address:
                print("Подключение к осциллографу по адресу:", rigol_address)
                try:
                    self.oscilloscope = self.rm.open_resource(rigol_address)
                    self.oscilloscope.timeout = 20000
                    self.oscilloscope.write_termination = '\n'
                    self.oscilloscope.read_termination = '\n'
                    self.oscilloscope.chunk_size = 1024
                    
                    idn = self.oscilloscope.query("*IDN?")
                    print("Подключено к осциллографу:", idn)
                    
                    self.oscilloscope.write(":WAV:FORM BYTE")
                    self.oscilloscope.write(":WAV:MODE NORM")
                    self.oscilloscope.write(":WAV:POIN 1200")
                    time.sleep(0.5)
                    
                    self.connected = True
                    return True
                except pyvisa.errors.VisaIOError as e:
                    print(f"Ошибка при подключении к осциллографу: {e}")
                    if self.oscilloscope:
                        try:
                            self.oscilloscope.close()
                        except Exception:
                            pass
                    self.oscilloscope = None
                    self.connected = False
                    return False
            else:
                print("Осциллограф Rigol не найден")
                self.connected = False
                return False
                
        except Exception as e:
            print("Ошибка при подключении к осциллографу:", e)
            traceback.print_exc()
            self.connected = False
            return False

    def update_active_channels(self):
        """Обновляет список активных каналов"""
        self.active_channels = []
        try:
            if not self.connected or not self.oscilloscope:
                return
                
            for channel in range(1, 5):
                try:
                    if self.oscilloscope.query(f":CHAN{channel}:DISP?").strip() == '1':
                        self.active_channels.append(channel)
                except pyvisa.errors.VisaIOError as e:
                    print(f"Ошибка при проверке активности канала {channel}: {e}")
                    continue
        except Exception as e:
            print(f"Ошибка при обновлении списка активных каналов: {e}")

    def get_channel_data(self, channel):
        """Получает данные с канала осциллографа (синхронная версия)"""
        try:
            if not self.connected or not self.oscilloscope:
                return None, None
            
            with oscilloscope_lock:
                try:
                    self.oscilloscope.write(f":WAV:SOUR CHAN{channel}")
                    time.sleep(0.05)
                    
                    volt_scale = float(self.oscilloscope.query(f":CHAN{channel}:SCAL?"))
                    volt_offset = float(self.oscilloscope.query(f":CHAN{channel}:OFFS?"))
                    time_scale = float(self.oscilloscope.query(":TIM:SCAL?"))
                    
                    self.oscilloscope.write(":WAV:DATA?")
                    time.sleep(0.05)
                    raw_data = self.oscilloscope.read_raw()
                    
                    if raw_data:
                        data_start = raw_data.find(b'#')
                        if data_start != -1:
                            header_end = raw_data.find(b'\n', data_start)
                            if header_end != -1:
                                raw_data = raw_data[header_end + 1:]
                        
                        try:
                            voltage_data = np.frombuffer(raw_data, dtype=np.uint8)
                            voltage_data = (voltage_data - 128) * (volt_scale / 25) + volt_offset
                            
                            step = 2
                            voltage_data = voltage_data[::step]
                            time_data = np.linspace(-6 * time_scale, 6 * time_scale, len(voltage_data))
                            
                            return time_data, voltage_data
                        except Exception as e:
                            print(f"Ошибка обработки данных осциллографа: {e}")
                            return None, None
                    
                    return None, None
                except pyvisa.errors.VisaIOError as e:
                    print(f"Ошибка при получении данных с канала {channel}: {e}")
                    if 'VI_ERROR_TMO' in str(e):
                        self.connected = False
                    return None, None
                
        except Exception as e:
            print(f"Ошибка при получении данных с канала {channel}: {e}")
            return None, None

    async def get_channel_data_async(self, channel):
        """Асинхронная обертка для получения данных с канала"""
        loop = asyncio.get_event_loop()
        time_data, voltage_data = await loop.run_in_executor(
            None, lambda: self.get_channel_data(channel)
        )
        return time_data, voltage_data

    def get_channel_settings(self, channel):
        """Получает настройки канала"""
        try:
            if not self.connected or not self.oscilloscope:
                return {"error": "Oscilloscope not connected"}
                
            with oscilloscope_lock:
                try:
                    volts_div = float(self.oscilloscope.query(f":CHAN{channel}:SCAL?"))
                    offset = float(self.oscilloscope.query(f":CHAN{channel}:OFFS?"))
                    coupling = self.oscilloscope.query(f":CHAN{channel}:COUP?").strip()
                    display = self.oscilloscope.query(f":CHAN{channel}:DISP?").strip()
                    
                    return {
                        "volts_div": volts_div,
                        "offset": offset,
                        "coupling": coupling,
                        "display": display
                    }
                except pyvisa.errors.VisaIOError as e:
                    print(f"Ошибка при получении настроек канала {channel}: {e}")
                    if 'VI_ERROR_TMO' in str(e) or 'VI_ERROR_INP_PROT_VIOL' in str(e):
                        self.connected = False
                    return {"error": str(e)}
        except Exception as e:
            print(f"Ошибка при получении настроек канала {channel}: {e}")
            return {"error": str(e)}

    async def get_channel_settings_async(self, channel):
        """Асинхронная обертка для получения настроек канала"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.get_channel_settings(channel))

    async def get_oscilloscope_data(self):
        """Получает данные со всех активных каналов"""
        if not self.connected:
            self.connect_to_oscilloscope()
            if not self.connected:
                return {"error": "Осциллограф не подключен"}
                
        try:
            self.update_active_channels()
            
            oscilloscope_data = {
                "time_base": 0.001,
                "time_offset": 0.0,
                "trigger_level": 0.0,
                "channels": {}
            }

            try:
                if self.connected and self.oscilloscope:
                    oscilloscope_data["time_base"] = float(self.oscilloscope.query(":TIM:SCAL?"))
                    oscilloscope_data["time_offset"] = float(self.oscilloscope.query(":TIM:OFFS?"))
                    oscilloscope_data["trigger_level"] = float(self.oscilloscope.query(":TRIG:EDGE:LEV?"))
            except Exception as e:
                print(f"Ошибка при получении общих настроек осциллографа: {e}")
                self.connected = False
                return {"error": "Ошибка получения настроек осциллографа"}
            
            for channel in range(1, 5):
                settings = self.get_channel_settings(channel)
                if 'error' not in settings:
                    is_active = settings.get('display') == '1'
                    
                    if is_active:
                        time_data, voltage_data = self.get_channel_data(channel)
                        if time_data is not None and voltage_data is not None:
                            oscilloscope_data["channels"][f"CH{channel}"] = {
                                "time": time_data.tolist(),
                                "voltage": voltage_data.tolist(),
                                "settings": settings,
                                "color": self.channel_colors[channel]
                            }
                    else:
                        oscilloscope_data["channels"][f"CH{channel}"] = {
                            "settings": settings,
                            "color": self.channel_colors[channel]
                        }
                
            if not any('voltage' in channel_data for channel_data in oscilloscope_data["channels"].values()):
                return {"error": "Нет активных каналов осциллографа"}
                
            return oscilloscope_data
        except Exception as e:
            print(f"Ошибка при получении данных с осциллографа: {e}")
            traceback.print_exc()
            return {"error": "Ошибка получения данных с осциллографа"}

class CustomHTTPRequestHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.error_message_format = '''
        <html>
            <head>
                <meta charset="utf-8">
                <title>Error %(code)d</title>
            </head>
            <body>
                <h1>Error %(code)d</h1>
                <p>%(message)s</p>
            </body>
        </html>
        '''
        super().__init__(*args, **kwargs)

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        try:
            parsed_path = urlparse(self.path)
            path = parsed_path.path
            query = parse_qs(parsed_path.query)

            if path == '/':
                self.serve_file('index.html', 'text/html')
            elif path.endswith('.js'):
                self.serve_file(path[1:], 'text/javascript')
            elif path.endswith('.css'):
                self.serve_file(path[1:], 'text/css')
            elif path.endswith('.html'):
                self.serve_file(path[1:], 'text/html')
            elif path == '/db/oscilloscope':
                page = int(query.get('page', ['1'])[0])
                per_page = int(query.get('per_page', ['50'])[0])
                self.send_json_response(get_oscilloscope_data_paginated(page=page, per_page=per_page))
            elif path == '/db/multimeter':
                page = int(query.get('page', ['1'])[0])
                per_page = int(query.get('per_page', ['50'])[0])
                self.send_json_response(get_multimeter_data_paginated(page=page, per_page=per_page))
            elif path == '/history/oscilloscope':
                period = query.get('period', ['hour'])[0]
                self.send_json_response(get_oscilloscope_history(period))
            elif path == '/history/multimeter':
                period = query.get('period', ['hour'])[0]
                self.send_json_response(get_multimeter_history(period))
            else:
                self.send_error(404, "File not found")
        except Exception as e:
            print(f"Ошибка при обработке GET запроса: {e}")
            traceback.print_exc()
            self.send_error(500, "Internal server error")

    def do_POST(self):
        """Обработка POST запросов для сохранения данных в БД"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            if self.path == '/save_data':
                try:
                    data = json.loads(post_data.decode('utf-8'))
                    data_type = data.get('type')
                    data_content = data.get('data', {})
                    
                    success = False
                    if data_type == 'oscilloscope':
                        success = save_oscilloscope_data(data_content)
                    elif data_type == 'multimeter':
                        success = save_multimeter_data(data_content)
                    
                    self.send_json_response({'success': success})
                except json.JSONDecodeError:
                    print("Ошибка декодирования JSON данных")
                    self.send_error(400, "Invalid JSON data")
                except Exception as e:
                    print(f"Ошибка при обработке POST данных: {e}")
                    traceback.print_exc()
                    self.send_error(500, "Internal server error")
            else:
                self.send_error(404, "Endpoint not found")
        except Exception as e:
            print(f"Ошибка при обработке POST запроса: {e}")
            traceback.print_exc()
            self.send_error(500, "Internal server error")

    def send_json_response(self, data):
        """Отправляет JSON-ответ"""
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(data).encode('utf-8'))
        except Exception as e:
            print(f"Ошибка при отправке JSON ответа: {e}")
            self.send_error(500, "Internal server error")
    
    def serve_file(self, filename, content_type):
        try:
            with open(filename, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', f'{content_type}; charset=utf-8')
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404, "File not found")
        except Exception as e:
            print(f"Ошибка при отправке файла {filename}: {e}")
            self.send_error(500, "Internal server error")

    def log_message(self, format, *args):
        pass

global_visualizer = None
global_multimeter = None
last_multimeter_values = {}

is_measurement_active = True
is_multimeter_running = True
is_oscilloscope_running = True
oscilloscope_task = None
multimeter_task = None

def run_lua_script_sync(script_name: str) -> dict:
    """Synchronous version of run_lua_script that runs in a separate process"""
    try:
        env = os.environ.copy()
        env['LUA_PATH'] = '?.lua;' + env.get('LUA_PATH', '')
        
        process = subprocess.Popen(
            ['lua', script_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            preexec_fn=os.setsid
        )
        
        try:
            stdout, stderr = process.communicate(timeout=300)
            return {
                'success': True,
                'output': stdout.decode('utf-8'),
                'error': stderr.decode('utf-8')
            }
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            return {
                'success': False,
                'error': 'Script execution timed out after 5 minutes'
            }
            
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

async def run_lua_script(script_name: str) -> dict:
    """Asynchronous wrapper for run_lua_script_sync"""
    loop = asyncio.get_running_loop()
    with ProcessPoolExecutor() as pool:
        return await loop.run_in_executor(pool, run_lua_script_sync, script_name)

def run_lua_script_stream(script_name: str, on_line, websocket=None, loop=None) -> bool:
    try:
        env = os.environ.copy()
        env['LUA_PATH'] = '?.lua;' + env.get('LUA_PATH', '')
        process = subprocess.Popen(
            ['lua', script_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            preexec_fn=os.setsid,
            bufsize=1,
            universal_newlines=True
        )
        multimeter_regex = re.compile(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\] ([\d.]+) В (DC|AC) AUTO \[Вольтметр\]')
        for line in process.stdout:
            on_line(line.rstrip())
            if websocket and loop:
                match = multimeter_regex.search(line)
                if match:
                    data = {
                        'timestamp': match.group(1),
                        'value': match.group(2),
                        'unit': 'В',
                        'mode': match.group(3),
                        'range_str': 'AUTO',
                        'measure_type': 'Вольтметр'
                    }
                    asyncio.run_coroutine_threadsafe(
                        websocket.send(json.dumps({'type': 'multimeter', 'data': data})),
                        loop
                    )
        process.wait()
        return process.returncode == 0
    except Exception as e:
        on_line(f"[ERROR] {e}")
        return False

async def run_lua_script_stream_async(script_name, websocket):
    loop = asyncio.get_running_loop()
    def send_line(line):
        asyncio.run_coroutine_threadsafe(
            websocket.send(json.dumps({'type': 'lua_output', 'line': line})),
            loop
        )
    success = await loop.run_in_executor(None, run_lua_script_stream, script_name, send_line, websocket, loop)
    await websocket.send(json.dumps({'type': 'lua_status', 'success': success}))

async def run_lua_test_parallel_async(script_name, websocket):
    """Запускает main.lua, разбирает вывод и отправляет данные по типу устройства в WebSocket"""
    process = await asyncio.create_subprocess_exec(
        'lua', script_name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )
    try:
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            decoded = line.decode('utf-8').rstrip()
            if decoded.startswith('[OSC]'):
                await websocket.send(json.dumps({'type': 'oscilloscope', 'line': decoded[5:].lstrip()}))
            elif decoded.startswith('[MULT]'):
                await websocket.send(json.dumps({'type': 'multimeter', 'line': decoded[6:].lstrip()}))
            else:
                await websocket.send(json.dumps({'type': 'lua_output', 'line': decoded}))
        returncode = await process.wait()
        await websocket.send(json.dumps({'type': 'lua_status', 'success': returncode == 0}))
    except Exception as e:
        await websocket.send(json.dumps({'type': 'lua_status', 'success': False, 'error': str(e)}))

async def handle_websocket(websocket):
    global global_multimeter, global_visualizer, is_measurement_active
    print("Клиент подключен к WebSocket")
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                action = data.get('action')
                
                if action == 'run_lua':
                    script_name = data.get('script', 'main.lua')
                    print(f"Запуск Lua скрипта: {script_name}")
                    await run_lua_test_parallel_async(script_name, websocket)
                
                elif action == 'start_measurements':
                    is_measurement_active = True
                    if global_visualizer and not global_visualizer.connected:
                        global_visualizer.connect_to_oscilloscope()
                    if not global_multimeter:
                        global_multimeter = UT803Reader()
                        global_multimeter.connect_serial() or global_multimeter.connect_hid()
                    await websocket.send(json.dumps({
                        'type': 'status',
                        'data': {'status': 'measurements_started'}
                    }))
                
                elif action == 'stop_measurements':
                    is_measurement_active = False
                    if global_visualizer and global_visualizer.oscilloscope:
                        try:
                            global_visualizer.oscilloscope.close()
                        except Exception as e:
                            print(f"Ошибка при разрыве соединения с осциллографом: {e}")
                        global_visualizer.oscilloscope = None
                        global_visualizer.connected = False
                        print("Соединение с осциллографом разорвано.")
                    if global_multimeter:
                        try:
                            global_multimeter.disconnect()
                        except Exception as e:
                            print(f"Ошибка при разрыве соединения с мультиметром: {e}")
                        global_multimeter = None
                        print("Соединение с мультиметром разорвано.")
                    await websocket.send(json.dumps({
                        'type': 'status',
                        'data': {'status': 'measurements_stopped'}
                    }))
                
                elif action == 'get_multimeter_data':
                    asyncio.create_task(handle_get_multimeter_data(websocket, id(websocket)))
                elif action == 'get_multimeter_history':
                    period = data.get('period', 'hour')
                    asyncio.create_task(send_multimeter_history(websocket, period))
                elif action == 'get_oscilloscope_data':
                    asyncio.create_task(handle_get_oscilloscope_data(websocket))
                
            except json.JSONDecodeError:
                pass
            except Exception as e:
                print(f"Ошибка обработки WebSocket сообщения: {e}")
                traceback.print_exc()
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        print(f"Ошибка WebSocket соединения: {e}")
        traceback.print_exc()
    finally:
        if id(websocket) in last_multimeter_values:
            del last_multimeter_values[id(websocket)]
        if websocket in active_websockets:
            active_websockets.remove(websocket)

async def update_oscilloscope_data():
    try:
        if not global_visualizer or not global_visualizer.connected:
            return
        oscilloscope_data = await global_visualizer.get_oscilloscope_data()
        if oscilloscope_data and 'error' not in oscilloscope_data:
            disconnected_clients = []
            send_tasks = []
            for websocket in active_websockets:
                try:
                    if hasattr(websocket, 'open') and websocket.open:
                        send_task = asyncio.create_task(
                            websocket.send(json.dumps(oscilloscope_data))
                        )
                        send_tasks.append(send_task)
                    else:
                        disconnected_clients.append(websocket)
                except Exception as e:
                    print(f"Ошибка подготовки отправки данных клиенту: {e}")
                    disconnected_clients.append(websocket)
            for client in disconnected_clients:
                if client in active_websockets:
                    active_websockets.remove(client)
            if send_tasks:
                await asyncio.wait(send_tasks, return_when=asyncio.ALL_COMPLETED)
    except Exception as e:
        print(f"Ошибка при получении данных с осциллографа: {e}")
        traceback.print_exc()

async def run_oscilloscope():
    """Функция для работы с осциллографом"""
    global global_visualizer, active_websockets, is_oscilloscope_running, is_measurement_active
    oscilloscope_interval = 0.1
    last_oscilloscope_update = 0
    
    while True:
        if not is_oscilloscope_running:
            print("Опрос осциллографа остановлен.")
            break
        try:
            current_time = time.time()
            if active_websockets and global_visualizer and global_visualizer.connected and \
               (current_time - last_oscilloscope_update) >= oscilloscope_interval and \
               is_measurement_active:
                last_oscilloscope_update = current_time
                await update_oscilloscope_data()
        except Exception as e:
            print(f"Ошибка в цикле осциллографа: {e}")
            await asyncio.sleep(0.1)
        await asyncio.sleep(0.01)

async def run_multimeter():
    """Асинхронно запускает чтение мультиметра в отдельном потоке и отправляет данные клиентам"""
    global global_multimeter, active_websockets, is_multimeter_running, is_measurement_active, last_live_multimeter_data
    
    print("Инициализация мультиметра (threaded)")
    
    try:
        rs232_port = None
        for port in list_ports.comports():
            if "USB" in port.device:
                rs232_port = port.device
                break
        if not rs232_port:
            print("Не удалось найти порт RS232 для мультиметра")
            return
            
        global_multimeter = UT803Reader()
        if global_multimeter.connect_serial():
            print(f"Мультиметр успешно подключен через RS232")
        elif global_multimeter.connect_hid():
            print(f"Мультиметр успешно подключен через HID")
        else:
            print("Не удалось подключиться к мультиметру")
            return
            
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            while is_multimeter_running:
                if not is_measurement_active:
                    await asyncio.sleep(0.1)
                    continue
                measurement, human_readable = await loop.run_in_executor(
                    pool,
                    lambda: global_multimeter.read_serial() if global_multimeter.serial_port else global_multimeter.read_hid()
                )
                
                if measurement and human_readable:
                    last_live_multimeter_data = measurement
                    print(f"Отправка данных мультиметра: {measurement}")
                    if active_websockets:
                        await send_to_all_websocket_clients({
                            "type": "multimeter",
                            "data": measurement
                        })
                await asyncio.sleep(0.02)
        if global_multimeter:
            global_multimeter.disconnect()
            global_multimeter = None
        print("Опрос мультиметра остановлен.")
    except Exception as e:
        print(f"Ошибка при инициализации мультиметра: {e}")
        if global_multimeter:
            global_multimeter.disconnect()
            global_multimeter = None
        print("Опрос мультиметра остановлен.")

def save_multimeter_data(data, force_save=False):
    """Сохраняет данные мультиметра в базу данных"""
    return True

def run_http_server():
    try:
        server_address = ('0.0.0.0', HTTP_PORT)
        httpd = HTTPServer(server_address, CustomHTTPRequestHandler)
        print(f"HTTP-сервер запущен на http://0.0.0.0:{HTTP_PORT}")
        httpd.serve_forever()
    except Exception as e:
        print(f"Ошибка запуска HTTP-сервера: {e}")
        traceback.print_exc()

async def run_websocket_server():
    print(f"WebSocket сервер запущен на ws://0.0.0.0:{WEBSOCKET_PORT}")
    try:
        async with websockets.serve(
            handle_websocket, 
            '0.0.0.0',
            WEBSOCKET_PORT,
            ping_interval=None,
            ping_timeout=None,
            max_size=None,
            max_queue=32,
            compression=None,
            origins=None
        ):
            print("WebSocket сервер успешно запущен и готов принимать подключения")
            await asyncio.Future()
    except Exception as e:
        print(f"Ошибка запуска WebSocket сервера: {e}")
        traceback.print_exc()
        raise

async def main():
    """Main function to start the server"""
    global is_multimeter_running, is_measurement_active
    
    try:
        print("Initializing devices...")
        print("Инициализация визуализатора осциллографа")
        global global_visualizer
        global_visualizer = OscilloscopeVisualizer()
        global_visualizer.connect_to_oscilloscope()
        
        print("Инициализация мультиметра")
        global global_multimeter
        global_multimeter = UT803Reader()
        if global_multimeter.connect_serial():
            print("Мультиметр успешно подключен через RS232")
        elif global_multimeter.connect_hid():
            print("Мультиметр успешно подключен через HID")
        else:
            print("Не удалось подключиться к мультиметру")
        
        print("Starting WebSocket server...")
        async with websockets.serve(
            handle_websocket,
            "0.0.0.0",
            8767,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=20,
            max_size=2**20,
            max_queue=2**10,
            compression=None
        ) as websocket_server:
            print("WebSocket server started at ws://0.0.0.0:8767")
            
            print("Starting HTTP server...")
            http_thread = threading.Thread(target=run_http_server)
            http_thread.daemon = True
            http_thread.start()
            print(f"HTTP-сервер запущен на http://0.0.0.0:{HTTP_PORT}")
            
            is_multimeter_running = True
            is_measurement_active = True
            multimeter_task = asyncio.create_task(run_multimeter())
            
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                print("Получен сигнал завершения работы")
            finally:
                is_multimeter_running = False
                is_measurement_active = False
                if multimeter_task:
                    multimeter_task.cancel()
                    try:
                        await multimeter_task
                    except asyncio.CancelledError:
                        pass
                
                if global_visualizer and global_visualizer.oscilloscope:
                    try:
                        global_visualizer.oscilloscope.close()
                    except Exception as e:
                        print(f"Ошибка при закрытии осциллографа: {e}")
                
                if global_multimeter:
                    try:
                        global_multimeter.disconnect()
                    except Exception as e:
                        print(f"Ошибка при закрытии мультиметра: {e}")
                
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        traceback.print_exc()
        sys.exit(1)

class UT803Reader:
    def __init__(self):
        self.device = None
        self.serial_port = None
        self.connected = False
        self.last_reading = None
    
    def connect_serial(self, port: str = '/dev/ttyUSB0') -> bool:
        try:
            self.serial_port = serial.Serial(
                port=port,
                baudrate=19200,
                bytesize=serial.SEVENBITS,
                parity=serial.PARITY_ODD,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            self.serial_port.setDTR(True)
            self.serial_port.setRTS(False)
            self.serial_port.reset_input_buffer()
            self.serial_port.reset_output_buffer()
            print(f"[Мультиметр] Successfully connected to RS232 port {port}")
            self.connected = True
            return True
        except serial.SerialException as e:
            print(f"[Мультиметр] Failed to connect to RS232: {str(e)}")
            return False
    
    def connect_hid(self) -> bool:
        try:
            for vid, pid in [(0x1A86, 0xE008), (0x04FA, 0x2490)]:
                devices = hid.enumerate(vid, pid)
                if devices:
                    self.device = hid.device()
                    self.device.open(vid, pid)
                    self.device.set_nonblocking(1)
                    print(f"[Мультиметр] Successfully connected to HID device {vid:04X}:{pid:04X}")
                    self.connected = True
                    return True
            print("[Мультиметр] No HID device found")
            return False
        except Exception as e:
            print(f"[Мультиметр] Failed to connect to HID: {str(e)}")
            return False
    
    def decode_ut803_data(self, data: str):
        try:
            parts = data.split(';')
            if len(parts) != 2:
                return None, "Invalid data format"
            value_str = parts[0].strip('@')
            function_code = parts[1]
            try:
                if value_str.startswith('?'):
                    value = "OL"
                else:
                    raw_value = float(value_str)
                    value = raw_value/1000
                    value = f"{value:.3f}"
            except ValueError:
                value = "Error"
            mode = "AC"
            unit = "В"
            measure_type = "Вольтметр"
            if function_code.startswith('8'):
                if '06' in function_code:
                    unit = "В"
                    measure_type = "Вольтметр"
                    mode = "DC"
            current_time = datetime.now()
            timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            if value == "OL":
                json_data = {
                    'timestamp': timestamp,
                    'value': "OL",
                    'unit': unit,
                    'mode': mode,
                    'range_str': "AUTO",
                    'measure_type': measure_type,
                    'raw_data': data
                }
                human_readable = f"[{timestamp}] OL {mode} AUTO"
                return json_data, human_readable
            elif value == "Error":
                return None, "Error"
            else:
                json_data = {
                    'timestamp': timestamp,
                    'value': value,
                    'unit': unit,
                    'mode': mode,
                    'range_str': "AUTO",
                    'measure_type': measure_type,
                    'raw_data': data
                }
                human_readable = f"[{timestamp}] {value} {unit} {mode} AUTO [{measure_type}]"
                return json_data, human_readable
        except Exception as e:
            print(f"[Мультиметр] Error decoding data: {str(e)}")
            return None, f"Error: {str(e)}"
    
    def read_serial(self):
        if not self.serial_port:
            return None, None
        try:
            self.serial_port.reset_input_buffer()
            data = self.serial_port.readline()
            if data:
                try:
                    decoded_data = data.decode('ascii').strip()
                except Exception as e:
                    print(f"[Мультиметр] Ошибка декодирования: {e}")
                    return None, None
                json_data, human_readable = self.decode_ut803_data(decoded_data)
                if json_data and json_data.get('value') == self.last_reading:
                    return None, None
                self.last_reading = json_data.get('value') if json_data else None
                return json_data, human_readable
        except Exception as e:
            print(f"[Мультиметр] Error reading from RS232: {str(e)}")
        return None, None
    
    def read_hid(self):
        if not self.device:
            return None, None
        try:
            data = self.device.read(64, timeout_ms=1000)
            if data:
                json_data, human_readable = self.decode_ut803_data(str(data))
                if json_data and json_data.get('value') == self.last_reading:
                    return None, None
                self.last_reading = json_data.get('value') if json_data else None
                return json_data, human_readable
        except Exception as e:
            print(f"[Мультиметр] Error reading from HID: {str(e)}")
        return None, None
    
    def disconnect(self):
        if self.serial_port:
            self.serial_port.close()
            self.serial_port = None
        if self.device:
            self.device.close()
            self.device = None
        self.connected = False

async def send_to_all_websocket_clients(message):
    global active_websockets
    if active_websockets:
        websockets_to_remove = []
        send_tasks = []
        for client in active_websockets:
            try:
                if hasattr(client, 'open') and client.open:
                    send_task = asyncio.create_task(
                        client.send(json.dumps(message))
                    )
                    send_tasks.append(send_task)
                else:
                    websockets_to_remove.append(client)
            except Exception as e:
                print(f"Ошибка отправки сообщения клиенту: {e}")
                websockets_to_remove.append(client)
        for client in websockets_to_remove:
            if client in active_websockets:
                active_websockets.remove(client)
        if send_tasks:
            await asyncio.wait(send_tasks, return_when=asyncio.ALL_COMPLETED)

async def handle_get_multimeter_data(websocket, connection_id):
    global last_live_multimeter_data, last_multimeter_values
    if 'last_live_multimeter_data' in globals() and last_live_multimeter_data:
        new_value = last_live_multimeter_data['value']
        last_value = last_multimeter_values.get(connection_id)
        if last_value != new_value:
            last_multimeter_values[connection_id] = new_value
            try:
                await websocket.send(json.dumps({
                    'type': 'multimeter',
                    'data': last_live_multimeter_data
                }))
            except Exception:
                pass

async def handle_get_oscilloscope_data(websocket):
    try:
        if global_visualizer and global_visualizer.connected:
            oscilloscope_data = await global_visualizer.get_oscilloscope_data()
            await websocket.send(json.dumps(oscilloscope_data))
    except Exception as e:
        print(f"Ошибка в handle_get_oscilloscope_data: {e}")

def get_oscilloscope_data_paginated(page=1, per_page=50):
    """Возвращает данные осциллографа с пагинацией"""
    session = Session()
    try:
        offset = (page - 1) * per_page
        total = session.query(OscilloscopeData).count()
        results = session.query(OscilloscopeData).order_by(OscilloscopeData.id.desc()).offset(offset).limit(per_page).all()
        data = []
        for row in results:
            data.append({
                'id': row.id,
                'timestamp': row.timestamp,
                'channel': row.channel,
                'voltage': row.voltage,
                'frequency': row.frequency
            })
        return {
            'data': data,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': (total + per_page - 1) // per_page
        }
    except Exception as e:
        print(f"Ошибка получения данных осциллографа с пагинацией: {e}")
        traceback.print_exc()
        return {
            'data': [],
            'total': 0,
            'page': page,
            'per_page': per_page,
            'total_pages': 1
        }
    finally:
        session.close()

def get_multimeter_data_paginated(page=1, per_page=50):
    """Возвращает данные мультиметра с пагинацией"""
    session = Session()
    try:
        offset = (page - 1) * per_page
        total = session.query(MultimeterData).count()
        results = session.query(MultimeterData).order_by(MultimeterData.id.desc()).offset(offset).limit(per_page).all()
        data = []
        for row in results:
            data.append({
                'id': row.id,
                'timestamp': row.timestamp,
                'value': row.value,
                'unit': row.unit,
                'mode': row.mode,
                'range_str': row.range_str,
                'measure_type': row.measure_type,
                'raw_data': row.raw_data
            })
        return {
            'data': data,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': (total + per_page - 1) // per_page
        }
    except Exception as e:
        print(f"Ошибка получения данных мультиметра с пагинацией: {e}")
        traceback.print_exc()
        return {
            'data': [],
            'total': 0,
            'page': page,
            'per_page': per_page,
            'total_pages': 1
        }
    finally:
        session.close()

if __name__ == "__main__":
    if not os.path.exists('index.html'):
        print("Предупреждение: файл index.html не найден!")
    if not os.path.exists('app.js'):
        print("Предупреждение: файл app.js не найден!")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nСервер остановлен пользователем")
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        traceback.print_exc()
        sys.exit(1)
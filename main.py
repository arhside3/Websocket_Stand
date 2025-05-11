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
from sqlalchemy.dialects.sqlite import JSON
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import locale
import traceback

if sys.platform.startswith('win'):
    locale.setlocale(locale.LC_ALL, 'Russian_Russia.UTF-8')
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

DATABASE_URL = 'sqlite:///my_database.db'
WEBSOCKET_PORT = 8767
HTTP_PORT = 8081

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

def save_oscilloscope_data(data, force_save=False):
    """Сохраняет данные осциллографа в базу данных, если нужно"""
    global no_save_oscilloscope
    if no_save_oscilloscope and not force_save:
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
                        frequency=0.0,  # TODO:
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

def save_multimeter_data(data):
    """Сохраняет данные мультиметра в базу данных"""
    session = Session()
    try:
        timestamp = data.get('timestamp', datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3])

        db_record = MultimeterData(
            timestamp=timestamp,
            value=data.get('value', '0.0'),
            unit=data.get('unit', 'В'),
            mode=data.get('mode', 'DC'),
            range_str=data.get('range_str', 'AUTO'),
            measure_type=data.get('measure_type', 'Вольтметр'),
            raw_data=data
        )
        session.add(db_record)
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        print(f"Ошибка сохранения данных мультиметра в БД: {e}")
        traceback.print_exc()
        return False
    finally:
        session.close()

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
    """Возвращает исторические данные осциллографа для графика"""
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

        results = session.query(OscilloscopeData).order_by(OscilloscopeData.id.desc()).limit(100).all()

        timestamps = []
        voltages = []
        
        for row in results:
            timestamps.append(row.timestamp)
            voltages.append(row.voltage)
        
        return {
            'timestamps': list(reversed(timestamps)),
            'voltages': list(reversed(voltages))
        }
    except Exception as e:
        print(f"Ошибка получения истории осциллографа: {e}")
        traceback.print_exc()
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

        results = session.query(MultimeterData).order_by(MultimeterData.id.desc()).limit(100).all()

        timestamps = []
        values = []
        
        for row in results:
            timestamps.append(row.timestamp)
            try:
                values.append(float(row.value))
            except:
                values.append(0.0)
        
        return {
            'timestamps': list(reversed(timestamps)),
            'values': list(reversed(values))
        }
    except Exception as e:
        print(f"Ошибка получения истории мультиметра: {e}")
        traceback.print_exc()
        return {'timestamps': [], 'values': []}
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
        
        self.channel_colors = {1: 'yellow', 2: 'cyan', 3: 'magenta', 4: 'green'}

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
                    
            self.rm = pyvisa.ResourceManager()
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
                    self.oscilloscope = self.rm.open_resource(rigol_address, timeout=2000)
                    self.oscilloscope.clear()
                    idn = self.oscilloscope.query("*IDN?")
                    print("Подключено к осциллографу:", idn)
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
        """Получает данные с канала осциллографа"""
        try:
            if not self.connected or not self.oscilloscope:
                return None, None
                
            with oscilloscope_lock:
                try:
                    time_offset = float(self.oscilloscope.query(":TIM:OFFS?"))
                    time_scale = float(self.oscilloscope.query(":TIM:SCAL?"))
                    
                    self.oscilloscope.write(f":WAV:SOUR CHAN{channel}")
                    self.oscilloscope.write(":WAV:MODE NORM")
                    self.oscilloscope.write(":WAV:FORM BYTE")
                    
                    raw_data = self.oscilloscope.query_binary_values(":WAV:DATA?", datatype='B')
                    
                    volt_scale = float(self.oscilloscope.query(f":CHAN{channel}:SCAL?"))
                    volt_offset = float(self.oscilloscope.query(f":CHAN{channel}:OFFS?"))
                    
                    voltage_data = np.array(raw_data)
                    voltage_data = (voltage_data - 128) * (volt_scale / 25) + volt_offset
                    
                    time_data = np.linspace(time_offset - 6 * time_scale, 
                                          time_offset + 6 * time_scale,
                                          len(voltage_data))
                    
                    return time_data, voltage_data
                except pyvisa.errors.VisaIOError as e:
                    print(f"Ошибка при получении данных с канала {channel}: {e}")
                    if 'VI_ERROR_TMO' in str(e) or 'VI_ERROR_INP_PROT_VIOL' in str(e):
                        self.connected = False
                    return None, None
                
        except Exception as e:
            print(f"Ошибка при получении данных с канала {channel}: {e}")
            return None, None

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
                    
                    return {
                        "volts_div": volts_div,
                        "offset": offset,
                        "coupling": coupling
                    }
                except pyvisa.errors.VisaIOError as e:
                    print(f"Ошибка при получении настроек канала {channel}: {e}")
                    if 'VI_ERROR_TMO' in str(e) or 'VI_ERROR_INP_PROT_VIOL' in str(e):
                        self.connected = False
                    return {"error": str(e)}
        except Exception as e:
            print(f"Ошибка при получении настроек канала {channel}: {e}")
            return {"error": str(e)}

    async def get_oscilloscope_data(self):
        """Получает данные со всех активных каналов"""
        if not self.connected:
            self.connect_to_oscilloscope()
            if not self.connected:
                return {"error": "Осциллограф не подключен"}
                
        try:
            self.update_active_channels()
            
            if not self.active_channels:
                self.active_channels = [1, 2]
            
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
            
            for channel in self.active_channels:
                time_data, voltage_data = self.get_channel_data(channel)
                if time_data is not None and voltage_data is not None:
                    settings = self.get_channel_settings(channel)
                    oscilloscope_data["channels"][f"CH{channel}"] = {
                        "time": time_data.tolist(),
                        "voltage": voltage_data.tolist(),
                        "settings": settings,
                        "color": self.channel_colors[channel]
                    }
                
            if not oscilloscope_data["channels"]:
                return {"error": "Не удалось получить данные с каналов осциллографа"}
                
            return oscilloscope_data
        except Exception as e:
            print(f"Ошибка при получении данных с осциллографа: {e}")
            traceback.print_exc()
            return {"error": "Ошибка получения данных с осциллографа"}

# HTTP-сервер
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

    def send_error(self, code, message=None, explain=None):
        try:
            self.send_response(code, message)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Connection', 'close')
            self.end_headers()
            
            content = self.error_message_format % {
                'code': code,
                'message': message or ''
            }
            self.wfile.write(content.encode('utf-8'))
        except Exception as e:
            print(f"Ошибка при отправке ошибки HTTP: {e}")

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
                self.send_json_response(get_oscilloscope_data_from_db())
            elif path == '/db/multimeter':
                self.send_json_response(get_multimeter_data_from_db())
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

# WebSocket обработчик
async def handle_websocket(websocket):
    global active_websockets, global_visualizer
    try:
        active_websockets.add(websocket)
        print(f"Клиент подключен к WebSocket")

        if global_visualizer is None or not global_visualizer.running:
            print("Инициализация визуализатора осциллографа")
            global_visualizer = OscilloscopeVisualizer()
            connected = global_visualizer.connect_to_oscilloscope()
            if connected:
                print("Осциллограф успешно подключен")
            else:
                print("Не удалось подключиться к осциллографу.")

        async for message in websocket:
            try:
                data = json.loads(message)
                if data.get('action') == 'run_lua':
                    script_name = data.get('script', 'main.lua')
                    try:
                        process = await asyncio.create_subprocess_shell(
                            f'lua {script_name}',
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE
                        )
                        stdout, stderr = await process.communicate()
                        stdout = stdout.decode('utf-8', errors='replace') if stdout else ''
                        stderr = stderr.decode('utf-8', errors='replace') if stderr else ''
                        if stdout:
                            await websocket.send(json.dumps({'output': stdout}))
                        if stderr:
                            await websocket.send(json.dumps({'output': f"Ошибка: {stderr}"}))
                    except Exception as e:
                        await websocket.send(json.dumps({'output': f"Ошибка выполнения скрипта: {str(e)}"}))
                        print(f"Ошибка выполнения Lua-скрипта: {e}")
                
                elif data.get('action') == 'toggle_save_oscilloscope':
                    global no_save_oscilloscope
                    no_save_oscilloscope = not no_save_oscilloscope
                    await websocket.send(json.dumps({
                        'status': 'ok',
                        'save_oscilloscope': not no_save_oscilloscope
                    }))
                    print(f"Сохранение данных осциллографа {'отключено' if no_save_oscilloscope else 'включено'}")
                        
                elif data.get('action') == 'get_oscilloscope_data':
                    if global_visualizer and global_visualizer.connected:
                        try:
                            oscilloscope_data = await global_visualizer.get_oscilloscope_data()

                            await websocket.send(json.dumps(oscilloscope_data))
                        except Exception as e:
                            print(f"Ошибка при получении/отправке данных осциллографа: {e}")
                            error_data = {"error": f"Ошибка получения данных: {str(e)}"}
                            await websocket.send(json.dumps(error_data))
                    else:
                        error_data = {"error": "Осциллограф не подключен"}
                        await websocket.send(json.dumps(error_data))
                        print("Сообщение об ошибке отправлено клиенту")

                elif data.get('type') == 'oscilloscope' and data.get('data'):
                    force_save = data.get('force_save', False)

                    if force_save:
                        success = save_oscilloscope_data(data['data'], force_save=True)
                    else:
                        success = save_oscilloscope_data(data['data'])
                    
                    for connected_ws in active_websockets:
                        if connected_ws != websocket and connected_ws.open:
                            try:
                                await connected_ws.send(json.dumps(data))
                            except Exception as ws_err:
                                print(f"Ошибка отправки данных клиенту: {ws_err}")
                                
                elif data.get('type') == 'multimeter' and data.get('data'):
                    success = save_multimeter_data(data['data'])
                    
                    for connected_ws in active_websockets:
                        if connected_ws != websocket and connected_ws.open:
                            try:
                                await connected_ws.send(json.dumps(data))
                            except Exception as ws_err:
                                print(f"Ошибка отправки данных клиенту: {ws_err}")
            except json.JSONDecodeError:
                print(f"Ошибка декодирования JSON: {message}")
            except Exception as e:
                print(f"Ошибка обработки сообщения: {e}")
                traceback.print_exc()
                try:
                    await websocket.send(json.dumps({'output': f"Ошибка: {str(e)}"}))
                except:
                    pass
    except websockets.exceptions.ConnectionClosed:
        print("WebSocket соединение закрыто")
    except Exception as e:
        print(f"Ошибка в WebSocket обработчике: {e}")
        traceback.print_exc()
    finally:
        if websocket in active_websockets:
            active_websockets.remove(websocket)

def run_http_server():
    try:
        server_address = ('', HTTP_PORT)
        httpd = HTTPServer(server_address, CustomHTTPRequestHandler)
        print(f"HTTP-сервер запущен на порту {HTTP_PORT}")
        httpd.serve_forever()
    except Exception as e:
        print(f"Ошибка запуска HTTP-сервера: {e}")
        traceback.print_exc()

async def run_oscilloscope():
    global global_visualizer, active_websockets
    
    while True:
        try:
            if active_websockets and global_visualizer and global_visualizer.connected:
                try:
                    oscilloscope_data = await global_visualizer.get_oscilloscope_data()
                    
                    if oscilloscope_data and 'error' not in oscilloscope_data:
                        disconnected_clients = []
                        for websocket in active_websockets:
                            try:
                                if hasattr(websocket, 'open') and websocket.open:
                                    await websocket.send(json.dumps(oscilloscope_data))
                                else:
                                    disconnected_clients.append(websocket)
                            except Exception as e:
                                print(f"Ошибка отправки данных клиенту: {e}")
                                disconnected_clients.append(websocket)
                        
                        for client in disconnected_clients:
                            if client in active_websockets:
                                active_websockets.remove(client)
                except Exception as e:
                    print(f"Ошибка получения данных с осциллографа: {e}")
        except Exception as e:
            print(f"Ошибка в цикле осциллографа: {e}")

        await asyncio.sleep(0.1)

async def run_websocket_server():
    print(f"WebSocket сервер запущен на ws://localhost:{WEBSOCKET_PORT}")
    async with websockets.serve(handle_websocket, 'localhost', WEBSOCKET_PORT, ping_interval=30, ping_timeout=300):
        await asyncio.Future()

async def main():
    http_thread = threading.Thread(target=run_http_server)
    http_thread.daemon = True
    http_thread.start()

    await asyncio.gather(
        run_websocket_server(),
        run_oscilloscope()
    )

if __name__ == "__main__":
    if not os.path.exists('index.html'):
        print("Предупреждение: файл index.html не найден!")
    if not os.path.exists('app.js'):
        print("Предупреждение: файл app.js не найден!")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nПрограмма завершена пользователем")
    except Exception as e:
        print(f"Ошибка при выполнении программы: {e}")
        traceback.print_exc()

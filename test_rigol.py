# -*- coding: utf-8 -*-
import threading
import pyvisa
import numpy as np
import json
import time
import sys
import locale
import os
import argparse
import sqlite3
import websockets
import asyncio
from datetime import datetime
import traceback
from sqlalchemy import create_engine, Column, Integer, JSON, Float, String, DateTime, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

if sys.platform.startswith('win'):
    locale.setlocale(locale.LC_ALL, 'Russian_Russia.UTF-8')
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

oscilloscope_lock = threading.Lock()

DATABASE_PATH = 'my_database.db'
# WEBSOCKET_URL = 'ws://localhost:8767'

# Constants
WEBSOCKET_PORT = 8768  # Changed from 8767 to avoid conflict
DATABASE_URL = 'sqlite:///my_database.db'  # Use the existing database

# Database setup
engine = create_engine(DATABASE_URL, echo=False)
Base = declarative_base()

class OscilloscopeData(Base):
    __tablename__ = 'осциллограф'
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime)
    channel = Column(String)
    voltage = Column(Float)
    frequency = Column(Float)
    raw_data = Column(JSON)
    time_base = Column(Float)
    time_offset = Column(Float)
    trigger_level = Column(Float)

# Drop and recreate tables
Base.metadata.drop_all(engine)  # Drop existing tables
Base.metadata.create_all(engine)  # Create tables with new schema
Session = sessionmaker(bind=engine)

class OscilloscopeReader:
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
                    
            # Создаем менеджер ресурсов с явным указанием бэкенда для Linux
            self.rm = pyvisa.ResourceManager('@py')
                
            # Получаем список доступных устройств
            resources = self.rm.list_resources()
            print("Доступные устройства:", resources)
            
            # Ищем осциллограф Rigol
            rigol_address = None
            for resource in resources:
                if 'USB' in resource and ('DS1' in resource or 'DS2' in resource):
                    rigol_address = resource
                    break
            
            if rigol_address:
                print("Подключение к осциллографу по адресу:", rigol_address)
                try:
                    # Открываем ресурс с расширенными настройками для Linux
                    self.oscilloscope = self.rm.open_resource(rigol_address)
                    self.oscilloscope.timeout = 20000  # Увеличиваем таймаут до 20 секунд
                    self.oscilloscope.write_termination = '\n'
                    self.oscilloscope.read_termination = '\n'
                    self.oscilloscope.chunk_size = 1024
                    
                    # Проверяем подключение
                    idn = self.oscilloscope.query("*IDN?")
                    print("Подключено к осциллографу:", idn)
                    
                    # Устанавливаем базовые настройки для работы
                    self.oscilloscope.write(":WAV:FORM BYTE")
                    self.oscilloscope.write(":WAV:MODE NORM")
                    self.oscilloscope.write(":WAV:POIN 1200")
                    time.sleep(0.5)  # Даем время на применение настроек
                    
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
            try:
                # Устанавливаем источник данных и ждем
                self.oscilloscope.write(f":WAV:SOUR CHAN{channel}")
                time.sleep(0.05)  # Сокращаем время ожидания
                
                # Получаем настройки канала до получения данных
                volt_scale = float(self.oscilloscope.query(f":CHAN{channel}:SCAL?"))
                volt_offset = float(self.oscilloscope.query(f":CHAN{channel}:OFFS?"))
                time_scale = float(self.oscilloscope.query(":TIM:SCAL?"))
                
                # Получаем данные в два этапа
                self.oscilloscope.write(":WAV:DATA?")
                time.sleep(0.05)  # Сокращаем время ожидания
                raw_data = self.oscilloscope.read_raw()
                
                # Обрабатываем полученные данные
                if raw_data:
                    # Пропускаем заголовок (#8...)
                    data_start = raw_data.find(b'#')
                    if data_start != -1:
                        header_end = raw_data.find(b'\n', data_start)
                        if header_end != -1:
                            raw_data = raw_data[header_end + 1:]
                    
                # Преобразуем данные - используем быстрый метод
                try:
                    # Используем оптимизированное преобразование данных
                    voltage_data = np.frombuffer(raw_data, dtype=np.uint8)
                    voltage_data = (voltage_data - 128) * (volt_scale / 25) + volt_offset
                    
                    # Создаем временную шкалу с меньшим количеством точек для повышения скорости
                    # Используем только каждую вторую точку для ускорения
                    step = 2  # Берем каждую вторую точку
                    voltage_data = voltage_data[::step]
                    time_data = np.linspace(-6 * time_scale, 6 * time_scale, len(voltage_data))
                    
                    return time_data, voltage_data
                except Exception as e:
                    print(f"Ошибка обработки данных осциллографа: {e}")
                    return None, None
    
            except pyvisa.errors.VisaIOError as e:
                print(f"Ошибка при получении данных с канала {channel}: {e}")
                if 'VI_ERROR_TMO' in str(e):
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
            try:
                volts_div = float(self.oscilloscope.query(f":CHAN{channel}:SCAL?"))
                offset = float(self.oscilloscope.query(f":CHAN{channel}:OFFS?"))
                coupling = self.oscilloscope.query(f":CHAN{channel}:COUP?").strip()
                display = self.oscilloscope.query(f":CHAN{channel}:DISP?").strip()
                
                return {
                    "volts_div": volts_div,
                    "offset": offset,
                    "coupling": coupling,
                "display": display  # Добавляем состояние отображения канала
                }
            except pyvisa.errors.VisaIOError as e:
                print(f"Ошибка при получении настроек канала {channel}: {e}")
                if 'VI_ERROR_TMO' in str(e) or 'VI_ERROR_INP_PROT_VIOL' in str(e):
                    self.connected = False
                return {"error": str(e)}
        except Exception as e:
            print(f"Ошибка при получении настроек канала {channel}: {e}")
            return {"error": str(e)}

    def get_oscilloscope_data(self):
        """Получает данные со всех активных каналов"""
        if not self.connected:
            self.connect_to_oscilloscope()
            if not self.connected:
                return {"error": "Осциллограф не подключен"}
                
        try:
            self.update_active_channels()
            
            oscilloscope_data = {
                "type": "oscilloscope_data",
                "data": {
                "time_base": 0.001,
                "time_offset": 0.0,
                "trigger_level": 0.0,
                "channels": {}
                }
            }
            
            try:
                if self.connected and self.oscilloscope:
                    oscilloscope_data["data"]["time_base"] = float(self.oscilloscope.query(":TIM:SCAL?"))
                    oscilloscope_data["data"]["time_offset"] = float(self.oscilloscope.query(":TIM:OFFS?"))
                    oscilloscope_data["data"]["trigger_level"] = float(self.oscilloscope.query(":TRIG:EDGE:LEV?"))
            except Exception as e:
                print(f"Ошибка при получении общих настроек осциллографа: {e}")
                self.connected = False
                return {"error": "Ошибка получения настроек осциллографа"}
            
            # Проверяем все каналы (1-4)
            for channel in range(1, 5):
                settings = self.get_channel_settings(channel)
                if 'error' not in settings:
                    # Проверяем, активен ли канал
                    is_active = settings.get('display') == '1'
                    
                    # Получаем данные только если канал активен
                    if is_active:
                        time_data, voltage_data = self.get_channel_data(channel)
                        if time_data is not None and voltage_data is not None:
                                    oscilloscope_data["data"]["channels"][f"CH{channel}"] = {
                                "time": time_data.tolist(),
                                "voltage": voltage_data.tolist(),
                                        "settings": settings,
                                        "color": self.channel_colors[channel]
                                    }
                        else:
                            # Для неактивных каналов отправляем только настройки
                            oscilloscope_data["data"]["channels"][f"CH{channel}"] = {
                            "settings": settings,
                            "color": self.channel_colors[channel]
                        }
                    
            if not any('voltage' in channel_data for channel_data in oscilloscope_data["data"]["channels"].values()):
                return {"error": "Нет активных каналов осциллографа"}
                
            return oscilloscope_data
        except Exception as e:
            print(f"Ошибка при получении данных с осциллографа: {e}")
            traceback.print_exc()
            return {"error": "Ошибка получения данных с осциллографа"}

    def close(self):
        """Закрывает соединение с осциллографом"""
        if self.oscilloscope:
            try:
                self.oscilloscope.close()
            except:
                pass
        if self.rm:
            try:
                self.rm.close()
            except:
                pass

def save_to_database(data):
    """Сохраняет данные осциллографа в БД SQLite"""
    if not data:
        print("Нет данных для сохранения")
        return False
    session = Session()
    if 'data' in data and 'channels' in data['data']:
        for channel_name, channel_data in data['data']['channels'].items():
            if 'voltage' in channel_data and len(channel_data['voltage']) > 0:
                avg_voltage = np.mean(channel_data['voltage'])
            
                record = OscilloscopeData(
                    timestamp=datetime.now(),
                    channel=channel_name,
                    voltage=float(avg_voltage),
                    frequency=0.0,  # Default value
                    raw_data=channel_data,
                    time_base=data['data']['time_base'],
                    time_offset=data['data']['time_offset'],
                    trigger_level=data['data']['trigger_level']
                )
                session.add(record)
                print(f"Сохранены данные канала {channel_name}, среднее напряжение: {avg_voltage:.3f}В")

    session.commit()
    return True

# WebSocket server
active_websockets = set()

async def handle_websocket(websocket, path):
    print(f"Новое подключение: {websocket.remote_address}")
    active_websockets.add(websocket)
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                if data.get('action') == 'get_oscilloscope_data':
                    oscilloscope_data = reader.get_oscilloscope_data()
                    if 'error' not in oscilloscope_data:
                        await websocket.send(json.dumps(oscilloscope_data))
                    else:
                        await websocket.send(json.dumps({
                            "type": "error",
                            "message": oscilloscope_data["error"]
                        }))
            except json.JSONDecodeError:
                print("Ошибка декодирования JSON")
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON format"
                }))
            except Exception as e:
                print(f"Ошибка обработки сообщения: {e}")
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": str(e)
                }))
    except websockets.exceptions.ConnectionClosed:
        print(f"Соединение закрыто: {websocket.remote_address}")
    finally:
            active_websockets.remove(websocket)

async def update_oscilloscope_data():
        try:
            if not reader.connected:
                return
            oscilloscope_data = reader.get_oscilloscope_data()
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

async def main_async(args):
    global reader
    reader = OscilloscopeReader()
    
    if not reader.connect_to_oscilloscope():
        print("Не удалось подключиться к осциллографу")
        return

    # Запускаем WebSocket сервер
    server = await websockets.serve(handle_websocket, "0.0.0.0", 8768)
    print("WebSocket сервер запущен на ws://0.0.0.0:8768")

    try:
        # Основной цикл измерений
        for i in range(args.samples):
            print(f"\nПолучение выборки {i+1}/{args.samples}")
            
            # Получаем данные с осциллографа
            oscilloscope_data = reader.get_oscilloscope_data()
            if 'error' in oscilloscope_data:
                print(f"Ошибка получения данных: {oscilloscope_data['error']}")
                continue

            # Сохраняем данные в БД
                print("Сохраняем данные в БД напрямую...")
            if save_to_database(oscilloscope_data):
                    print("Данные успешно сохранены в БД напрямую")
            else:
                print("Ошибка при сохранении данных в БД")

            # --- ВАЖНО: отправляем данные всем WebSocket клиентам ---
            await update_oscilloscope_data()  # Эта функция отправляет данные всем клиентам
            
            # Ждем указанный интервал
            await asyncio.sleep(args.interval)

    except KeyboardInterrupt:
        print("\nЗавершение работы...")
    except Exception as e:
        print(f"Ошибка в основном цикле: {e}")
        traceback.print_exc()
    finally:
        # Закрываем соединения
        if reader:
            reader.close()
            server.close()
            await server.wait_closed()
            print("Работа программы завершена")

def main():
    parser = argparse.ArgumentParser(description='Тестирование осциллографа Rigol')
    parser.add_argument('--samples', type=int, default=10, help='Количество выборок')
    parser.add_argument('--interval', type=float, default=1.0, help='Интервал между выборками в секундах')
    parser.add_argument('--force-save', action='store_true', help='Принудительное сохранение в БД')
    args = parser.parse_args()

    asyncio.run(main_async(args))

if __name__ == "__main__":
    main() 
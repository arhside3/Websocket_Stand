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

if sys.platform.startswith('win'):
    locale.setlocale(locale.LC_ALL, 'Russian_Russia.UTF-8')
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

oscilloscope_lock = threading.Lock()

DATABASE_PATH = 'my_database.db'
WEBSOCKET_URL = 'ws://localhost:8767'

class OscilloscopeReader:
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

    def get_oscilloscope_data(self):
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
            print(f"Ошибка при получении данных осциллографа: {e}")
            traceback.print_exc()
            return {"error": f"Ошибка получения данных с осциллографа: {e}"}

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
    
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS осциллограф (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                channel TEXT,
                voltage REAL,
                frequency REAL,
                raw_data TEXT
            )
        """)
        
        if 'channels' in data:
            for channel_name, channel_data in data['channels'].items():
                if 'voltage' in channel_data and len(channel_data['voltage']) > 0:
                    mean_voltage = np.mean(channel_data['voltage'])
                    
                    cursor.execute(
                        "INSERT INTO осциллограф (timestamp, channel, voltage, frequency, raw_data) VALUES (?, ?, ?, ?, ?)",
                        (
                            timestamp,
                            channel_name,
                            float(mean_voltage),
                            0.0,
                            json.dumps(channel_data)
                        )
                    )
                    print(f"Сохранены данные канала {channel_name}, среднее напряжение: {mean_voltage:.3f}В")
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Ошибка сохранения данных в БД: {e}")
        traceback.print_exc()
        return False

async def send_data_to_websocket(data, save_to_db=True):
    """Отправляет данные на WebSocket сервер и опционально сохраняет в БД"""
    try:
        async with websockets.connect(WEBSOCKET_URL) as websocket:
            if save_to_db:
                await websocket.send(json.dumps({
                    'type': 'oscilloscope',
                    'data': data
                }))
                print("Данные отправлены на сервер для сохранения в БД")
            else:
                await websocket.send(json.dumps(data))
                print("Данные отправлены на сервер для отображения")
            
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                print(f"Получен ответ от сервера: {response}")
            except asyncio.TimeoutError:
                print("Тайм-аут ожидания ответа от сервера")
        
        return True
    except Exception as e:
        print(f"Ошибка отправки данных через WebSocket: {e}")
        traceback.print_exc()
        
        if save_to_db:
            print("Сохраняем данные в БД напрямую...")
            return save_to_database(data)
        
        return False

async def main_async(args):
    reader = OscilloscopeReader()
    
    try:
        if not args.test:
            if not reader.connect_to_oscilloscope():
                print("Не удалось подключиться к осциллографу.")
                return
        else:
            print("Запрошен тестовый режим, но генерация тестовых данных отключена")
            return
        
        sample_count = 0
        
        while args.continuous or sample_count < args.samples:
            if not args.continuous:
                print(f"\nПолучение выборки {sample_count+1}/{args.samples}")
            else:
                print(f"\nПолучение выборки #{sample_count+1}")
            
            data = reader.get_oscilloscope_data()
            
            if data and 'error' in data:
                print(f"Ошибка получения данных: {data['error']}")
                if not args.continuous:
                    break
                else:
                    await asyncio.sleep(args.interval)
                    continue
            
            if data:
                force_save = args.force_save
                
                if args.no_save and not force_save:
                    success = await send_data_to_websocket(data, save_to_db=False)
                    if success:
                        print(f"Данные успешно отправлены для отображения (без сохранения в БД)")
                    else:
                        print(f"Ошибка отправки данных")
                else:
                    save_to_db = True
                    
                    if force_save:
                        try:
                            async with websockets.connect(WEBSOCKET_URL) as websocket:
                                await websocket.send(json.dumps({
                                    'type': 'oscilloscope',
                                    'data': data,
                                    'force_save': True
                                }))
                                print("Данные отправлены с принудительным сохранением в БД")
                                success = True
                        except Exception as e:
                            print(f"Ошибка отправки данных через WebSocket: {e}")
                            print("Сохраняем данные в БД напрямую...")
                            success = save_to_database(data)
                            if success:
                                print("Данные успешно сохранены в БД напрямую")
                            else:
                                print("Ошибка при прямом сохранении данных в БД")
                    else:
                        success = await send_data_to_websocket(data, save_to_db=True)
                        if success:
                            print(f"Данные успешно отправлены и сохранены в БД")
                        else:
                            print(f"Ошибка отправки/сохранения данных")
            
            sample_count += 1
            
            if args.continuous or sample_count < args.samples:
                await asyncio.sleep(args.interval)
    
    except KeyboardInterrupt:
        print("\nПрограмма завершена пользователем")
    except Exception as e:
        print(f"Ошибка выполнения программы: {e}")
        traceback.print_exc()
    finally:
        reader.close()
        print("Завершение работы программы")

def main():
    parser = argparse.ArgumentParser(description='Сбор данных с осциллографа Rigol и отправка на сервер')
    parser.add_argument('--samples', type=int, default=5, help='Количество выборок данных (по умолчанию: 5)')
    parser.add_argument('--interval', type=float, default=1.0, help='Интервал между выборками в секундах (по умолчанию: 1.0)')
    parser.add_argument('--test', action='store_true', help='Тестовый режим (данные не будут сгенерированы)')
    parser.add_argument('--continuous', action='store_true', help='Непрерывный режим сбора данных')
    parser.add_argument('--no-save', action='store_true', help='Не сохранять данные в БД, только отображать')
    parser.add_argument('--force-save', action='store_true', help='Принудительно сохранять данные в БД, даже если режим сохранения отключен')
    args = parser.parse_args()

    asyncio.run(main_async(args))

if __name__ == '__main__':
    main() 
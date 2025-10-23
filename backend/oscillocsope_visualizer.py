import asyncio
import json
import threading
import time
import traceback

import numpy as np
import pyvisa

from backend.engine import *
from backend.models import OscilloscopeData

oscilloscope_lock = threading.Lock()
active_websockets = set()


class OscilloscopeVisualizer:
    def __init__(self):
        self.rm = None
        self.oscilloscope = None
        self.active_channels = []
        self.running = True
        self.connected = False

        self.channel_colors = {
            1: 'yellow',
            2: 'cyan',
            3: 'magenta',
            4: '#00aaff',
        }

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
                if 'USB' in resource and (
                    'DS1' in resource or 'DS2' in resource
                ):
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
                    if (
                        self.oscilloscope.query(
                            f":CHAN{channel}:DISP?"
                        ).strip()
                        == '1'
                    ):
                        self.active_channels.append(channel)
                except pyvisa.errors.VisaIOError as e:
                    print(
                        f"Ошибка при проверке активности канала {channel}: {e}"
                    )
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

                    volt_scale = float(
                        self.oscilloscope.query(f":CHAN{channel}:SCAL?")
                    )
                    volt_offset = float(
                        self.oscilloscope.query(f":CHAN{channel}:OFFS?")
                    )
                    time_scale = float(self.oscilloscope.query(":TIM:SCAL?"))

                    self.oscilloscope.write(":WAV:DATA?")
                    time.sleep(0.05)
                    raw_data = self.oscilloscope.read_raw()

                    if raw_data:
                        data_start = raw_data.find(b'#')
                        if data_start != -1:
                            header_end = raw_data.find(b'\n', data_start)
                            if header_end != -1:
                                raw_data = raw_data[header_end + 1 :]

                        try:
                            voltage_data = np.frombuffer(
                                raw_data, dtype=np.uint8
                            )
                            voltage_data = (voltage_data - 128) * (
                                volt_scale / 25
                            ) + volt_offset

                            step = 2
                            voltage_data = voltage_data[::step]
                            time_data = np.linspace(
                                -6 * time_scale,
                                6 * time_scale,
                                len(voltage_data),
                            )

                            return time_data, voltage_data
                        except Exception as e:
                            print(f"Ошибка обработки данных осциллографа: {e}")
                            return None, None

                    return None, None
                except pyvisa.errors.VisaIOError as e:
                    print(
                        f"Ошибка при получении данных с канала {channel}: {e}"
                    )
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
                    volts_div = float(
                        self.oscilloscope.query(f":CHAN{channel}:SCAL?")
                    )
                    offset = float(
                        self.oscilloscope.query(f":CHAN{channel}:OFFS?")
                    )
                    coupling = self.oscilloscope.query(
                        f":CHAN{channel}:COUP?"
                    ).strip()
                    display = self.oscilloscope.query(
                        f":CHAN{channel}:DISP?"
                    ).strip()

                    return {
                        "volts_div": volts_div,
                        "offset": offset,
                        "coupling": coupling,
                        "display": display,
                    }
                except pyvisa.errors.VisaIOError as e:
                    print(
                        f"Ошибка при получении настроек канала {channel}: {e}"
                    )
                    if 'VI_ERROR_TMO' in str(
                        e
                    ) or 'VI_ERROR_INP_PROT_VIOL' in str(e):
                        self.connected = False
                    return {"error": str(e)}
        except Exception as e:
            print(f"Ошибка при получении настроек канала {channel}: {e}")
            return {"error": str(e)}

    async def get_channel_settings_async(self, channel):
        """Асинхронная обертка для получения настроек канала"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self.get_channel_settings(channel)
        )

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
                "channels": {},
            }

            try:
                if self.connected and self.oscilloscope:
                    oscilloscope_data["time_base"] = float(
                        self.oscilloscope.query(":TIM:SCAL?")
                    )
                    oscilloscope_data["time_offset"] = float(
                        self.oscilloscope.query(":TIM:OFFS?")
                    )
                    oscilloscope_data["trigger_level"] = float(
                        self.oscilloscope.query(":TRIG:EDGE:LEV?")
                    )
                    try:
                        oscilloscope_data["trigger"] = {
                            "level": float(
                                self.oscilloscope.query(":TRIG:EDGE:LEV?")
                            ),
                            "mode": self.oscilloscope.query(
                                ":TRIG:MODE?"
                            ).strip(),
                            "source": self.oscilloscope.query(
                                ":TRIG:EDGE:SOUR?"
                            ).strip(),
                            "slope": self.oscilloscope.query(
                                ":TRIG:EDGE:SLOP?"
                            ).strip(),
                        }
                    except Exception as e:
                        oscilloscope_data["trigger"] = {
                            "level": oscilloscope_data.get("trigger_level", 0),
                            "mode": "Auto",
                            "source": "CH1",
                            "slope": "Rising",
                        }
            except Exception as e:
                print(f"Ошибка при получении общих настроек осциллографа: {e}")
                self.connected = False
                return {"error": "Ошибка получения настроек осциллографа"}

            for channel in range(1, 5):
                settings = self.get_channel_settings(channel)
                if 'error' not in settings:
                    is_active = settings.get('display') == '1'

                    if is_active:
                        time_data, voltage_data = self.get_channel_data(
                            channel
                        )
                        if time_data is not None and voltage_data is not None:
                            oscilloscope_data["channels"][f"CH{channel}"] = {
                                "time": time_data.tolist(),
                                "voltage": voltage_data.tolist(),
                                "settings": settings,
                                "color": self.channel_colors[channel],
                            }
                    else:
                        oscilloscope_data["channels"][f"CH{channel}"] = {
                            "settings": settings,
                            "color": self.channel_colors[channel],
                        }

            if not any(
                'voltage' in channel_data
                for channel_data in oscilloscope_data["channels"].values()
            ):
                return {"error": "Нет активных каналов осциллографа"}

            return oscilloscope_data
        except Exception as e:
            print(f"Ошибка при получении данных с осциллографа: {e}")
            traceback.print_exc()
            return {"error": "Ошибка получения данных с осциллографа"}

    def set_channel_settings(self, channel_name, settings):
        """Устанавливает настройки канала осциллографа"""
        if not self.connected or not self.oscilloscope:
            return {"error": "Oscilloscope not connected"}
        try:
            ch_num = int(channel_name.replace('CH', ''))
            with oscilloscope_lock:
                if 'display' in settings:
                    self.oscilloscope.write(
                        f":CHAN{ch_num}:DISP {1 if settings['display'] else 0}"
                    )
                if 'volts_div' in settings:
                    self.oscilloscope.write(
                        f":CHAN{ch_num}:SCAL {settings['volts_div']}"
                    )
                if 'offset' in settings:
                    self.oscilloscope.write(
                        f":CHAN{ch_num}:OFFS {settings['offset']}"
                    )
                if 'coupling' in settings:
                    self.oscilloscope.write(
                        f":CHAN{ch_num}:COUP {settings['coupling']}"
                    )
            return self.get_channel_settings(ch_num)
        except Exception as e:
            print(f"Ошибка при установке настроек канала {channel_name}: {e}")
            return {"error": str(e)}


def get_channel_history(channel_name, limit=20):
    session = Session()
    try:
        results = (
            session.query(OscilloscopeData)
            .filter(OscilloscopeData.channel == channel_name)
            .order_by(OscilloscopeData.id.desc())
            .limit(limit)
            .all()
        )
        all_time = []
        all_voltage = []
        import base64

        for row in reversed(results):
            try:
                t = np.frombuffer(
                    base64.b64decode(row.time_data), dtype=np.float32
                )
                v = np.frombuffer(
                    base64.b64decode(row.voltage_data), dtype=np.float32
                )
                all_time.extend(t.tolist())
                all_voltage.extend(v.tolist())
            except Exception as e:
                continue
        return all_time, all_voltage
    finally:
        session.close()


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
                await asyncio.wait(
                    send_tasks, return_when=asyncio.ALL_COMPLETED
                )
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
            if (
                active_websockets
                and global_visualizer
                and global_visualizer.connected
                and (current_time - last_oscilloscope_update)
                >= oscilloscope_interval
                and is_measurement_active
            ):
                last_oscilloscope_update = current_time
                await update_oscilloscope_data()
        except Exception as e:
            print(f"Ошибка в цикле осциллографа: {e}")
            await asyncio.sleep(0.1)
        await asyncio.sleep(0.01)

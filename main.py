import asyncio
import concurrent.futures
import json
import os
import sys
import threading
import traceback
from datetime import datetime
from http.server import HTTPServer

import websockets
from serial.tools import list_ports

from backend.http_methods import *
from backend.measurement import *
from backend.multimetrUT803 import *
from backend.oscillocsope_visualizer import *
from backend.run_lua import *
from backend.send_websocket import send_to_all_websocket_clients
from backend.settings import (HTTP_PORT, current_uart_data, global_multimeter,
                              http_event_loop, is_measurement_active,
                              is_multimeter_running, last_multimeter_values,
                              multimeter_task, oscilloscope_task)
from backend.setup_db import *

active_websockets = set()


def process_uart_packet(packet_bytes):
    try:
        start_byte = packet_bytes[0]
        command = packet_bytes[1]
        status = packet_bytes[2]
        payload_len = packet_bytes[3]
        payload = packet_bytes[4:62]
        crc_one = packet_bytes[62]
        crc_two = packet_bytes[63]

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        data = {
            'timestamp': timestamp,
            'start_byte': start_byte,
            'command': command,
            'status': status,
            'payload_len': payload_len,
            'payload': payload,
            'crc_one': crc_one,
            'crc_two': crc_two,
        }

        save_uart_data(data)
        if current_uart_table:
            save_uart_data_to_test(data, current_uart_table)

        print(
            f"UART пакет сохранен: CMD={command}, StartByte=0x{start_byte:02X}"
        )

    except Exception as e:
        print(f"Ошибка обработки UART пакета: {e}")
        traceback.print_exc()


async def handle_websocket(websocket):
    global global_multimeter, global_visualizer, is_measurement_active, is_oscilloscope_running, is_multimeter_running, oscilloscope_task, multimeter_task
    print("Клиент подключен к WebSocket")

    active_websockets.add(websocket)

    try:
        await websocket.send(
            json.dumps({'type': 'sensor_data', 'data': current_uart_data})
        )
        print(f"📤 Sent current UART data to new client: {current_uart_data}")
    except Exception as e:
        print(f"Error sending initial UART data: {e}")

    try:
        async for message in websocket:
            try:
                if isinstance(message, bytes):
                    process_uart_packet(message)
                    continue

                data = json.loads(message)

                if 'timestamp' in data and 'value' in data and 'unit' in data:
                    print(f"Получены данные мультиметра: {data}")
                    force_save = data.get('force_save', False)
                    print(f"Флаг force_save: {force_save}")
                    if force_save:
                        save_multimeter_data(data, force_save=True)
                        print(
                            f"Данные мультиметра сохранены (force_save): {data}"
                        )

                    await send_to_all_websocket_clients(
                        {"type": "multimeter", "data": data}
                    )
                    continue

                action = data.get('action')

                if action == 'run_lua':
                    script_name = data.get('script', 'contrib/main.lua')
                    print(f"Запуск Lua скрипта: {script_name}")

                    test_number = start_new_test()
                    if test_number:
                        await websocket.send(
                            json.dumps(
                                {
                                    'type': 'test_started',
                                    'test_number': test_number,
                                }
                            )
                        )

                    await run_lua_test_parallel_async(script_name, websocket)

                elif action == 'start_measurements':
                    is_measurement_active = True
                    if global_visualizer and not global_visualizer.connected:
                        global_visualizer.connect_to_oscilloscope()
                    if not global_multimeter:
                        global_multimeter = UT803Reader()
                        global_multimeter.connect_serial() or global_multimeter.connect_hid()
                    await websocket.send(
                        json.dumps(
                            {
                                'type': 'status',
                                'data': {'status': 'measurements_started'},
                            }
                        )
                    )

                elif action == 'stop_measurements':
                    is_measurement_active = False
                    if global_visualizer and global_visualizer.oscilloscope:
                        try:
                            global_visualizer.oscilloscope.close()
                        except Exception as e:
                            print(
                                f"Ошибка при разрыве соединения с осциллографом: {e}"
                            )
                        global_visualizer.oscilloscope = None
                        global_visualizer.connected = False
                        print("Соединение с осциллографом разорвано.")
                    await websocket.send(
                        json.dumps(
                            {
                                'type': 'status',
                                'data': {'status': 'measurements_stopped'},
                            }
                        )
                    )

                elif action == 'start_oscilloscope':
                    if not global_visualizer:
                        global_visualizer = OscilloscopeVisualizer()
                    if not global_visualizer.connected:
                        global_visualizer.connect_to_oscilloscope()
                    is_oscilloscope_running = True
                    if not oscilloscope_task or oscilloscope_task.done():
                        loop = asyncio.get_running_loop()
                        oscilloscope_task = loop.create_task(
                            run_oscilloscope()
                        )
                    await websocket.send(
                        json.dumps(
                            {
                                'type': 'status',
                                'data': {'status': 'oscilloscope_started'},
                            }
                        )
                    )

                elif action == 'stop_oscilloscope':
                    is_oscilloscope_running = False
                    if global_visualizer and global_visualizer.oscilloscope:
                        try:
                            global_visualizer.oscilloscope.close()
                        except Exception as e:
                            print(
                                f"Ошибка при разрыве соединения с осциллографом: {e}"
                            )
                        global_visualizer.oscilloscope = None
                        global_visualizer.connected = False
                        print("Соединение с осциллографом разорвано.")
                    await websocket.send(
                        json.dumps(
                            {
                                'type': 'status',
                                'data': {'status': 'oscilloscope_stopped'},
                            }
                        )
                    )

                elif action == 'start_multimeter':
                    if not global_multimeter:
                        global_multimeter = UT803Reader()
                        global_multimeter.connect_serial() or global_multimeter.connect_hid()
                    is_multimeter_running = True
                    if not multimeter_task or multimeter_task.done():
                        loop = asyncio.get_running_loop()
                        multimeter_task = loop.create_task(run_multimeter())
                    await websocket.send(
                        json.dumps(
                            {
                                'type': 'status',
                                'data': {'status': 'multimeter_started'},
                            }
                        )
                    )

                elif action == 'stop_multimeter':
                    is_multimeter_running = False
                    if global_multimeter:
                        try:
                            global_multimeter.disconnect()
                        except Exception as e:
                            print(
                                f"Ошибка при разрыве соединения с мультиметром: {e}"
                            )
                        global_multimeter = None
                        print("Соединение с мультиметром разорвано.")
                    await websocket.send(
                        json.dumps(
                            {
                                'type': 'status',
                                'data': {'status': 'multimeter_stopped'},
                            }
                        )
                    )

                elif action == 'get_multimeter_data':
                    asyncio.create_task(
                        handle_get_multimeter_data(websocket, id(websocket))
                    )

                elif action == 'get_uart_data':
                    try:
                        await websocket.send(
                            json.dumps(
                                {
                                    'type': 'sensor_data',
                                    'data': current_uart_data,
                                }
                            )
                        )
                        print(
                            f"Sent UART data on request: {current_uart_data}"
                        )
                    except Exception as e:
                        print(f"Error sending UART data on request: {e}")

                elif action == 'get_oscilloscope_data':
                    asyncio.create_task(
                        handle_get_oscilloscope_data(websocket)
                    )

                elif action == 'set_channel_settings':
                    channel = data.get('channel')
                    settings = data.get('settings', {})
                    if global_visualizer and channel and settings:
                        result = global_visualizer.set_channel_settings(
                            channel, settings
                        )
                        await websocket.send(
                            json.dumps(
                                {
                                    'type': 'channel_settings',
                                    'channel': channel,
                                    'settings': result,
                                }
                            )
                        )

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
                    lambda: (
                        global_multimeter.read_serial()
                        if global_multimeter.serial_port
                        else global_multimeter.read_hid()
                    ),
                )

                if measurement and human_readable:
                    last_live_multimeter_data = measurement
                    print(f"Отправка данных мультиметра: {measurement}")
                    if active_websockets:
                        await send_to_all_websocket_clients(
                            {"type": "multimeter", "data": measurement}
                        )
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


def run_http_server():
    try:
        server_address = ('0.0.0.0', HTTP_PORT)
        httpd = HTTPServer(server_address, CustomHTTPRequestHandler)
        print(f"HTTP-сервер запущен на http://0.0.0.0:{HTTP_PORT}")
        httpd.serve_forever()
    except Exception as e:
        print(f"Ошибка запуска HTTP-сервера: {e}")
        traceback.print_exc()


async def main():
    """Main function to start the server"""
    global is_multimeter_running, is_measurement_active, http_event_loop

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
            compression=None,
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


async def handle_get_multimeter_data(websocket, connection_id):
    global last_live_multimeter_data, last_multimeter_values
    if 'last_live_multimeter_data' in globals() and last_live_multimeter_data:
        new_value = last_live_multimeter_data['value']
        last_value = last_multimeter_values.get(connection_id)
        if last_value != new_value:
            last_multimeter_values[connection_id] = new_value
            try:
                await websocket.send(
                    json.dumps(
                        {
                            'type': 'multimeter',
                            'data': last_live_multimeter_data,
                        }
                    )
                )
            except Exception:
                pass


async def handle_get_oscilloscope_data(websocket):
    try:
        if global_visualizer and global_visualizer.connected:
            oscilloscope_data = await global_visualizer.get_oscilloscope_data()
            await websocket.send(json.dumps(oscilloscope_data))
    except Exception as e:
        print(f"Ошибка в handle_get_oscilloscope_data: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description='Сервер для работы с осциллографом и мультиметром'
    )
    parser.add_argument(
        '--reset-db',
        action='store_true',
        help='Принудительно сбросить базу данных (удалить все данные)',
    )
    parser.add_argument(
        '--check-db',
        action='store_true',
        help='Проверить структуру базу данных',
    )

    args = parser.parse_args()

    if args.reset_db:
        print("ВНИМАНИЕ: Выполняется принудительный сброс базы данных!")
        print("Все существующие данные будут удалены!")
        confirm = input("Вы уверены? (y/N): ")
        if confirm.lower() in ['y', 'yes', 'да']:
            print("База данных сброшена.")
        else:
            print("Сброс базы данных отменен.")
        sys.exit(0)

    if args.check_db:
        print("Проверка структуры базы данных...")
        try:
            session = Session()
            oscilloscope_count = session.query(OscilloscopeData).count()
            multimeter_count = session.query(MultimeterData).count()
            session.close()
            print(f"База данных в порядке:")
            print(f"  - Записей осциллографа: {oscilloscope_count}")
            print(f"  - Записей мультиметра: {multimeter_count}")
        except Exception as e:
            print(f"Ошибка структуры базы данных: {e}")
            print("Рекомендуется выполнить сброс: python3 main.py --reset-db")
        sys.exit(0)

    if not os.path.exists('frontend/index.html'):
        print("Предупреждение: файл index.html не найден!")
    if not os.path.exists('frontend/src/app.js'):
        print("Предупреждение: файл app.js не найден!")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nСервер остановлен пользователем")
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        traceback.print_exc()
        sys.exit(1)

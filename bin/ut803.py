"""
UT803 Multimeter Reader - Supports both HID and RS232 interfaces
"""

import argparse
import asyncio
import json
import logging
import socket
import sys
import time
from datetime import datetime
from typing import Optional, Tuple

import hid
import serial
import websockets

logging.basicConfig(
    level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('UT803')

sys.stdout.reconfigure(line_buffering=True)


class UT803Reader:
    def __init__(self, measurement_time: int = 10, force_save: bool = False):
        self.device = None
        self.serial_port = None
        self.websocket = None
        self.measurement_time = measurement_time
        self.force_save = force_save
        self.start_time = None
        self.last_reading = None
        self.is_running = True

    def connect_serial(self, port: str = '/dev/ttyUSB0') -> bool:
        """Connect to the multimeter via RS232"""
        try:
            self.serial_port = serial.Serial(
                port=port,
                baudrate=19200,
                bytesize=serial.SEVENBITS,
                parity=serial.PARITY_ODD,
                stopbits=serial.STOPBITS_ONE,
                timeout=1,
            )
            self.serial_port.setDTR(True)
            self.serial_port.setRTS(False)
            self.serial_port.reset_input_buffer()
            self.serial_port.reset_output_buffer()

            time.sleep(0.5)
            self.serial_port.write(b'*IDN?\n')
            response = self.serial_port.readline()
            if response:
                logger.info(f"Successfully connected to RS232 port {port}")
                return True
            else:
                logger.error("No response from device")
                return False

        except serial.SerialException as e:
            logger.error(f"Failed to connect to RS232: {str(e)}")
            return False

    def connect_hid(self) -> bool:
        """Connect to the multimeter via HID"""
        try:
            for vid, pid in [(0x1A86, 0xE008), (0x04FA, 0x2490)]:
                devices = hid.enumerate(vid, pid)
                if devices:
                    self.device = hid.device()
                    self.device.open(vid, pid)
                    self.device.set_nonblocking(1)

                    time.sleep(0.5)
                    data = self.device.read(64, timeout_ms=1000)
                    if data:
                        logger.info(
                            f"Successfully connected to HID device {vid:04X}:{pid:04X}"
                        )
                        return True
                    else:
                        logger.error("No response from HID device")
                        self.device.close()
                        self.device = None
                        return False

            logger.error("No HID device found")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to HID: {str(e)}")
            if self.device:
                try:
                    self.device.close()
                except:
                    pass
                self.device = None
            return False

    async def connect_websocket(self):
        """Connect to WebSocket server"""
        max_retries = 5
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                logger.info(
                    f"Attempting to connect to WebSocket server (attempt {attempt + 1}/{max_retries})..."
                )

                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                result = sock.connect_ex(('127.0.0.1', 8767))
                sock.close()

                if result != 0:
                    logger.error(
                        f"WebSocket server is not running on port 8767 (error code: {result})"
                    )
                    logger.error("Please make sure main.py is running")
                    if attempt < max_retries - 1:
                        logger.info(f"Retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                    continue

                logger.info(
                    "Server is running, attempting WebSocket connection..."
                )
                self.websocket = await websockets.connect(
                    'ws://127.0.0.1:8767',
                    ping_interval=None,
                    ping_timeout=None,
                    close_timeout=5,
                    max_size=None,
                    compression=None,
                )
                logger.info("Successfully connected to WebSocket server")
                return True

            except ConnectionRefusedError:
                logger.error(
                    "Connection refused. Make sure the WebSocket server (main.py) is running."
                )
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error(
                        "Failed to connect after all attempts. Please start the WebSocket server first."
                    )
                    return False
            except Exception as e:
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries} failed: {str(e)}"
                )
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error(
                        "Failed to connect to WebSocket server after all attempts"
                    )
                    return False

    def decode_ut803_data(self, data) -> tuple:
        """
        Универсальный декодер: определяет формат (бинарный/ASCII) и парсит оба варианта.
        data: bytes или str
        """
        if isinstance(data, bytes) and len(data) == 11:
            return self._decode_binary_packet(data)
        if isinstance(data, str) and len(data) == 11:
            try:
                b = bytes([ord(x) for x in data])
                return self._decode_binary_packet(b)
            except Exception:
                pass
        if isinstance(data, str) and ';' in data:
            return self._decode_ascii_protocol(data)
        if isinstance(data, bytes):
            try:
                s = data.decode('ascii', errors='ignore').strip()
                if ';' in s:
                    return self._decode_ascii_protocol(s)
            except Exception:
                pass
        return None, 'Unknown data format'

    def _decode_binary_protocol(self, data: str) -> Tuple[dict, str]:
        """Decode 11-byte binary protocol packet"""
        try:
            packet = data[:-2]

            if len(packet) != 9:
                return None, "Invalid packet length"

            exponent = ord(packet[0]) - 48
            base_value = int(packet[1:5])
            measurement_type = packet[5]
            flags = packet[6:9]

            # Декодируем флаги
            flag1 = ord(flags[0]) - 48
            flag2 = ord(flags[1]) - 48
            flag3 = ord(flags[2]) - 48

            measurement_info = self._get_measurement_type_info(
                measurement_type
            )
            if not measurement_info:
                return None, f"Unknown measurement type: {measurement_type}"

            value = self._calculate_value(
                base_value, exponent, measurement_info['offset']
            )

            unit = measurement_info['unit']
            mode = self._determine_mode(flag3, measurement_info)
            measure_type = measurement_info['type']

            is_negative = (flag1 & 0x4) != 0
            is_overload = (flag1 & 0x1) != 0
            is_auto_range = (flag3 & 0x2) != 0
            is_ac = (flag3 & 0x4) != 0
            is_dc = (flag3 & 0x8) != 0

            if is_negative:
                value = -value

            if is_overload:
                value_str = "OL"
            else:
                value_str = f"{value:.6f}".rstrip('0').rstrip('.')

            current_time = datetime.now()
            timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

            json_data = {
                'timestamp': timestamp,
                'value': value_str,
                'unit': unit,
                'mode': mode,
                'range_str': "AUTO" if is_auto_range else "MANUAL",
                'measure_type': measure_type,
                'raw_data': {
                    'packet': data,
                    'exponent': exponent,
                    'base_value': base_value,
                    'measurement_type': measurement_type,
                    'flags': flags,
                    'is_negative': is_negative,
                    'is_overload': is_overload,
                    'is_auto_range': is_auto_range,
                    'is_ac': is_ac,
                    'is_dc': is_dc,
                },
            }

            human_readable = f"[{timestamp}] {value_str} {unit} {mode} {'AUTO' if is_auto_range else 'MANUAL'} [{measure_type}]"
            if is_overload:
                human_readable = f"[{timestamp}] OL {unit} {mode} {'AUTO' if is_auto_range else 'MANUAL'} [{measure_type}]"

            return json_data, human_readable

        except Exception as e:
            logger.error(f"Error decoding binary protocol: {str(e)}")
            return None, f"Binary decode error: {str(e)}"

    def _decode_ascii_protocol(self, data: str) -> Tuple[dict, str]:
        """Decode ASCII protocol (legacy format)"""
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
                    if function_code.startswith('8'):
                        value = raw_value / 1000
                    else:
                        value = raw_value / 1000
                    value = f"{value:.3f}"
            except ValueError:
                value = "Error"

            mode = "DC"
            unit = "В"
            measure_type = "Вольтметр"

            if function_code.startswith('8'):
                if '06' in function_code:
                    unit = "В"
                    measure_type = "Вольтметр"
                    mode = "AC"

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
                    'raw_data': data,
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
                    'raw_data': data,
                }
                human_readable = f"[{timestamp}] {value} {unit} {mode} AUTO [{measure_type}]"
                return json_data, human_readable

        except Exception as e:
            logger.error(f"Error decoding ASCII protocol: {str(e)}")
            return None, f"ASCII decode error: {str(e)}"

    def _get_measurement_type_info(self, measurement_type: str):
        """Get measurement type information based on protocol"""
        measurement_types = {
            '1': {'type': 'Diode Test', 'unit': 'V', 'offset': 0},
            '2': {'type': 'Frequency', 'unit': 'Hz', 'offset': 0},
            '3': {'type': 'Resistance', 'unit': 'Ω', 'offset': 1},
            '4': {'type': 'Temperature', 'unit': '°C', 'offset': 0},
            '5': {'type': 'Continuity', 'unit': 'Ω', 'offset': 1},
            '6': {'type': 'Capacitance', 'unit': 'nF', 'offset': 12},
            '9': {'type': 'Current', 'unit': 'A', 'offset': 2},
            ';': {'type': 'Voltage', 'unit': 'V', 'offset': 3},
            '=': {'type': 'Current', 'unit': 'µA', 'offset': 1},
            '|': {'type': 'hFE', 'unit': '', 'offset': 0},
            '>': {'type': 'Current', 'unit': 'mA', 'offset': 2},
        }
        return measurement_types.get(measurement_type)

    def _calculate_value(
        self,
        base_value: int,
        exponent: int,
        offset: int,
        measurement_type=None,
    ):
        """Calculate actual value from base value and exponent with offset. Для nF (ёмкость) — base_value / 1000."""
        try:
            if measurement_type == '6':
                return base_value / 1000
            adjusted_exponent = exponent - offset
            value = base_value * (10**adjusted_exponent)
            return value
        except Exception as e:
            print(f"[Мультиметр] Error calculating value: {str(e)}")
            return 0.0

    def _decode_binary_packet(self, packet: bytes):
        if len(packet) != 11:
            return None, 'Invalid binary packet length'

        def sd(b):
            if 0x30 <= b <= 0x39:
                return b - 0x30
            elif 0x3A <= b <= 0x3F:
                return b - 0x30
            elif 0x0A <= b <= 0x29:
                return b - 0x0A
            else:
                return 0

        exponent = sd(packet[0])
        base_value = (
            sd(packet[1]) * 1000
            + sd(packet[2]) * 100
            + sd(packet[3]) * 10
            + sd(packet[4])
        )
        measurement_type = chr(packet[5]) if 32 <= packet[5] <= 127 else '?'
        flag1 = sd(packet[6])
        flag2 = sd(packet[7])
        flag3 = sd(packet[8])
        measurement_info = self._get_measurement_type_info(measurement_type)
        if not measurement_info:
            return None, f"Unknown measurement type: {measurement_type}"
        value = self._calculate_value(
            base_value,
            exponent,
            measurement_info['offset'],
            measurement_type=(
                packet[5] if isinstance(packet[5], str) else chr(packet[5])
            ),
        )
        unit = measurement_info['unit']
        mode = self._determine_mode(flag3, measurement_info)
        measure_type = measurement_info['type']
        is_negative = (flag1 & 0x4) != 0
        is_overload = (flag1 & 0x1) != 0
        is_auto_range = (flag3 & 0x2) != 0
        is_ac = (flag3 & 0x4) != 0
        is_dc = (flag3 & 0x8) != 0
        if is_negative:
            value = -value
        if is_overload:
            value_str = "OL"
        else:
            value_str = f"{value:.6f}".rstrip('0').rstrip('.')
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        json_data = {
            'timestamp': timestamp,
            'value': value_str,
            'unit': unit,
            'mode': mode,
            'range_str': "AUTO" if is_auto_range else "MANUAL",
            'measure_type': measure_type,
            'raw_data': {
                'packet': list(packet),
                'exponent': exponent,
                'base_value': base_value,
                'measurement_type': measurement_type,
                'flags': [flag1, flag2, flag3],
                'is_negative': is_negative,
                'is_overload': is_overload,
                'is_auto_range': is_auto_range,
                'is_ac': is_ac,
                'is_dc': is_dc,
            },
        }
        human_readable = f"[{timestamp}] {value_str} {unit} {mode} {'AUTO' if is_auto_range else 'MANUAL'} [{measure_type}]"
        if is_overload:
            human_readable = f"[{timestamp}] OL {unit} {mode} {'AUTO' if is_auto_range else 'MANUAL'} [{measure_type}]"
        return json_data, human_readable

    def _determine_mode(self, flag3: int, measurement_info: dict) -> str:
        """Determine measurement mode based on flags"""
        is_ac = (flag3 & 0x4) != 0
        is_dc = (flag3 & 0x8) != 0

        if measurement_info['type'] == 'Voltage':
            if is_ac:
                return 'AC'
            elif is_dc:
                return 'DC'
            else:
                return 'DC'
        elif measurement_info['type'] == 'Current':
            if is_ac:
                return 'AC'
            elif is_dc:
                return 'DC'
            else:
                return 'DC'
        elif measurement_info['type'] == 'Temperature':

            return '°C'
        else:
            return 'DC'

    async def send_measurement(self, data: dict):
        """Send measurement data to WebSocket server"""
        if self.websocket and data:
            try:
                data['force_save'] = self.force_save
                logger.info(
                    f"Отправка данных мультиметра с force_save={self.force_save}: {data}"
                )
                await self.websocket.send(json.dumps(data))
            except Exception as e:
                logger.error(f"Error sending data: {str(e)}")

    def read_serial(self) -> tuple:
        if not self.serial_port:
            return None, None
        try:
            self.serial_port.reset_input_buffer()
            data = self.serial_port.read(11)
            if data and len(data) == 11:
                json_data, human_readable = self.decode_ut803_data(data)
                if json_data and json_data.get('value') == self.last_reading:
                    return None, None
                self.last_reading = (
                    json_data.get('value') if json_data else None
                )
                return json_data, human_readable
            data = self.serial_port.readline()
            if data:
                try:
                    decoded_data = data.decode('ascii').strip()
                except Exception:
                    return None, None
                json_data, human_readable = self.decode_ut803_data(
                    decoded_data
                )
                if json_data and json_data.get('value') == self.last_reading:
                    return None, None
                self.last_reading = (
                    json_data.get('value') if json_data else None
                )
                return json_data, human_readable
        except Exception as e:
            logger.error(f"Error reading from RS232: {str(e)}")
        return None, None

    def read_hid(self) -> tuple:
        if not self.device:
            return None, None
        try:
            data = self.device.read(11, timeout_ms=1000)
            if data and len(data) == 11:
                json_data, human_readable = self.decode_ut803_data(bytes(data))
                if json_data and json_data.get('value') == self.last_reading:
                    return None, None
                self.last_reading = (
                    json_data.get('value') if json_data else None
                )
                return json_data, human_readable
        except Exception as e:
            logger.error(f"Error reading from HID: {str(e)}")
        return None, None

    async def receive_messages(self):
        """Receive messages from WebSocket server"""
        if not self.websocket:
            return

        try:
            while self.is_running:
                try:
                    message = await self.websocket.recv()
                    data = json.loads(message)

                    if "status" in data and data["status"] == "complete":
                        logger.info(
                            f"Received completion message. Total measurements: {data.get('count', 0)}"
                        )
                        self.is_running = False
                        break
                except websockets.exceptions.ConnectionClosed:
                    break
                except Exception as e:
                    logger.error(f"Error receiving message: {str(e)}")
                    break
        except Exception as e:
            logger.error(f"Error in receive_messages: {str(e)}")

    async def run(self):
        """Main measurement loop"""
        if not await self.connect_websocket():
            return

        self.start_time = time.time()
        self.is_running = True

        try:
            while self.is_running and (
                time.time() - self.start_time < self.measurement_time
            ):
                measurement = None
                human_readable = None

                if self.serial_port:
                    measurement, human_readable = self.read_serial()
                elif self.device:
                    measurement, human_readable = self.read_hid()

                if measurement and human_readable:
                    try:
                        await self.send_measurement(measurement)
                        print(human_readable)
                    except Exception as e:
                        logger.error(f"Error sending data: {str(e)}")

                        if not await self.connect_websocket():
                            break

                await asyncio.sleep(0.1)

        except KeyboardInterrupt:
            logger.info("\nStopping measurement...")
        finally:
            self.is_running = False
            await self.disconnect()

    async def disconnect(self):
        """Disconnect from all interfaces"""
        if self.serial_port:
            self.serial_port.close()
            self.serial_port = None
        if self.device:
            self.device.close()
            self.device = None
        if self.websocket:
            await self.websocket.close()
            self.websocket = None


def parse_args():
    parser = argparse.ArgumentParser(description='UT803 Multimeter Reader')
    parser.add_argument(
        '--measurement_time',
        type=int,
        default=10,
        help='Measurement time in seconds (default: 10)',
    )
    parser.add_argument(
        '--force-save',
        action='store_true',
        help='Force save measurements to database',
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    reader = UT803Reader(
        measurement_time=args.measurement_time, force_save=args.force_save
    )

    if reader.connect_serial():
        logger.info("Reading from RS232 interface...")
        await reader.run()
    elif reader.connect_hid():
        logger.info("Reading from HID interface...")
        await reader.run()
    else:
        logger.error("Failed to connect to either interface")


if __name__ == "__main__":
    asyncio.run(main())

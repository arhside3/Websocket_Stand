import hid
import serial

global_multimeter = None
last_multimeter_values = {}

is_multimeter_running = True
oscilloscope_task = None
multimeter_task = None
active_websockets = set()
is_measurement_active = True
current_test_number = None


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
                timeout=1,
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
                    print(
                        f"[Мультиметр] Successfully connected to HID device {vid:04X}:{pid:04X}"
                    )
                    self.connected = True
                    return True
            print("[Мультиметр] No HID device found")
            return False
        except Exception as e:
            print(f"[Мультиметр] Failed to connect to HID: {str(e)}")
            return False

    def decode_ut803_data(self, data):
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

    def _decode_binary_packet(self, packet: bytes):
        """
        Декодирует 11-байтовый бинарный пакет UT803 (super-decimal)
        """
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

    def read_serial(self):
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
            print(f"[Мультиметр] Error reading from RS232: {str(e)}")
        return None, None

    def read_hid(self):
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

    def _determine_mode(self, flag3: int, measurement_info):
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

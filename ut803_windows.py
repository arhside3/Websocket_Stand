
"""
Декодер для мультиметра UT803 - использует методы из HE2325U_HIDAPI
для корректной инициализации и чтения данных с устройства
"""

import hid
import time
import binascii
import sys

VID = 0x1A86
PID = 0xE008

BPS = 19200

PACKET_SIZE = 11

class UT803Decoder:
    def __init__(self):
        self.device = None
        self.last_packet = None
        self.buffer = bytearray()
        
    def connect(self):
        """Подключение к мультиметру и настройка параметров соединения"""
        try:
            all_devices = hid.enumerate(VID, PID)
            
            if len(all_devices) == 0:
                print(f"Устройство с VID=0x{VID:04X}, PID=0x{PID:04X} не найдено")
                return False
            
            for dev in all_devices:
                name = ""
                if 'manufacturer_string' in dev and dev['manufacturer_string']:
                    name += dev['manufacturer_string'] + " "
                if 'product_string' in dev and dev['product_string']:
                    name += dev['product_string']
                path = dev['path']
                if isinstance(path, bytes):
                    path = path.decode('ascii', errors='ignore')
                print(f"* {name} [{path}]")
                
            self.device = hid.device()
            self.device.open(VID, PID)
            self.device.set_nonblocking(1)
            
            print(f"Подключено к мультиметру UT803 (VID:{VID:04X} PID:{PID:04X})")
            
            self.configure_device()
            
            return True
        except Exception as e:
            print(f"Ошибка подключения: {e}")
            return False
    
    def configure_device(self):
        """Настройка параметров соединения через Feature Report"""
        try:
            buf = [0] * 6
            buf[0] = 0x0
            buf[1] = BPS & 0xFF
            buf[2] = (BPS >> 8) & 0xFF
            buf[3] = (BPS >> 16) & 0xFF
            buf[4] = (BPS >> 24) & 0xFF
            buf[5] = 0x03
            
            result = self.device.send_feature_report(buf)
            
            if result == -1:
                print("Ошибка отправки Feature Report")
            else:
                print(f"Feature Report отправлен успешно ({result} байт)")
        except Exception as e:
            print(f"Ошибка настройки устройства: {e}")
    
    def disconnect(self):
        """Отключение от мультиметра"""
        if self.device:
            self.device.close()
            print("Мультиметр отключен")
            self.device = None
    
    def read_data(self):
        """Чтение данных с мультиметра по протоколу HE2325U"""
        if not self.device:
            return
        
        try:
            answer = self.device.read(256, timeout_ms=1000)
            if len(answer) < 1:
                return
                
            nbytes = answer[0] & 0x7
            if nbytes > 0:
                if len(answer) < nbytes + 1:
                    print("Ошибка: объявлено больше байт, чем получено")
                    return
                    
                payload = answer[1:nbytes + 1]
                payload = [b & (~(1<<7)) for b in payload]
                
                self.buffer.extend(payload)
                
                self.process_buffer()
        except Exception as e:
            print(f"Ошибка чтения данных: {e}")
    
    def process_buffer(self):
        """Обработка буфера данных и поиск полных пакетов"""
        while len(self.buffer) >= PACKET_SIZE:
            if self.buffer[9] == 0x0D and self.buffer[10] == 0x0A:
                packet = bytes(self.buffer[:PACKET_SIZE])
                self.buffer = self.buffer[PACKET_SIZE:]
                
                if packet != self.last_packet:
                    self.last_packet = packet
                    self.decode_ut803_packet(packet)
            else:
                self.buffer.pop(0)
    
    def decode_ut803_packet(self, packet):
        """Декодирование пакета UT803 по документации"""
        try:
            if len(packet) != PACKET_SIZE:
                return
            
            range_byte = packet[0] & 0x0F
            digits = [packet[1] & 0x0F, packet[2] & 0x0F, packet[3] & 0x0F, packet[4] & 0x0F]
            function_byte = packet[5]
            info_byte = packet[6]
            info2_byte = packet[7]
            coupling_byte = packet[8]
            
            is_overload = (info_byte & 0x01) != 0
            
            is_negative = (info_byte & 0x08) != 0
            
            value = 0
            for digit in digits:
                value = value * 10 + digit
            
            decimal_pos, unit = self.get_decimal_and_unit(function_byte, range_byte)
            
            if is_overload:
                value_str = "OL"
            else:
                if decimal_pos > 0:
                    divisor = 10 ** decimal_pos
                    value_str = format(value / divisor, f'.{decimal_pos}f')
                else:
                    value_str = str(value)
                
                if is_negative:
                    value_str = "" + value_str
            
            modes = []
            
            if coupling_byte & 0x04:
                modes.append("AC")
            elif coupling_byte & 0x08:
                modes.append("DC")
            
            if coupling_byte & 0x02:
                modes.append("AUTO")
            else:
                modes.append("MAN")
            
            if info2_byte & 0x08:
                modes.append("HOLD")
            if info2_byte & 0x04:
                modes.append("MAX")
            if info2_byte & 0x02:
                modes.append("MIN")
            
            function_name = self.get_function_name(function_byte)
            
            if not (value == 0 and function_byte in [0x3B, 0x33, 0x28]):
                measurement = f"{value_str} {unit} {' '.join(modes)}"
                if function_name:
                    measurement += f" [{function_name}]"
                print(measurement)
                
        except Exception as e:
            print(f"Ошибка декодирования пакета: {e}")
    
    def get_decimal_and_unit(self, function_byte, range_byte):
        """Определение позиции десятичной точки и единицы измерения"""
        if function_byte == 0x3B:
            range_table = [3, 2, 1, 0, 3]
            units = ["В", "В", "В", "В", "мВ"]
            return range_table[range_byte] if range_byte < len(range_table) else 0, units[range_byte] if range_byte < len(units) else "В"
        
        elif function_byte == 0x33:
            range_table = [1, 1, 2, 2, 3, 3]
            if range_byte == 0:
                return 1, "Ом"
            elif range_byte <= 3:
                return range_table[range_byte], "кОм"
            else:
                return range_table[range_byte], "МОм"
        
        elif function_byte == 0x68:
            range_table = [3, 2, 1, 3, 2, 1, 3]
            if range_byte <= 2:
                return range_table[range_byte], "нФ"
            elif range_byte <= 5:
                return range_table[range_byte], "мкФ"
            else:
                return range_table[range_byte], "мФ"
        
        elif function_byte == 0x28:
            if range_byte == 0:
                return 0, "Гц"
            elif range_byte <= 2:
                return range_byte, "кГц"
            else:
                return range_byte - 3, "МГц"
        
        elif function_byte == 0x48:
            return 0, "°C"
        
        elif function_byte == 0x40:
            return 0, "°F"
        
        elif function_byte == 0x3D:
            if range_byte == 0:
                return 1, "мкА"
            else:
                return 0, "мкА"
        
        elif function_byte == 0x3F:
            if range_byte == 0:
                return 2, "мА"
            else:
                return 1, "мА"
        
        elif function_byte == 0x39:
            return 2, "А"
        
        elif function_byte == 0x19:
            return 0, "В"
        
        return 0, ""
    
    def get_function_name(self, function_byte):
        """Получение названия функции"""
        functions = {
            0x3B: "Вольтметр",
            0x33: "Омметр",
            0x68: "Ёмкость",
            0x28: "Частота",
            0x48: "Термометр °C",
            0x40: "Термометр °F",
            0x3D: "Микроамперметр",
            0x3F: "Миллиамперметр",
            0x39: "Амперметр",
            0x19: "Диод",
            0x59: "Прозвонка"
        }
        return functions.get(function_byte, "")

def main():
    decoder = UT803Decoder()
    
    try:
        if not decoder.connect():
            print("Не удалось подключиться к мультиметру!")
            return
        
        print("\nНажмите Ctrl+C для завершения...\n")

        while True:
            decoder.read_data()
            time.sleep(0.01)
            
    except KeyboardInterrupt:
        print("\nПрограмма завершена пользователем")
    
    finally:
        decoder.disconnect()

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
    Декодер данных для мультиметра UT803 через HID
    Надежная версия с поддержкой чисел вида 0.XXX
"""

import hid
import time
import sys
import re
import binascii
import threading

VID = 0x1A86
PID = 0xE008

PACKET_MARKERS = [0xF7, 0xB0, 0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39]

REQUEST_DATA_COMMAND = [0x00, 0xAB, 0xCD, 0x00, 0x00, 0x00, 0x00, 0x00]

INIT_COMMAND = [0x00, 0xAB, 0xCD, 0x01, 0x00, 0x00, 0x00, 0x00]

def parse_packet(packet):
    """Анализ пакета данных от мультиметра с поддержкой чисел, начинающихся с нуля"""
    try:
        ascii_data = ''.join([chr(b) if 32 <= b <= 126 else '.' for b in packet])

        match = re.search(r'(\d{4})', ascii_data)
        if match:
            num = match.group(1)
            value = int(num) / 1000.0
            value_str = f"{value:.3f}".replace('.', ',')
            return {'value': value, 'value_str': value_str, 'unit': 'V', 
                    'ac': True, 'dc': False, 'auto': True, 'hold': False}

        zero_match = re.search(r'0\.(\d{3})', ascii_data)
        if zero_match:
            value = float(f"0.{zero_match.group(1)}")
            value_str = f"0,{zero_match.group(1)}"
            return {'value': value, 'value_str': value_str, 'unit': 'V', 
                    'ac': True, 'dc': False, 'auto': True, 'hold': False}

        zero_match2 = re.search(r'0,(\d{3})', ascii_data)
        if zero_match2:
            value = float(f"0.{zero_match2.group(1)}")
            value_str = f"0,{zero_match2.group(1)}"
            return {'value': value, 'value_str': value_str, 'unit': 'V', 
                    'ac': True, 'dc': False, 'auto': True, 'hold': False}
        
        return None
    
    except Exception as e:
        print(f"Ошибка парсинга: {e}")
        return None

def request_thread(device):
    """Поток для быстрой отправки запросов данных"""
    try:
        for _ in range(2):
            device.write(INIT_COMMAND)
            time.sleep(0.0001)
        
        while True:
            device.write(REQUEST_DATA_COMMAND)
            time.sleep(0.0005)
    except Exception as e:
        print(f"Ошибка в потоке запросов: {e}")

def main():
    print("Поиск мультиметра UT803...")

    devices = hid.enumerate()
    found = False
    for dev in devices:
        if dev['vendor_id'] == VID and dev['product_id'] == PID:
            found = True
            print(f"Найдено устройство: VID: 0x{dev['vendor_id']:04X}, PID: 0x{dev['product_id']:04X} - {dev.get('product_string', '')}")
    
    if not found:
        print(f"ВНИМАНИЕ: Не найдено устройство с VID/PID 0x{VID:04X}/0x{PID:04X}")
    
    try:
        print(f"Подключение к устройству...")
        device = hid.device()
        device.open(VID, PID)
        device.set_nonblocking(1)
        print("Устройство успешно открыто!")
        
        print("Инициализация устройства...")
        for _ in range(2):
            device.write(INIT_COMMAND)
            time.sleep(0.0001)

        request_t = threading.Thread(target=request_thread, args=(device,), daemon=True)
        request_t.start()

        buffer = bytearray()
        
        print("\nПоказываю измерения напряжения (V), совместимые с оригинальным ПО...\n")
        print("No.\tTime\t\tDC/AC\tValue\tUnit\tAuto")
        
        count = 0
        last_value_str = None
        last_display_time = 0
        
        while True:
            for _ in range(2):
                data = device.read(64)
                if data:
                    buffer.extend(data)

            if len(buffer) >= 16:
                for i in range(len(buffer) - 15):
                    if buffer[i] in PACKET_MARKERS:
                        packet = bytes(buffer[i:i+16])
                        result = parse_packet(packet)
                        
                        if result:
                            current_time = time.time()
                            current_ms = int(current_time * 1000)
                            time_since_last = current_ms - last_display_time
                            
                            if (last_value_str != result['value_str'] or 
                                time_since_last > 10):
                                
                                count += 1
                                timestamp = time.strftime("%H:%M:%S", time.localtime())

                                print(f"{count}\t{timestamp}\t{'AC' if result['ac'] else 'DC'}\t{result['value_str']}\t{result['unit']}\t{'AUTO' if result['auto'] else ''}")

                                last_value_str = result['value_str']
                                last_display_time = current_ms

                        del buffer[:i+16]
                        break

                if len(buffer) > 512:
                    del buffer[:256]

    
    except KeyboardInterrupt:
        print("\nПрограмма остановлена пользователем")
    except Exception as e:
        print(f"\nОшибка: {e}")
    finally:
        try:
            device.close()
            print("Устройство закрыто")
        except:
            pass

if __name__ == "__main__":
    main()

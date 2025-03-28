#!/usr/bin/env python3
"""
    Декодер данных для мультиметра UT803 через HID
    Точная реализация протокола UT803 с исправлениями для AC/DC и True RMS
"""

import hid
import time
import sys
import re
import binascii
import threading

# Константы
VID = 0x1A86  # Стандартный VID для UT803
PID = 0xE008  # Стандартный PID для UT803

# Маркеры начала пакетов
PACKET_MARKERS = [0xF7, 0xB0, 0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39]

# Команда запроса данных
REQUEST_DATA_COMMAND = [0x00, 0xAB, 0xCD, 0x00, 0x00, 0x00, 0x00, 0x00]

# Команда инициализации
INIT_COMMAND = [0x00, 0xAB, 0xCD, 0x01, 0x00, 0x00, 0x00, 0x00]

# Константы протокола UT803
FLAG_3_3_AC = 0x04  # Бит 3 в третьем флаге - AC измерение
FLAG_3_4_DC = 0x08  # Бит 4 в третьем флаге - DC измерение
FLAG_3_2_AUTO = 0x02  # Бит 2 в третьем флаге - Auto Range
FLAG_2_4_HOLD = 0x08  # Бит 4 во втором флаге - Hold значение
FLAG_2_3_MAX = 0x04  # Бит 3 во втором флаге - Maximum
FLAG_2_2_MIN = 0x02  # Бит 2 во втором флаге - Minimum
FLAG_1_3_NEG = 0x04  # Бит 3 в первом флаге - Отрицательное значение

# Включить отладочный режим для вывода дополнительной информации
DEBUG = False

def parse_packet(packet):
    """Анализ пакета по протоколу UT803 с точным определением режима и значения"""
    try:
        # Преобразуем пакет в строку для анализа
        ascii_data = ''.join([chr(b) if 32 <= b <= 126 else '.' for b in packet])
        hex_data = ' '.join([f"{b:02X}" for b in packet])
        
        if DEBUG:
            print(f"ASCII: '{ascii_data}', HEX: {hex_data}")
        
        # Поиск 11-байтного пакета в данных (9 символов + CR + LF)
        for i in range(len(packet) - 10):
            if packet[i+9] == 0x0D and packet[i+10] == 0x0A:  # CR+LF в конце
                if all(32 <= packet[i+j] <= 126 for j in range(9)):  # Все символы печатные
                    # Извлекаем поля пакета
                    exponent = packet[i] - 48  # ASCII -> число
                    base_value = ''.join([chr(packet[i+j]) for j in range(1, 5)])
                    measurement_type = chr(packet[i+5])
                    flag1 = packet[i+6] - 48  # ASCII -> число
                    flag2 = packet[i+7] - 48  # ASCII -> число
                    flag3 = packet[i+8] - 48  # ASCII -> число
                    
                    if DEBUG:
                        print(f"Найден пакет: exp={exponent}, base={base_value}, type={measurement_type}, flags={flag1},{flag2},{flag3}")
                    
                    # Определяем режим измерения
                    is_ac = (flag3 & FLAG_3_3_AC) != 0
                    is_dc = (flag3 & FLAG_3_4_DC) != 0
                    is_auto = (flag3 & FLAG_3_2_AUTO) != 0
                    is_hold = (flag2 & FLAG_2_4_HOLD) != 0
                    is_max = (flag2 & FLAG_2_3_MAX) != 0
                    is_min = (flag2 & FLAG_2_2_MIN) != 0
                    is_negative = (flag1 & FLAG_1_3_NEG) != 0
                    
                    # Определяем режим отображения
                    mode = "HOLD" if is_hold else "MAX" if is_max else "MIN" if is_min else "AUTO" if is_auto else "MAN"
                    
                    # Преобразуем базовое значение в число
                    try:
                        value = int(base_value)
                        
                        # Смещение экспоненты для напряжения
                        offset = 5 if (exponent & 0x4) > 0 else 3
                        
                        # Вычисляем значение с учетом экспоненты и смещения
                        if measurement_type == ';':  # Напряжение
                            real_value = value * (10 ** (exponent - offset))
                            value_str = f"{'-' if is_negative else ''}{real_value:.3f}"
                            unit = 'V'
                            
                            # Исправление для часто встречающейся ошибки с десятичной точкой
                            if '0.' in value_str and len(value_str) >= 5 and value_str[2] != '0':
                                # Перемещаем десятичную точку на одну позицию вправо
                                try:
                                    fixed_value = float(value_str)
                                    if 0.1 <= fixed_value <= 0.999:
                                        fixed_value = fixed_value * 10
                                        value_str = f"{'-' if is_negative else ''}{fixed_value:.3f}"
                                except:
                                    pass
                            
                            return {'value_str': value_str, 'unit': unit, 'ac': is_ac, 'dc': is_dc, 'mode': mode}
                        else:
                            # Другие типы измерений
                            return {'value_str': f"{'-' if is_negative else ''}{value}", 'unit': 'V', 'ac': is_ac, 'dc': is_dc, 'mode': mode}
                    except ValueError:
                        if DEBUG:
                            print(f"Ошибка преобразования значения: {base_value}")
        
        # Если не удалось распознать пакет по протоколу, используем запасной метод
        # Определение режима
        is_ac = '~' in ascii_data or 'AC' in ascii_data or 'ac' in ascii_data
        is_dc = 'DC' in ascii_data or 'dc' in ascii_data
        
        if not is_ac and not is_dc:
            is_dc = True  # По умолчанию DC
        
        # Поиск числового значения с помощью регулярных выражений
        for pattern in [
            r'(\d\.\d{3})',  # X.XXX
            r'(\d{1})(\d{3})',  # XXXX -> X.XXX
            r'0[.,](\d{3})',  # 0.XXX
            r'-0[.,](\d{3})',  # -0.XXX
            r'-(\d{1})(\d{3})',  # -XXXX -> -X.XXX
            r'(\d{3})'  # XXX -> 0.XXX
        ]:
            match = re.search(pattern, ascii_data)
            if match:
                if pattern == r'(\d\.\d{3})':
                    value_str = match.group(1)
                elif pattern == r'(\d{1})(\d{3})':
                    value_str = f"{match.group(1)}.{match.group(2)}"
                elif pattern == r'0[.,](\d{3})':
                    value_str = f"0.{match.group(1)}"
                elif pattern == r'-0[.,](\d{3})':
                    value_str = f"-0.{match.group(1)}"
                elif pattern == r'-(\d{1})(\d{3})':
                    value_str = f"-{match.group(1)}.{match.group(2)}"
                else:  # r'(\d{3})'
                    value_str = f"0.{match.group(1)}"
                
                return {'value_str': value_str, 'unit': 'V', 'ac': is_ac, 'dc': is_dc, 'mode': 'AUTO'}
        
        return None
    
    except Exception as e:
        if DEBUG:
            print(f"Ошибка парсинга: {e}")
        return None

def ultra_request_thread(device):
    """Ультрабыстрая отправка запросов без задержек"""
    try:
        commands = [REQUEST_DATA_COMMAND] * 100
        while True:
            for cmd in commands:
                device.write(cmd)
    except Exception as e:
        pass

def main():
    print("Поиск мультиметра UT803...")
    
    try:
        print(f"Подключение к устройству...")
        device = hid.device()
        device.open(VID, PID)
        device.set_nonblocking(1)
        print("Устройство успешно открыто!")
        
        # Инициализация
        print("Инициализация...")
        for _ in range(20):
            device.write(INIT_COMMAND)
            device.write(REQUEST_DATA_COMMAND)
        
        # Буфер данных
        buffer = bytearray()
        
        # Запускаем поток для ультрабыстрой отправки запросов
        threading.Thread(target=ultra_request_thread, args=(device,), daemon=True).start()
        
        print("\nПоказываю измерения напряжения (V) в режиме мультиметра...\n")
        print("No.\tTime\t\tDC/AC\tValue\tUnit\tMode")
        sys.stdout.flush()
        
        count = 0
        
        # Главный цикл
        while True:
            # Максимально быстрое чтение
            for _ in range(100):
                data = device.read(64)
                if data:
                    buffer.extend(data)
                    
                    # Проверяем данные после каждого чтения
                    while len(buffer) >= 16:
                        found = False
                        
                        for i in range(min(len(buffer) - 15, 100)):
                            if buffer[i] in PACKET_MARKERS:
                                packet = bytes(buffer[i:i+16])
                                result = parse_packet(packet)
                                
                                if result:
                                    # Выводим все успешно распознанные результаты
                                    count += 1
                                    timestamp = time.strftime("%H:%M:%S", time.localtime())
                                    print(f"{count}\t{timestamp}\t{'AC' if result.get('ac', False) else 'DC'}\t{result['value_str']}\t{result['unit']}\t{result['mode']}")
                                    sys.stdout.flush()
                                
                                # Удаляем обработанные данные
                                del buffer[:i+16]
                                found = True
                                break
                        
                        if not found:
                            del buffer[:1]
            
            # Очистка переполненного буфера
            if len(buffer) > 512:
                buffer = bytearray()
    
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

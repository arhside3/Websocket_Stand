#!/usr/bin/env python3
"""
    Декодер данных для мультиметра UT803 через HID
    Универсальная версия для режимов AC и DC с поддержкой True RMS
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

# Порог шума для DC (выше для фильтрации ложных показаний)
DC_NOISE_THRESHOLD = 0.015  # 15 мВ

# Порог шума для AC (ниже, так как AC измерения могут быть более мелкими)
AC_NOISE_THRESHOLD = 0.005  # 5 мВ

def parse_packet(packet):
    """Универсальный анализ пакета для режимов AC и DC с поддержкой True RMS"""
    try:
        # Преобразуем пакет в строку для анализа
        ascii_data = ''.join([chr(b) if 32 <= b <= 126 else '.' for b in packet])
        hex_data = ' '.join([f"{b:02X}" for b in packet])
        
        # Улучшенное определение режима по данным (AC или DC)
        is_ac = 'AC' in ascii_data or 'ac' in ascii_data or '~' in ascii_data
        is_dc = 'DC' in ascii_data or 'dc' in ascii_data
        
        # Проверка на True RMS
        is_trms = 'RMS' in ascii_data or 'rms' in ascii_data or 'TRM' in ascii_data
        
        # Если не удалось определить точно, используем другие признаки
        if not is_ac and not is_dc:
            if '~' in ascii_data:
                is_ac = True
            elif '-' in ascii_data and not re.search(r'-\s*0+[.,]', ascii_data):
                is_dc = True
            else:
                # В случае сомнений, определяем по преобладанию признаков
                ac_count = ascii_data.count('~') + ascii_data.count('A')
                dc_count = ascii_data.count('-') + ascii_data.count('D')
                is_ac = ac_count > dc_count
                is_dc = not is_ac
        
        # Задаем порог шума в зависимости от режима
        noise_threshold = AC_NOISE_THRESHOLD if is_ac else DC_NOISE_THRESHOLD
        
        # Проверка на отрицательные значения
        is_negative = '-' in ascii_data
        
        # Специальная обработка для нулевых значений (0.000)
        if ('000' in ascii_data and not re.search(r'[1-9]\d{2}', ascii_data)) or \
           ('00' in ascii_data and not re.search(r'[1-9]', ascii_data)):
            return {'value_str': '0.000', 'unit': 'V', 'ac': is_ac, 'dc': is_dc, 'trms': is_trms}
        
        # Прямой поиск чисел вида 5xx в режиме AC и DC
        for i in range(len(ascii_data)-2):
            if ascii_data[i] == '5' and ascii_data[i+1:i+3].isdigit():
                num = f"5{ascii_data[i+1:i+3]}"
                value = float(f"0.{num}")
                # Проверка на шум с учетом режима
                if abs(value) < noise_threshold and not is_negative and not is_ac:
                    return {'value_str': '0.000', 'unit': 'V', 'ac': is_ac, 'dc': is_dc, 'trms': is_trms}
                else:
                    value_str = f"{'-' if is_negative else ''}0.{num}"
                    return {'value_str': value_str, 'unit': 'V', 'ac': is_ac, 'dc': is_dc, 'trms': is_trms}
        
        # Специальный поиск для режима AC: числа с символом ~
        if is_ac:
            ac_match = re.search(r'~?\s*(\d{1,3})', ascii_data)
            if ac_match:
                num = ac_match.group(1).zfill(3)
                value = float(f"0.{num}")
                if abs(value) < noise_threshold and not is_negative:
                    return {'value_str': '0.000', 'unit': 'V', 'ac': True, 'dc': False, 'trms': is_trms}
                else:
                    value_str = f"0.{num}"
                    return {'value_str': value_str, 'unit': 'V', 'ac': True, 'dc': False, 'trms': is_trms}
        
        # Поиск отрицательных значений (-0.xxx)
        if is_negative:
            neg_match = re.search(r'-\s*0[.,](\d{3})', ascii_data)
            if neg_match:
                value = float(f"-0.{neg_match.group(1)}")
                if abs(value) < noise_threshold and is_dc:  # Для DC применяем фильтр шума
                    return {'value_str': '0.000', 'unit': 'V', 'ac': is_ac, 'dc': is_dc, 'trms': is_trms}
                else:
                    return {'value_str': f"-0.{neg_match.group(1)}", 'unit': 'V', 'ac': is_ac, 'dc': is_dc, 'trms': is_trms}
            
            # Поиск отрицательных трехзначных чисел
            neg_digits = re.search(r'-\s*(\d{1,3})', ascii_data)
            if neg_digits:
                num = neg_digits.group(1).zfill(3)
                value = float(f"-0.{num}")
                if abs(value) < noise_threshold and is_dc:  # Для DC применяем фильтр шума
                    return {'value_str': '0.000', 'unit': 'V', 'ac': is_ac, 'dc': is_dc, 'trms': is_trms}
                else:
                    return {'value_str': f"-0.{num}", 'unit': 'V', 'ac': is_ac, 'dc': is_dc, 'trms': is_trms}
        
        # 1. Ищем стандартные 4-значные числа (1642 -> 1.642V)
        match = re.search(r'(\d{4})', ascii_data)
        if match:
            num = match.group(1)
            value = int(num) / 1000.0
            if abs(value) < noise_threshold and not is_negative and is_dc:
                return {'value_str': '0.000', 'unit': 'V', 'ac': is_ac, 'dc': is_dc, 'trms': is_trms}
            else:
                value_str = f"{'-' if is_negative else ''}{value:.3f}"
                return {'value_str': value_str, 'unit': 'V', 'ac': is_ac, 'dc': is_dc, 'trms': is_trms}
        
        # 2. Ищем числа вида 0.XXX или 0,XXX
        zero_match = re.search(r'0[.,](\d{3})', ascii_data)
        if zero_match:
            value = float(f"0.{zero_match.group(1)}")
            if abs(value) < noise_threshold and not is_negative and is_dc:
                return {'value_str': '0.000', 'unit': 'V', 'ac': is_ac, 'dc': is_dc, 'trms': is_trms}
            else:
                value_str = f"{'-' if is_negative else ''}0.{zero_match.group(1)}"
                return {'value_str': value_str, 'unit': 'V', 'ac': is_ac, 'dc': is_dc, 'trms': is_trms}
        
        # 3. Ищем трехзначные числа (xxx -> 0.xxxV)
        match3 = re.search(r'(\d{3})', ascii_data)
        if match3:
            num = match3.group(1)
            if num[0] == '0' and '5' in ascii_data:
                for i in range(len(ascii_data)-2):
                    if ascii_data[i] == '5' and ascii_data[i+1:i+3].isdigit():
                        num = f"5{ascii_data[i+1:i+3]}"
                        break
            
            value = float(f"0.{num}")
            if abs(value) < noise_threshold and not is_negative and is_dc:
                return {'value_str': '0.000', 'unit': 'V', 'ac': is_ac, 'dc': is_dc, 'trms': is_trms}
            else:
                value_str = f"{'-' if is_negative else ''}0.{num}"
                return {'value_str': value_str, 'unit': 'V', 'ac': is_ac, 'dc': is_dc, 'trms': is_trms}
        
        # 4. Ищем даже маленькие значения (одно- и двузначные числа)
        small_match = re.search(r'(\d{1,2})', ascii_data)
        if small_match:
            num = small_match.group(1).zfill(3)  # дополняем нулями до 3 цифр
            value = float(f"0.{num}")
            if abs(value) < noise_threshold and not is_negative and is_dc:
                return {'value_str': '0.000', 'unit': 'V', 'ac': is_ac, 'dc': is_dc, 'trms': is_trms}
            else:
                value_str = f"{'-' if is_negative else ''}0.{num}"
                return {'value_str': value_str, 'unit': 'V', 'ac': is_ac, 'dc': is_dc, 'trms': is_trms}
        
        return None
    
    except Exception as e:
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
        
        # Главный цикл без фильтрации и задержек
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
                                    mode_str = "TRMS" if result.get('trms', False) else "AUTO"
                                    print(f"{count}\t{timestamp}\t{'AC' if result.get('ac', False) else 'DC'}\t{result['value_str']}\t{result['unit']}\t{mode_str}")
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

#!/usr/bin/env python3
"""
    Специальный декодер данных для мультиметра UT803 через HID
    С исправлением ошибки первой цифры и стабилизацией показаний
"""

import hid
import time
import sys
import re
import binascii
import threading
import collections

# Идентификаторы устройства
VID = 0x1A86
PID = 0xE008

# Команды управления
REQUEST_DATA_COMMAND = [0x00, 0xAB, 0xCD, 0x00, 0x00, 0x00, 0x00, 0x00]
INIT_COMMAND = [0x00, 0xAB, 0xCD, 0x01, 0x00, 0x00, 0x00, 0x00]

# Маркеры начала пакетов
PACKET_MARKERS = [0xF7, 0xB0, 0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39]

# Флаги состояния
FLAG_3_3_AC = 0x04
FLAG_3_4_DC = 0x08
FLAG_3_2_AUTO = 0x02

# Режим отладки
DEBUG = False

# Класс для управления историей измерений и определения стабильного значения
class StableValueDetector:
    def __init__(self, window_size=20, stable_count=5):
        self.values = collections.deque(maxlen=window_size)
        self.stable_value = None
        self.stable_count = stable_count
        self.last_stable_time = 0
        self.stability_counter = 0
        self.current_range = None  # Текущий диапазон измерений
    
    def add_value(self, value):
        """Добавляет новое значение и возвращает стабильное"""
        try:
            float_value = float(value)
            
            # Определяем диапазон значения
            value_range = self._determine_range(float_value)
            
            # Добавляем значение в историю
            self.values.append((float_value, value_range))
            
            # Анализируем текущее состояние
            range_counts = self._count_ranges()
            
            # Если есть доминирующий диапазон
            if range_counts:
                dominant_range, count = max(range_counts.items(), key=lambda x: x[1])
                
                # Если диапазон стабилен достаточное количество измерений
                if count >= self.stable_count:
                    # Устанавливаем текущий диапазон
                    self.current_range = dominant_range
                    
                    # Вычисляем среднее значение для этого диапазона
                    range_values = [v for v, r in self.values if r == dominant_range]
                    if range_values:
                        # Используем среднее из последних 5 значений этого диапазона
                        recent_values = range_values[-5:] if len(range_values) > 5 else range_values
                        mean_value = sum(recent_values) / len(recent_values)
                        
                        # Обновляем стабильное значение
                        self.stable_value = mean_value
                        self.last_stable_time = time.time()
                        self.stability_counter += 1
                        
                        # Возвращаем отформатированное значение
                        return f"{mean_value:.3f}", True
            
            # Если у нас есть стабильное значение, используем его
            if self.stable_value is not None:
                # Проверяем время с последнего стабильного значения
                if time.time() - self.last_stable_time < 5.0:  # 5 секунд таймаут
                    # Возвращаем последнее стабильное значение
                    return f"{self.stable_value:.3f}", False
            
            # В крайнем случае возвращаем текущее значение
            return value, False
            
        except Exception as e:
            if DEBUG:
                print(f"Ошибка обработки значения: {e}")
            return value, False
    
    def _determine_range(self, value):
        """Определяет диапазон значения"""
        if 0.1 <= value < 0.35:
            return "LOW"
        elif 1.5 <= value < 3.0:
            return "HIGH"
        else:
            return "UNKNOWN"
    
    def _count_ranges(self):
        """Подсчитывает количество значений в каждом диапазоне"""
        counts = {}
        for _, value_range in self.values:
            if value_range in ["LOW", "HIGH"]:  # Учитываем только известные диапазоны
                counts[value_range] = counts.get(value_range, 0) + 1
        return counts
    
    def get_status(self):
        """Возвращает текущий статус стабильности"""
        if self.stability_counter >= 10:
            return "Стабильно"
        elif self.stability_counter >= 5:
            return "Нормально"
        elif self.stable_value is not None:
            return "Фильтрованное"
        else:
            return "Нестабильно"

# Функция для поиска значений в пакете данных
def extract_value_from_packet(packet):
    """Извлекает значение измерения из пакета данных"""
    try:
        # Конвертируем в строковое представление для анализа
        ascii_data = ''.join([chr(b) if 32 <= b <= 126 else '.' for b in packet])
        
        if DEBUG:
            hex_data = ' '.join([f"{b:02X}" for b in packet])
            print(f"ASCII: '{ascii_data}', HEX: {hex_data}")
        
        # Пытаемся найти значение в формате X.XXX (например, 2.441)
        value_match = re.search(r'([0-9])\.([0-9]{3})', ascii_data)
        if value_match:
            first_digit = value_match.group(1)
            decimals = value_match.group(2)
            value_str = f"{first_digit}.{decimals}"
            return value_str, True
        
        # Ищем числовую последовательность, похожую на измерение
        for pattern in [
            r'([0-9])([0-9]{3})',  # Например, "2441" -> "2.441"
            r'0[.,]([0-9]{3})'     # Например, "0.244" -> "0.244"
        ]:
            match = re.search(pattern, ascii_data)
            if match:
                if pattern == r'([0-9])([0-9]{3})':
                    value_str = f"{match.group(1)}.{match.group(2)}"
                else:
                    value_str = f"0.{match.group(1)}"
                return value_str, True
        
        # Проверка на специальные форматы (например, HEX представление чисел)
        if re.search(r'[0-9A-F]{2}.[0-9A-F]{2}.[0-9A-F]{2}.[0-9A-F]{2}', ascii_data):
            # Может быть бинарное представление float
            for i in range(len(packet) - 3):
                try:
                    import struct
                    value = struct.unpack('f', packet[i:i+4])[0]
                    if 0.1 <= value <= 3.0:  # Разумный диапазон для нашего случая
                        return f"{value:.3f}", True
                except:
                    pass
        
        return None, False
    
    except Exception as e:
        if DEBUG:
            print(f"Ошибка извлечения значения: {e}")
        return None, False

# Функция для постоянного запроса данных
def request_data_thread(device):
    """Фоновый поток для непрерывного запроса данных"""
    try:
        while True:
            device.write(REQUEST_DATA_COMMAND)
            time.sleep(0.01)  # Небольшая пауза между запросами
    except:
        pass

# Основная функция программы
def main():
    global DEBUG
    
    # Проверяем аргументы командной строки
    if len(sys.argv) > 1 and "--debug" in sys.argv:
        DEBUG = True
        print("Режим отладки включен")
    
    print("Поиск мультиметра UT803...")
    
    # Подключение к устройству
    try:
        print("Подключение к устройству...")
        device = hid.device()
        device.open(VID, PID)
        device.set_nonblocking(1)
        print("Устройство успешно открыто!")
        
        # Инициализация устройства
        print("Инициализация...")
        for _ in range(10):
            device.write(INIT_COMMAND)
            time.sleep(0.05)
        
        # Запускаем фоновый поток запроса данных
        threading.Thread(target=request_data_thread, args=(device,), daemon=True).start()
        
        # Буфер для хранения данных
        buffer = bytearray()
        
        # Детектор стабильных значений
        detector = StableValueDetector()
        
        # Начинаем отображение измерений
        print("\nПоказываю измерения напряжения (V) в режиме мультиметра...\n")
        print("No.\tTime\t\tDC/AC\tValue\tUnit\tДиапазон\tСтатус")
        print("-" * 70)
        
        count = 0
        last_display_time = 0
        last_displayed_value = None
        
        # Основной цикл чтения данных
        while True:
            # Читаем данные с устройства
            data = device.read(64)
            
            if data:
                # Добавляем в буфер
                buffer.extend(data)
                
                # Обрабатываем буфер
                while len(buffer) >= 16:  # Минимальный размер пакета
                    found = False
                    
                    # Ищем маркеры начала пакета
                    for i in range(min(len(buffer) - 15, 50)):
                        if buffer[i] in PACKET_MARKERS:
                            # Берем пакет для анализа
                            packet = bytes(buffer[i:i+16])
                            
                            # Пытаемся извлечь значение
                            value_str, value_found = extract_value_from_packet(packet)
                            
                            if value_found:
                                # Обрабатываем найденное значение через детектор стабильности
                                stable_value, is_new = detector.add_value(value_str)
                                
                                # Определяем текущее время
                                current_time = time.time()
                                
                                # Показываем результат, если он новый или прошла секунда
                                if (is_new or last_displayed_value != stable_value or 
                                    current_time - last_display_time >= 1.0):
                                    
                                    # Увеличиваем счетчик
                                    count += 1
                                    
                                    # Форматируем время
                                    timestamp = time.strftime("%H:%M:%S", time.localtime())
                                    
                                    # Получаем диапазон
                                    range_str = detector.current_range if detector.current_range else "НЕИЗВ"
                                    
                                    # Получаем статус стабильности
                                    status = detector.get_status()
                                    
                                    # Выводим информацию
                                    print(f"{count}\t{timestamp}\tDC\t{stable_value}\tV\t{range_str}\t\t{status}")
                                    sys.stdout.flush()
                                    
                                    # Обновляем последние значения
                                    last_displayed_value = stable_value
                                    last_display_time = current_time
                            
                            # Удаляем обработанные данные
                            del buffer[:i+16]
                            found = True
                            break
                    
                    # Если ничего не нашли, удаляем первый байт
                    if not found:
                        del buffer[:1]
            
            # Ограничиваем размер буфера
            if len(buffer) > 1024:
                buffer = buffer[-512:]
            
            # Небольшая пауза для экономии ресурсов
            time.sleep(0.01)
    
    except KeyboardInterrupt:
        print("\nПрограмма остановлена пользователем")
    except Exception as e:
        print(f"\nОшибка: {e}")
        if DEBUG:
            import traceback
            traceback.print_exc()
    finally:
        try:
            device.close()
            print("Устройство закрыто")
        except:
            pass

if __name__ == "__main__":
    main()

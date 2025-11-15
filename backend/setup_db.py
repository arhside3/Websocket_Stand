import json
import locale
import sys
import traceback
from datetime import datetime

import numpy as np
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.engine import engine, Base, Session
from backend.models import MultimeterData, OscilloscopeData, UARTData

if sys.platform.startswith('win'):
    locale.setlocale(locale.LC_ALL, 'Russian_Russia.UTF-8')
    import codecs

    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

def setup_database():
    print("Проверка и создание рабочих таблиц базы данных...")
    try:
        Base.metadata.create_all(engine)
        
        session = Session()
        result = session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        tables = [row[0] for row in result]
        session.close()
        
        print("Созданные таблицы:")
        for table in tables:
            print(f"  - {table}")
            
        print("Рабочие таблицы базы данных готовы")
        return True
    except Exception as e:
        print(f"Ошибка при создании рабочих таблиц: {e}")
        traceback.print_exc()
        return False

database_initialized = setup_database()


def get_next_test_number():
    session = Session()
    try:
        result = session.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' AND (name LIKE 'мультиметр_%' OR name LIKE 'осциллограф_%' OR name LIKE 'uart_%')"
            )
        )
        existing_tests = set()
        for row in result:
            name = row[0]
            if (
                name.startswith('мультиметр_')
                or name.startswith('осциллограф_')
                or name.startswith('uart_')
            ):
                try:
                    number = int(name.split('_')[-1])
                    existing_tests.add(number)
                except Exception:
                    continue
        if not existing_tests:
            return 1
        return max(existing_tests) + 1
    except Exception as e:
        print(f"Ошибка при получении номера испытания: {e}")
        traceback.print_exc()
        return 1
    finally:
        session.close()


def create_uart_table(test_number):
    """Создаёт таблицу для данных UART нового испытания"""
    session = Session()
    try:
        uart_table = f"uart_{test_number}"
        create_uart_sql = f"""
        CREATE TABLE IF NOT EXISTS {uart_table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            start_byte INTEGER,
            command INTEGER,
            status INTEGER,
            payload_len INTEGER,
            payload BLOB,
            crc_one INTEGER,
            crc_two INTEGER
        )"""
        session.execute(text(create_uart_sql))
        session.commit()
        print(f"Создана таблица испытания: {uart_table}")
        return uart_table
    except Exception as e:
        session.rollback()
        print(f"Ошибка при создании таблицы UART: {e}")
        return None
    finally:
        session.close()


def create_test_tables(test_number):
    session = Session()
    try:
        mult_table = f"мультиметр_{test_number}"
        osc_table = f"осциллограф_{test_number}"
        uart_table = f"uart_{test_number}"

        create_mult_sql = f"""
        CREATE TABLE IF NOT EXISTS {mult_table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            value TEXT,
            unit TEXT,
            mode TEXT,
            range_str TEXT,
            measure_type TEXT,
            raw_data JSON
        )
        """

        create_osc_sql = f"""
        CREATE TABLE IF NOT EXISTS {osc_table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            channel TEXT,
            time_data TEXT,
            voltage_data TEXT,
            raw_data JSON
        )
        """

        create_uart_sql = f"""
        CREATE TABLE IF NOT EXISTS {uart_table} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            temp600_1 REAL,
            temp600_2 REAL,
            tempNormal1 REAL,
            tempNormal2 REAL,
            thrust1 REAL,
            gauge_id TEXT,
            calibration_value REAL,
            command INTEGER,
            start_byte INTEGER,
            status INTEGER,
            payload_len INTEGER,
            payload BLOB,
            crc_one INTEGER,
            crc_two INTEGER,
            data_type TEXT,
            raw_data JSON,
            test_number INTEGER
        )
        """

        session.execute(text(create_mult_sql))
        session.execute(text(create_osc_sql))
        session.execute(text(create_uart_sql))
        session.commit()
        print(f"Созданы таблицы испытания: {mult_table}, {osc_table}, {uart_table}")
        return mult_table, osc_table, uart_table
    except Exception as e:
        session.rollback()
        print(f"Ошибка при создании таблиц испытания: {e}")
        traceback.print_exc()
        return None, None, None
    finally:
        session.close()


def save_oscilloscope_data_to_test(data, osc_table):
    """Сохраняет данные осциллографа в таблицу испытания"""
    if not osc_table:
        return False
    session = Session()
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        import base64

        if data.get('channels'):
            for channel_name, channel_data in data['channels'].items():
                if 'voltage' in channel_data and 'time' in channel_data:
                    time_bytes = np.array(
                        channel_data['time'], dtype=np.float32
                    ).tobytes()
                    voltage_bytes = np.array(
                        channel_data['voltage'], dtype=np.float32
                    ).tobytes()
                    insert_sql = f"""
                    INSERT INTO {osc_table} (timestamp, channel, time_data, voltage_data, raw_data)
                    VALUES (:timestamp, :channel, :time_data, :voltage_data, :raw_data)
                    """
                    session.execute(
                        text(insert_sql),
                        {
                            'timestamp': timestamp,
                            'channel': channel_name,
                            'time_data': base64.b64encode(time_bytes).decode(
                                'utf-8'
                            ),
                            'voltage_data': base64.b64encode(
                                voltage_bytes
                            ).decode('utf-8'),
                            'raw_data': json.dumps(channel_data),
                        },
                    )
        session.commit()
        print(
            f"Данные осциллографа сохранены в таблицу испытания: {osc_table}"
        )
        return True
    except Exception as e:
        session.rollback()
        print(
            f"Ошибка сохранения данных осциллографа в таблицу испытания: {e}"
        )
        traceback.print_exc()
        return False
    finally:
        session.close()


def save_multimeter_data_to_test(data, mult_table):
    """Сохраняет данные мультиметра в таблицу испытания"""
    if not mult_table:
        return False
    session = Session()
    try:
        insert_sql = f"""
        INSERT INTO {mult_table} (timestamp, value, unit, mode, range_str, measure_type, raw_data)
        VALUES (:timestamp, :value, :unit, :mode, :range_str, :measure_type, :raw_data)
        """
        session.execute(
            text(insert_sql),
            {
                'timestamp': data.get('timestamp', ''),
                'value': data.get('value', ''),
                'unit': data.get('unit', ''),
                'mode': data.get('mode', ''),
                'range_str': data.get('range_str', ''),
                'measure_type': data.get('measure_type', ''),
                'raw_data': json.dumps(data.get('raw_data', {})),
            },
        )
        session.commit()
        print(
            f"Данные мультиметра сохранены в таблицу испытания: {mult_table}"
        )
        return True
    except Exception as e:
        session.rollback()
        print(f"Ошибка сохранения данных мультиметра в таблицу испытания: {e}")
        traceback.print_exc()
        return False
    finally:
        session.close()


def save_uart_data_to_test(data, uart_table):
    if not uart_table:
        return False
    session = Session()
    try:
        insert_sql = f"""
        INSERT INTO {uart_table} (
            timestamp, start_byte, command, status, payload_len, payload, crc_one, crc_two
        )
        VALUES (
            :timestamp, :start_byte, :command, :status, :payload_len, :payload, :crc_one, :crc_two
        )
        """
        session.execute(
            text(insert_sql),
            {
                'timestamp': data.get('timestamp', ''),
                'start_byte': data.get('start_byte'),
                'command': data.get('command'),
                'status': data.get('status'),
                'payload_len': data.get('payload_len'),
                'payload': data.get('payload'),
                'crc_one': data.get('crc_one'),
                'crc_two': data.get('crc_two'),
            },
        )
        session.commit()
        print(f"Данные UART сохранены в таблицу испытания: {uart_table}")
        return True
    except Exception as e:
        session.rollback()
        print(f"Ошибка сохранения данных UART в таблицу испытания: {e}")
        traceback.print_exc()
        return False
    finally:
        session.close()


def start_new_test():
    from main import move_working_tables_to_test

    global current_test_number, current_multimeter_table, current_oscilloscope_table, current_uart_table
    current_test_number = get_next_test_number()
    (
        current_multimeter_table,
        current_oscilloscope_table,
        current_uart_table,
    ) = create_test_tables(current_test_number)
    if (
        current_multimeter_table
        and current_oscilloscope_table
        and current_uart_table
    ):
        print(f"Начато новое испытание #{current_test_number}")
        move_working_tables_to_test(current_test_number)
        return current_test_number
    else:
        print("Ошибка при создании таблиц испытания")
        return None


current_uart_table = None


def get_test_list():
    """Возвращает список всех испытаний"""
    session = Session()
    try:
        result = session.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'мультиметр_%' ORDER BY name"
            )
        )
        tests = []
        for row in result:
            mult_table = row[0]
            try:
                test_number = int(mult_table.split('_')[-1])
                osc_table = f"осциллограф_{test_number}"
                check_osc = session.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name = :osc"
                    ),
                    {'osc': osc_table},
                )
                if not check_osc.fetchone():
                    continue
                count_mult = session.execute(
                    text(f"SELECT COUNT(*) FROM {mult_table}")
                )
                count_osc = session.execute(
                    text(f"SELECT COUNT(*) FROM {osc_table}")
                )
                record_count = (
                    count_mult.fetchone()[0] + count_osc.fetchone()[0]
                )
                time_mult = session.execute(
                    text(
                        f"SELECT MIN(timestamp), MAX(timestamp) FROM {mult_table}"
                    )
                )
                time_osc = session.execute(
                    text(
                        f"SELECT MIN(timestamp), MAX(timestamp) FROM {osc_table}"
                    )
                )
                t1 = time_mult.fetchone()
                t2 = time_osc.fetchone()
                start_time = (
                    min([x for x in [t1[0], t2[0]] if x])
                    if t1[0] or t2[0]
                    else "Неизвестно"
                )
                end_time = (
                    max([x for x in [t1[1], t2[1]] if x])
                    if t1[1] or t2[1]
                    else "Неизвестно"
                )
                tests.append(
                    {
                        'number': test_number,
                        'multimeter_table': mult_table,
                        'oscilloscope_table': osc_table,
                        'record_count': record_count,
                        'start_time': start_time,
                        'end_time': end_time,
                    }
                )
            except Exception:
                continue
        return sorted(tests, key=lambda x: x['number'])
    except Exception as e:
        print(f"Ошибка при получении списка испытаний: {e}")
        return []
    finally:
        session.close()


def get_test_data(test_number, data_type=None, limit=100, page=1):
    """Возвращает данные конкретного испытания с поддержкой пагинации"""
    session = Session()
    try:
        mult_table = f"мультиметр_{test_number}"
        osc_table = f"осциллограф_{test_number}"
        data = {}
        offset = (page - 1) * limit
        total = 0
        total_pages = 1
        if data_type == 'multimeter' or data_type is None:
            check_mult = session.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name = :mult"
                ),
                {'mult': mult_table},
            )
            if check_mult.fetchone():
                total_result = session.execute(
                    text(f"SELECT COUNT(*) FROM {mult_table}")
                )
                total = total_result.fetchone()[0]
                total_pages = max(1, (total + limit - 1) // limit)
                result = session.execute(
                    text(
                        f"SELECT * FROM {mult_table} ORDER BY id DESC LIMIT :limit OFFSET :offset"
                    ),
                    {'limit': limit, 'offset': offset},
                )
                data['multimeter'] = [
                    {
                        'id': row[0],
                        'timestamp': row[1],
                        'value': row[2],
                        'unit': row[3],
                        'mode': row[4],
                        'range_str': row[5],
                        'measure_type': row[6],
                        'raw_data': row[7],
                    }
                    for row in result
                ]
        if data_type == 'oscilloscope' or data_type is None:
            check_osc = session.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name = :osc"
                ),
                {'osc': osc_table},
            )
            if check_osc.fetchone():
                total_result = session.execute(
                    text(f"SELECT COUNT(*) FROM {osc_table}")
                )
                total = total_result.fetchone()[0]
                total_pages = max(1, (total + limit - 1) // limit)
                result = session.execute(
                    text(
                        f"SELECT * FROM {osc_table} ORDER BY id DESC LIMIT :limit OFFSET :offset"
                    ),
                    {'limit': limit, 'offset': offset},
                )
                data['oscilloscope'] = [
                    {
                        'id': row[0],
                        'timestamp': row[1],
                        'channel': row[2],
                        'time_data': row[3],
                        'voltage_data': row[4],
                        'raw_data': row[5],
                    }
                    for row in result
                ]
        data['total'] = total
        data['page'] = page
        data['per_page'] = limit
        data['total_pages'] = total_pages
        return data
    except Exception as e:
        print(f"Ошибка при получении данных испытания: {e}")
        return {'error': str(e)}
    finally:
        session.close()


def get_oscilloscope_data_paginated(page=1, per_page=50, test_number=None):
    session = Session()
    try:
        if test_number is None:
            total = session.query(OscilloscopeData).count()
            results = (
                session.query(OscilloscopeData)
                .order_by(OscilloscopeData.id.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
                .all()
            )
            data = [
                {
                    'id': row.id,
                    'timestamp': row.timestamp,
                    'channel': row.channel,
                    'time_data': row.time_data,
                    'voltage_data': row.voltage_data,
                    'raw_data': row.raw_data,
                }
                for row in results
            ]
        else:
            table = f"осциллограф_{test_number}"
            offset = (page - 1) * per_page
            total_result = session.execute(
                text(f"SELECT COUNT(*) FROM {table}")
            )
            total = total_result.fetchone()[0]
            result = session.execute(
                text(
                    f"SELECT * FROM {table} ORDER BY id DESC LIMIT :limit OFFSET :offset"
                ),
                {'limit': per_page, 'offset': offset},
            )
            data = [
                {
                    'id': row[0],
                    'timestamp': row[1],
                    'channel': row[2],
                    'time_data': row[3],
                    'voltage_data': row[4],
                    'raw_data': row[5],
                }
                for row in result
            ]
        return {
            'data': data,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': (total + per_page - 1) // per_page,
        }
    except Exception as e:
        print(f"Ошибка получения данных осциллографа с пагинацией: {e}")
        traceback.print_exc()
        return {
            'data': [],
            'total': 0,
            'page': page,
            'per_page': per_page,
            'total_pages': 1,
        }
    finally:
        session.close()


def get_multimeter_data_paginated(page=1, per_page=50, test_number=None):
    session = Session()
    try:
        if test_number is None:
            total = session.query(MultimeterData).count()
            results = (
                session.query(MultimeterData)
                .order_by(MultimeterData.id.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
                .all()
            )
            data = [
                {
                    'id': row.id,
                    'timestamp': row.timestamp,
                    'value': row.value,
                    'unit': row.unit,
                    'mode': row.mode,
                    'range_str': row.range_str,
                    'measure_type': row.measure_type,
                    'raw_data': row.raw_data,
                }
                for row in results
            ]
        else:
            table = f"мультиметр_{test_number}"
            offset = (page - 1) * per_page
            total_result = session.execute(
                text(f"SELECT COUNT(*) FROM {table}")
            )
            total = total_result.fetchone()[0]
            result = session.execute(
                text(
                    f"SELECT * FROM {table} ORDER BY id DESC LIMIT :limit OFFSET :offset"
                ),
                {'limit': per_page, 'offset': offset},
            )
            data = [
                {
                    'id': row[0],
                    'timestamp': row[1],
                    'value': row[2],
                    'unit': row[3],
                    'mode': row[4],
                    'range_str': row[5],
                    'measure_type': row[6],
                    'raw_data': row[7],
                }
                for row in result
            ]
        return {
            'data': data,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': (total + per_page - 1) // per_page,
        }
    except Exception as e:
        print(f"Ошибка получения данных мультиметра с пагинацией: {e}")
        traceback.print_exc()
        return {
            'data': [],
            'total': 0,
            'page': page,
            'per_page': per_page,
            'total_pages': 1,
        }
    finally:
        session.close()

def save_uart_sensor_data(sensor_data, test_number=None):
    """Сохраняет данные датчиков UART в основную таблицу"""
    session = Session()
    try:
        db_record = UARTData(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            temp600_1=sensor_data.get('temp600_1'),
            temp600_2=sensor_data.get('temp600_2'),
            tempNormal1=sensor_data.get('tempNormal1'),
            tempNormal2=sensor_data.get('tempNormal2'),
            thrust1=sensor_data.get('thrust1'),
            data_type='sensor_data',
            raw_data=sensor_data,
            test_number=test_number
        )
        session.add(db_record)
        session.commit()
        print(f"Данные датчиков UART сохранены: {sensor_data}")
        return True
    except Exception as e:
        session.rollback()
        print(f"Ошибка сохранения данных датчиков UART: {e}")
        traceback.print_exc()
        return False
    finally:
        session.close()

def save_uart_calibration_data(gauge_id, value, command=0x3D, test_number=None):
    """Сохраняет данные калибровки UART"""
    session = Session()
    try:
        db_record = UARTData(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            gauge_id=gauge_id,
            calibration_value=value,
            command=command,
            data_type='calibration',
            raw_data={'gauge_id': gauge_id, 'value': value, 'command': command},
            test_number=test_number
        )
        session.add(db_record)
        session.commit()
        print(f"Данные калибровки UART сохранены: {gauge_id}={value}")
        return True
    except Exception as e:
        session.rollback()
        print(f"Ошибка сохранения данных калибровки UART: {e}")
        traceback.print_exc()
        return False
    finally:
        session.close()

def save_uart_raw_packet(data, test_number=None):
    """Сохраняет сырые данные UART пакета"""
    session = Session()
    try:
        db_record = UARTData(
            timestamp=data.get('timestamp', ''),
            start_byte=data.get('start_byte'),
            command=data.get('command'),
            status=data.get('status'),
            payload_len=data.get('payload_len'),
            payload=data.get('payload'),
            crc_one=data.get('crc_one'),
            crc_two=data.get('crc_two'),
            data_type='raw_packet',
            raw_data=data,
            test_number=test_number
        )
        session.add(db_record)
        session.commit()
        print(f"Сырые данные UART пакета сохранены: CMD={data.get('command')}")
        return True
    except Exception as e:
        session.rollback()
        print(f"Ошибка сохранения сырых данных UART: {e}")
        traceback.print_exc()
        return False
    finally:
        session.close()

def save_uart_sensor_data_to_test(sensor_data, uart_table):
    """Сохраняет данные датчиков UART в таблицу испытания"""
    if not uart_table:
        return False
    session = Session()
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        insert_sql = f"""
        INSERT INTO {uart_table} (
            timestamp, temp600_1, temp600_2, tempNormal1, tempNormal2, thrust1, 
            data_type, raw_data
        )
        VALUES (
            :timestamp, :temp600_1, :temp600_2, :tempNormal1, :tempNormal2, :thrust1,
            :data_type, :raw_data
        )
        """
        session.execute(
            text(insert_sql),
            {
                'timestamp': timestamp,
                'temp600_1': sensor_data.get('temp600_1'),
                'temp600_2': sensor_data.get('temp600_2'),
                'tempNormal1': sensor_data.get('tempNormal1'),
                'tempNormal2': sensor_data.get('tempNormal2'),
                'thrust1': sensor_data.get('thrust1'),
                'data_type': 'sensor_data',
                'raw_data': json.dumps(sensor_data),
            },
        )
        session.commit()
        print(f"Данные датчиков UART сохранены в таблицу испытания: {uart_table}")
        return True
    except Exception as e:
        session.rollback()
        print(f"Ошибка сохранения данных датчиков UART в таблицу испытания: {e}")
        traceback.print_exc()
        return False
    finally:
        session.close()

def get_uart_data_paginated(page=1, per_page=50, test_number=None, data_type=None):
    """Получает данные UART с пагинацией"""
    session = Session()
    try:
        if test_number is None:
            query = session.query(UARTData)
            if data_type:
                query = query.filter(UARTData.data_type == data_type)
            
            total = query.count()
            results = (
                query.order_by(UARTData.id.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
                .all()
            )
            
            data = []
            for row in results:
                item = {
                    'id': row.id,
                    'timestamp': row.timestamp,
                    'data_type': row.data_type,
                    'temp600_1': row.temp600_1,
                    'temp600_2': row.temp600_2,
                    'tempNormal1': row.tempNormal1,
                    'tempNormal2': row.tempNormal2,
                    'thrust1': row.thrust1,
                    'gauge_id': row.gauge_id,
                    'calibration_value': row.calibration_value,
                    'command': row.command,
                    'raw_data': row.raw_data,
                    'test_number': row.test_number
                }
                data.append(item)
        else:
            table = f"uart_{test_number}"
            offset = (page - 1) * per_page
            
            base_sql = f"SELECT * FROM {table}"
            count_sql = f"SELECT COUNT(*) FROM {table}"
            
            if data_type:
                base_sql += f" WHERE data_type = '{data_type}'"
                count_sql += f" WHERE data_type = '{data_type}'"
            
            base_sql += " ORDER BY id DESC LIMIT :limit OFFSET :offset"
            
            total_result = session.execute(text(count_sql))
            total = total_result.fetchone()[0]
            
            result = session.execute(
                text(base_sql),
                {'limit': per_page, 'offset': offset}
            )
            
            data = []
            for row in result:
                raw_data = json.loads(row[17]) if row[17] else {}
                item = {
                    'id': row[0],
                    'timestamp': row[1],
                    'temp600_1': row[2],
                    'temp600_2': row[3],
                    'tempNormal1': row[4],
                    'tempNormal2': row[5],
                    'thrust1': row[6],
                    'gauge_id': row[7],
                    'calibration_value': row[8],
                    'command': row[9],
                    'start_byte': row[10],
                    'status': row[11],
                    'payload_len': row[12],
                    'payload': row[13],
                    'crc_one': row[14],
                    'crc_two': row[15],
                    'data_type': row[16],
                    'raw_data': raw_data,
                    'test_number': row[18]
                }
                data.append(item)
        
        return {
            'data': data,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': max(1, (total + per_page - 1) // per_page),
        }
    except Exception as e:
        print(f"Ошибка получения данных UART с пагинацией: {e}")
        traceback.print_exc()
        return {
            'data': [],
            'total': 0,
            'page': page,
            'per_page': per_page,
            'total_pages': 1,
        }
    finally:
        session.close()
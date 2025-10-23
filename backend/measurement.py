import traceback
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import text

from backend.engine import *
from backend.models import MultimeterData, OscilloscopeData

current_multimeter_table = None
current_oscilloscope_table = None
is_data_collection_active = False

is_multimeter_collection_active = False


class Measurement:
    def __init__(
        self, value, unit, mode, range_str, measure_type, raw_data, timestamp
    ):
        self.value = value
        self.unit = unit
        self.mode = mode
        self.range_str = range_str
        self.measure_type = measure_type
        self.raw_data = raw_data
        self.timestamp = timestamp


def save_oscilloscope_data(data, force_save=False):
    from backend.setup_db import save_oscilloscope_data_to_test

    global is_data_collection_active, current_oscilloscope_table
    if not is_data_collection_active and not force_save:
        return True
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
                    db_record = OscilloscopeData(
                        timestamp=timestamp,
                        channel=channel_name,
                        time_data=base64.b64encode(time_bytes).decode('utf-8'),
                        voltage_data=base64.b64encode(voltage_bytes).decode(
                            'utf-8'
                        ),
                        raw_data=channel_data,
                    )
                    session.add(db_record)
        session.commit()
        print("Данные осциллографа сохранены в рабочую таблицу")
        if current_oscilloscope_table:
            save_oscilloscope_data_to_test(data, current_oscilloscope_table)
        return True
    except Exception as e:
        session.rollback()
        print(f"Ошибка сохранения данных осциллографа: {e}")
        traceback.print_exc()
        return False
    finally:
        session.close()


def save_multimeter_data(data, force_save=False):
    from backend.setup_db import save_multimeter_data_to_test

    global is_multimeter_collection_active, current_multimeter_table
    if not is_multimeter_collection_active and not force_save:
        return True
    session = Session()
    try:
        db_record = MultimeterData(
            timestamp=data.get('timestamp', ''),
            value=data.get('value', ''),
            unit=data.get('unit', ''),
            mode=data.get('mode', ''),
            range_str=data.get('range_str', ''),
            measure_type=data.get('measure_type', ''),
            raw_data=data.get('raw_data', {}),
        )
        session.add(db_record)
        session.commit()
        print("Данные мультиметра сохранены в рабочую таблицу")
        if current_multimeter_table:
            save_multimeter_data_to_test(data, current_multimeter_table)
        return True
    except Exception as e:
        session.rollback()
        print(f"Ошибка сохранения данных мультиметра: {e}")
        traceback.print_exc()
        return False
    finally:
        session.close()


def save_uart_data(data):
    session = Session()
    try:
        insert_sql = """
        INSERT INTO uart (timestamp, start_byte, command, status, payload_len, payload, crc_one, crc_two)
        VALUES (:timestamp, :start_byte, :command, :status, :payload_len, :payload, :crc_one, :crc_two)
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
        print("Данные UART сохранены в рабочую таблицу")
        return True
    except Exception as e:
        session.rollback()
        print(f"Ошибка сохранения данных UART: {e}")
        traceback.print_exc()
        return False
    finally:
        session.close()


def get_oscilloscope_data_from_db(limit=100):
    session = Session()
    try:
        results = (
            session.query(OscilloscopeData)
            .order_by(OscilloscopeData.id.desc())
            .limit(limit)
            .all()
        )
        data = []
        for row in results:
            data.append(
                {
                    'id': row.id,
                    'timestamp': row.timestamp,
                    'channel': row.channel,
                    'time_data': row.time_data,
                    'voltage_data': row.voltage_data,
                }
            )
        return data
    except Exception as e:
        print(f"Ошибка получения данных осциллографа из БД: {e}")
        traceback.print_exc()
        return []
    finally:
        session.close()


def get_multimeter_data_from_db(limit=100):
    session = Session()
    try:
        results = (
            session.query(MultimeterData)
            .order_by(MultimeterData.id.desc())
            .limit(limit)
            .all()
        )
        data = []
        for row in results:
            data.append(
                {
                    'id': row.id,
                    'timestamp': row.timestamp,
                    'value': row.value,
                    'unit': row.unit,
                    'mode': row.mode,
                    'range_str': row.range_str,
                    'measure_type': row.measure_type,
                }
            )
        return data
    except Exception as e:
        print(f"Ошибка получения данных мультиметра из БД: {e}")
        traceback.print_exc()
        return []
    finally:
        session.close()


def get_oscilloscope_history(period='hour'):
    session = Session()
    try:
        now = datetime.now()
        if period == 'test':
            results = (
                session.query(OscilloscopeData)
                .order_by(OscilloscopeData.id.desc())
                .limit(10)
                .all()
            )

            if not results:
                print(
                    "Нет данных осциллографа в БД для тестового графика, генерируем тестовые данные"
                )
                timestamps = []
                test_channels = {
                    "CH1": {"name": "CH1", "values": []},
                    "CH2": {"name": "CH2", "values": []},
                    "CH3": {"name": "CH3", "values": []},
                    "CH4": {"name": "CH4", "values": []},
                }

                phase_shift = np.random.random() * np.pi
                amplitude_shift = np.random.random() * 0.5 + 0.75

                for i in range(10):
                    timestamp = (now - timedelta(seconds=i * 5)).strftime(
                        "%Y-%m-%d %H:%M:%S.%f"
                    )[:-3]
                    timestamps.append(timestamp)

                    test_channels["CH1"]["values"].append(
                        3.0 * amplitude_shift * np.sin(i / 3.0 + phase_shift)
                        + 3.0
                        + np.random.random() * 0.2
                        - 0.1
                    )

                    test_channels["CH2"]["values"].append(
                        2.0 * amplitude_shift * np.cos(i / 2.0 + phase_shift)
                        + 2.0
                        + np.random.random() * 0.2
                        - 0.1
                    )

                    test_channels["CH3"]["values"].append(
                        (i % 5) * 0.5 * amplitude_shift
                        + 1.0
                        + np.random.random() * 0.1
                        - 0.05
                    )

                    test_channels["CH4"]["values"].append(
                        4.0
                        if (i + int(phase_shift * 5)) % 4 < 2
                        else 1.0 + np.random.random() * 0.2 - 0.1
                    )

                return {
                    'timestamps': list(reversed(timestamps)),
                    'channels': list(test_channels.values()),
                }

            timestamps = []
            channels = {}
            for row in reversed(results):
                timestamps.append(row.timestamp)
                if row.channel not in channels:
                    channels[row.channel] = {'name': row.channel, 'values': []}
                try:
                    import base64

                    voltage_bytes = base64.b64decode(row.voltage_data)
                    voltage_array = np.frombuffer(
                        voltage_bytes, dtype=np.float32
                    )
                    avg_voltage = np.mean(voltage_array)
                    channels[row.channel]['values'].append(float(avg_voltage))
                except Exception as e:
                    print(
                        f"Ошибка декодирования данных канала {row.channel}: {e}"
                    )
                    channels[row.channel]['values'].append(0.0)
            return {
                'timestamps': timestamps,
                'channels': list(channels.values()),
            }
        else:
            if period == 'hour':
                start_time = now - timedelta(hours=1)
            elif period == 'day':
                start_time = now - timedelta(days=1)
            elif period == 'week':
                start_time = now - timedelta(weeks=1)
            else:
                start_time = now - timedelta(hours=1)
            start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
            results = (
                session.query(OscilloscopeData)
                .filter(OscilloscopeData.timestamp >= start_time_str)
                .order_by(OscilloscopeData.id.asc())
                .all()
            )
            timestamps = []
            voltages = []
            for row in results:
                timestamps.append(row.timestamp)
                try:
                    import base64

                    voltage_bytes = base64.b64decode(row.voltage_data)
                    voltage_array = np.frombuffer(
                        voltage_bytes, dtype=np.float32
                    )
                    avg_voltage = np.mean(voltage_array)
                    voltages.append(float(avg_voltage))
                except Exception as e:
                    print(f"Ошибка декодирования данных: {e}")
                    voltages.append(0.0)
            return {'timestamps': timestamps, 'voltages': voltages}
    except Exception as e:
        print(f"Ошибка получения истории осциллографа: {e}")
        return {'timestamps': [], 'voltages': []}
    finally:
        session.close()


def get_multimeter_history(period='hour'):
    """Возвращает исторические данные мультиметра для графика"""
    session = Session()
    try:
        now = datetime.now()
        if period == 'hour':
            start_time = now - timedelta(hours=1)
        elif period == 'day':
            start_time = now - timedelta(days=1)
        elif period == 'week':
            start_time = now - timedelta(weeks=1)
        else:
            start_time = now - timedelta(hours=1)

        start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")

        results = (
            session.query(MultimeterData)
            .filter(MultimeterData.timestamp >= start_time_str)
            .order_by(MultimeterData.timestamp.asc())
            .all()
        )

        timestamps = []
        values = []
        raw_data_list = []

        for row in results:
            try:
                value = float(row.value) if row.value != 'OL' else None
                if value is not None:
                    timestamps.append(row.timestamp)
                    values.append(value)
                    raw_data_list.append(
                        row.raw_data if row.raw_data else None
                    )
            except (ValueError, TypeError):
                continue

        if not timestamps:
            print("Нет данных мультиметра в БД за указанный период")
            return {'timestamps': [], 'values': [], 'raw_data': []}

        print(f"Получено {len(timestamps)} точек данных мультиметра из БД")
        return {
            'timestamps': timestamps,
            'values': values,
            'raw_data': raw_data_list,
        }
    except Exception as e:
        print(f"Ошибка получения истории мультиметра: {e}")
        traceback.print_exc()
        return {'timestamps': [], 'values': [], 'raw_data': []}
    finally:
        session.close()

from sqlalchemy import JSON, Column, Integer, LargeBinary, String
from sqlalchemy.dialects.sqlite import JSON

from backend.engine import *


class OscilloscopeData(Base):
    __tablename__ = 'осциллограф'
    id = Column(Integer, primary_key=True)
    timestamp = Column(String)
    channel = Column(String)
    time_data = Column(String)
    voltage_data = Column(String)
    raw_data = Column(JSON)


class MultimeterData(Base):
    __tablename__ = 'мультиметр'
    id = Column(Integer, primary_key=True)
    timestamp = Column(String)
    value = Column(String)
    unit = Column(String)
    mode = Column(String)
    range_str = Column(String)
    measure_type = Column(String)
    raw_data = Column(JSON)


class UARTData(Base):
    __tablename__ = 'uart'
    id = Column(Integer, primary_key=True)
    timestamp = Column(String)
    start_byte = Column(Integer)
    command = Column(Integer)
    status = Column(Integer)
    payload_len = Column(Integer)
    payload = Column(LargeBinary)
    crc_one = Column(Integer)
    crc_two = Column(Integer)

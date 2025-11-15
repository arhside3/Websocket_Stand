from sqlalchemy import JSON, Column, Integer, LargeBinary, String, Float
from sqlalchemy.dialects.sqlite import JSON

from backend.engine import Base


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
    __tablename__ = 'uart_data'
    id = Column(Integer, primary_key=True)
    timestamp = Column(String)
    
    temp600_1 = Column(Float)
    temp600_2 = Column(Float)
    tempNormal1 = Column(Float)
    tempNormal2 = Column(Float)
    thrust1 = Column(Float)
    
    gauge_id = Column(String)
    calibration_value = Column(Float)
    command = Column(Integer)
    
    start_byte = Column(Integer)
    status = Column(Integer)
    payload_len = Column(Integer)
    payload = Column(LargeBinary)
    crc_one = Column(Integer)
    crc_two = Column(Integer)
    
    data_type = Column(String)
    raw_data = Column(JSON)
    test_number = Column(Integer, nullable=True)
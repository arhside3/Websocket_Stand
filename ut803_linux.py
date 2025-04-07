"""
UT803 Multimeter Reader - Supports both HID and RS232 interfaces
"""

import hid
import serial
import time
import sys
import logging
from typing import Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('UT803')

class UT803Reader:
    def __init__(self):
        self.device = None
        self.serial_port = None
        
    def connect_serial(self, port: str = '/dev/ttyUSB0') -> bool:
        """Connect to the multimeter via RS232"""
        try:
            self.serial_port = serial.Serial(
                port=port,
                baudrate=19200,
                bytesize=serial.SEVENBITS,
                parity=serial.PARITY_ODD,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            self.serial_port.setDTR(True)
            self.serial_port.setRTS(False)
            logger.info(f"Successfully connected to RS232 port {port}")
            return True
        except serial.SerialException as e:
            logger.error(f"Failed to connect to RS232: {str(e)}")
            return False
            
    def connect_hid(self) -> bool:
        """Connect to the multimeter via HID"""
        try:
            for vid, pid in [(0x1A86, 0xE008), (0x04FA, 0x2490)]:
                devices = hid.enumerate(vid, pid)
                if devices:
                    self.device = hid.device()
                    self.device.open(vid, pid)
                    self.device.set_nonblocking(1)
                    logger.info(f"Successfully connected to HID device {vid:04X}:{pid:04X}")
                    return True
            logger.error("No HID device found")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to HID: {str(e)}")
            return False
            
    def decode_ut803_data(self, data: str) -> str:
        """Decode UT803 data format into formatted string"""
        try:
            parts = data.split(';')
            if len(parts) != 2:
                return "Invalid data format"
                
            value_str = parts[0].strip('@')
            function_code = parts[1]
            
            try:
                if value_str.startswith('?'):
                    value = "OL"
                else:
                    raw_value = float(value_str)
                    if function_code.startswith('8'):
                        value = f"{raw_value/1000:.3f}"
                    else:
                        value = f"{raw_value/1000:.3f}"
            except ValueError:
                value = "Error"

            mode = "AC"  
            unit = "В"
            measure_type = "Вольтметр"
            
            if function_code.startswith('8'):
                if '06' in function_code:
                    unit = "В"
                    measure_type = "Вольтметр"
                    mode = "DC"
            
            if value == "OL":
                return f"OL {mode} AUTO"
            elif value == "Error":
                return "Error"
            else:
                range_str = "AUTO"
                output = f"{value} {unit} {mode} {range_str}"
                if measure_type:
                    output += f" [{measure_type}]"
                return output
                
        except Exception as e:
            logger.error(f"Error decoding data: {str(e)}")
            return f"Error: {str(e)}"
            
    def read_serial(self) -> Optional[str]:
        """Read data from RS232 interface"""
        if not self.serial_port:
            return None
        try:
            data = self.serial_port.readline()
            if data:
                decoded_data = data.decode('ascii').strip()
                return self.decode_ut803_data(decoded_data)
        except Exception as e:
            logger.error(f"Error reading from RS232: {str(e)}")
        return None
        
    def read_hid(self) -> Optional[str]:
        """Read data from HID interface"""
        if not self.device:
            return None
        try:
            data = self.device.read(64, timeout_ms=1000)
            if data:
                return str(data)
        except Exception as e:
            logger.error(f"Error reading from HID: {str(e)}")
        return None
        
    def disconnect(self):
        """Disconnect from both interfaces"""
        if self.serial_port:
            self.serial_port.close()
            self.serial_port = None
        if self.device:
            self.device.close()
            self.device = None
            
def main():
    reader = UT803Reader()
    
    if reader.connect_serial():
        print("Reading from RS232 interface...")
        try:
            while True:
                data = reader.read_serial()
                if data:
                    print(f"Reading: {data}")
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nStopping RS232 reading")
            
    elif reader.connect_hid():
        print("Reading from HID interface...")
        try:
            while True:
                data = reader.read_hid()
                if data:
                    print(f"HID: {data}")
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nStopping HID reading")
            
    else:
        print("Failed to connect to either interface")
        
    reader.disconnect()

if __name__ == "__main__":
    main()

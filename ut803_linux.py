"""
UT803 Multimeter Reader - Supports both HID and RS232 interfaces
"""

import hid
import serial
import time
import sys
import logging
import json
import websockets
import asyncio
import argparse
from typing import Optional, Tuple
from datetime import datetime
import socket

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('UT803')

sys.stdout.reconfigure(line_buffering=True)

class UT803Reader:
    def __init__(self, measurement_time: int = 10):
        self.device = None
        self.serial_port = None
        self.websocket = None
        self.measurement_time = measurement_time
        self.start_time = None
        self.last_reading = None
        self.is_running = True
        
        
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
            self.serial_port.reset_input_buffer()
            self.serial_port.reset_output_buffer()

            time.sleep(0.5)
            self.serial_port.write(b'*IDN?\n')
            response = self.serial_port.readline()
            if response:
                logger.info(f"Successfully connected to RS232 port {port}")
                return True
            else:
                logger.error("No response from device")
                return False
                
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

                    time.sleep(0.5)
                    data = self.device.read(64, timeout_ms=1000)
                    if data:
                        logger.info(f"Successfully connected to HID device {vid:04X}:{pid:04X}")
                        return True
                    else:
                        logger.error("No response from HID device")
                        self.device.close()
                        self.device = None
                        return False
                        
            logger.error("No HID device found")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to HID: {str(e)}")
            if self.device:
                try:
                    self.device.close()
                except:
                    pass
                self.device = None
            return False

    async def connect_websocket(self):
        """Connect to WebSocket server"""
        max_retries = 5
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Attempting to connect to WebSocket server (attempt {attempt + 1}/{max_retries})...")
                
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                result = sock.connect_ex(('127.0.0.1', 8767))
                sock.close()
                
                if result != 0:
                    logger.error(f"WebSocket server is not running on port 8767 (error code: {result})")
                    logger.error("Please make sure main.py is running")
                    if attempt < max_retries - 1:
                        logger.info(f"Retrying in {retry_delay} seconds...")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                    continue
                
                logger.info("Server is running, attempting WebSocket connection...")
                self.websocket = await websockets.connect(
                    'ws://127.0.0.1:8767',
                    ping_interval=None,
                    ping_timeout=None,
                    close_timeout=5,
                    max_size=None,
                    compression=None
                )
                logger.info("Successfully connected to WebSocket server")
                return True
                
            except ConnectionRefusedError:
                logger.error("Connection refused. Make sure the WebSocket server (main.py) is running.")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error("Failed to connect after all attempts. Please start the WebSocket server first.")
                    return False
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {str(e)}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error("Failed to connect to WebSocket server after all attempts")
                    return False

    def decode_ut803_data(self, data: str) -> Tuple[dict, str]:
        """Decode UT803 data format into structured data and human readable format"""
        try:
            data = data.strip().replace('\x00', '')
            
            parts = data.split(';')
            if len(parts) != 2:
                return None, "Invalid data format"
                
            value_str = parts[0].strip('@')
            function_code = parts[1]
            
            try:
                if value_str.startswith('?'):
                    value = "OL"
                else:
                    raw_value = float(value_str)
                    if function_code.startswith('8'):
                        value = raw_value/1000
                    else:
                        value = raw_value/1000
                    value = f"{value:.3f}"
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
            
            current_time = datetime.now()
            timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            
            if value == "OL":
                json_data = {
                    'timestamp': timestamp,
                    'value': "OL",
                    'unit': unit,
                    'mode': mode,
                    'range_str': "AUTO",
                    'measure_type': measure_type,
                    'raw_data': data
                }
                human_readable = f"[{timestamp}] OL {mode} AUTO"
                return json_data, human_readable
            elif value == "Error":
                return None, "Error"
            else:
                json_data = {
                    'timestamp': timestamp,
                    'value': value,  
                    'unit': unit,
                    'mode': mode,
                    'range_str': "AUTO",
                    'measure_type': measure_type,
                    'raw_data': data
                }
                human_readable = f"[{timestamp}] {value} {unit} {mode} AUTO [{measure_type}]"
                return json_data, human_readable
                
        except Exception as e:
            logger.error(f"Error decoding data: {str(e)}")
            return None, f"Error: {str(e)}"

    async def send_measurement(self, data: dict):
        """Send measurement data to WebSocket server"""
        if self.websocket and data:
            try:
                await self.websocket.send(json.dumps(data))
            except Exception as e:
                logger.error(f"Error sending data: {str(e)}")
            
    def read_serial(self) -> Tuple[Optional[dict], Optional[str]]:
        """Read data from RS232 interface"""
        if not self.serial_port:
            return None, None
        try:
            self.serial_port.reset_input_buffer()
            
            data = self.serial_port.readline()
            if data:
                decoded_data = data.decode('ascii').strip()
                json_data, human_readable = self.decode_ut803_data(decoded_data)
                

                if json_data and json_data.get('value') == self.last_reading:
                    return None, None
                    
                self.last_reading = json_data.get('value') if json_data else None
                return json_data, human_readable
                
        except Exception as e:
            logger.error(f"Error reading from RS232: {str(e)}")
        return None, None
        
    def read_hid(self) -> Tuple[Optional[dict], Optional[str]]:
        """Read data from HID interface"""
        if not self.device:
            return None, None
        try:
            data = self.device.read(64, timeout_ms=1000)
            if data:
                json_data, human_readable = self.decode_ut803_data(str(data))
                

                if json_data and json_data.get('value') == self.last_reading:
                    return None, None
                    
                self.last_reading = json_data.get('value') if json_data else None
                return json_data, human_readable
                
        except Exception as e:
            logger.error(f"Error reading from HID: {str(e)}")
        return None, None

    async def receive_messages(self):
        """Receive messages from WebSocket server"""
        if not self.websocket:
            return
            
        try:
            while self.is_running:
                try:
                    message = await self.websocket.recv()
                    data = json.loads(message)
                    
                    if "status" in data and data["status"] == "complete":
                        logger.info(f"Received completion message. Total measurements: {data.get('count', 0)}")
                        self.is_running = False
                        break
                except websockets.exceptions.ConnectionClosed:
                    break
                except Exception as e:
                    logger.error(f"Error receiving message: {str(e)}")
                    break
        except Exception as e:
            logger.error(f"Error in receive_messages: {str(e)}")

    async def run(self):
        """Main measurement loop"""
        if not await self.connect_websocket():
            return

        self.start_time = time.time()
        self.is_running = True
        
        try:
            while self.is_running and (time.time() - self.start_time < self.measurement_time):
                measurement = None
                human_readable = None
                
                if self.serial_port:
                    measurement, human_readable = self.read_serial()
                elif self.device:
                    measurement, human_readable = self.read_hid()

                if measurement and human_readable:
                    try:
                        await self.websocket.send(json.dumps(measurement))
                        print(human_readable)
                    except Exception as e:
                        logger.error(f"Error sending data: {str(e)}")

                        if not await self.connect_websocket():
                            break
                
                await asyncio.sleep(0.1)

        except KeyboardInterrupt:
            logger.info("\nStopping measurement...")
        finally:
            self.is_running = False
            await self.disconnect()

    async def disconnect(self):
        """Disconnect from all interfaces"""
        if self.serial_port:
            self.serial_port.close()
            self.serial_port = None
        if self.device:
            self.device.close()
            self.device = None
        if self.websocket:
            await self.websocket.close()
            self.websocket = None

def parse_args():
    parser = argparse.ArgumentParser(description='UT803 Multimeter Reader')
    parser.add_argument('--measurement_time', type=int, default=10,
                      help='Measurement time in seconds (default: 10)')
    return parser.parse_args()
            
async def main():
    args = parse_args()
    reader = UT803Reader(measurement_time=args.measurement_time)
    
    if reader.connect_serial():
        logger.info("Reading from RS232 interface...")
        await reader.run()
    elif reader.connect_hid():
        logger.info("Reading from HID interface...")
        await reader.run()
    else:
        logger.error("Failed to connect to either interface")

if __name__ == "__main__":
    asyncio.run(main())
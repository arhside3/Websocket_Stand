#!/usr/bin/env python3
"""
    HID readout tool for UNI-T UT803 multimeter
    Modified version for HID interface (VID=0x1A86, PID=0xE008)
"""

import sys
import time
import hid
import argparse
from collections import deque

def chrToInt(c):
    """Convert special UT803 character to integer"""
    num = ord(c) - 48
    if 0 <= num <= 15:
        return num
    raise ValueError(f"Invalid numeric character: {c} (0x{ord(c):02X})")

class UT803_HID:
    MEASUREMENT_TYPES = {
        1: "diode",
        2: "frequency",
        3: "resistance",
        4: "temperature",
        5: "continuity",
        6: "capacitance",
        9: "current",
        11: "voltage",
        13: "current",
        14: "hFE",
        15: "current",
    }

    def __init__(self, vid=0x1A86, pid=0xE008):
        self.vid = vid
        self.pid = pid
        self.device = None
        self.buffer = deque(maxlen=64)
        self.connect()

    def connect(self):
        try:
            print("Available HID devices:")
            for dev in hid.enumerate():
                print(f"  VID: 0x{dev['vendor_id']:04X}, PID: 0x{dev['product_id']:04X}")
            
            self.device = hid.device()
            self.device.open(self.vid, self.pid)
            print(f"Connected to HID device {self.vid:04X}:{self.pid:04X}")
            self.device.set_nonblocking(1)
        except Exception as e:
            raise IOError(f"HID device error: {str(e)}")

    def read_raw_packet(self):
        """Read exactly 11 bytes of data (UT803 packet)"""
        packet = bytearray()
        timeout = time.time() + 1.0  # 1 second timeout

        while len(packet) < 11 and time.time() < timeout:
            data = self.device.read(64)
            if data:
                self.buffer.extend(data)

            # Try to extract 11-byte packet from buffer
            while len(self.buffer) >= 11:
                # Найдите начало пакета
                for i in range(len(self.buffer) - 10):
                    if 0x30 <= self.buffer[i] <= 0x3F:
                        packet = bytes([self.buffer[j] for j in range(i, i + 11)])  # Извлекаем пакет
                        # Удаляем обработанные байты
                        for _ in range(i + 11):
                            self.buffer.popleft()  # Убираем один элемент за раз
                        return packet

                # Если пакет не найден, удаляем первый байт
                self.buffer.popleft()

        return None

    def read(self):
        try:
            packet = self.read_raw_packet()
            if not packet:
                return None
                
            # Convert to ASCII string
            line = packet.decode('ascii', errors='replace')
            if len(line) < 11:
                print(f"Short packet: {packet.hex()}")
                return None
                
            return self.parse(line)
        except Exception as e:
            print(f"Read error: {str(e)}", file=sys.stderr)
            return None

    def parse(self, line):
        try:
            # Byte positions as per protocol
            exponent = chrToInt(line[0])
            base_value = line[1:5]
            measurement = chrToInt(line[5])
            flags = [chrToInt(c) for c in line[6:9]]
            
            # Validate data
            if not base_value.isdigit():
                print(f"Invalid base value: {base_value}")
                return None
                
            meas_type = self.MEASUREMENT_TYPES.get(measurement, "unknown")
            unit = self.get_unit(measurement, flags)
            
            # Calculate value
            exponent += self.get_exponent_offset(unit, exponent)
            value = float(base_value) * (10 ** exponent)
            
            # Handle sign
            if flags[0] & 0x4:
                value = -value

            # Parse flags
            flags_dict = {
                'overload': bool(flags[0] & 0x1),
                'sign': bool(flags[0] & 0x4),
                'not_farenheit': bool(flags[0] & 0x8),
                'min': bool(flags[1] & 0x2),
                'max': bool(flags[1] & 0x4),
                'hold': bool(flags[1] & 0x8),
                'autorange': bool(flags[2] & 0x2),
                'ac': bool(flags[2] & 0x4),
                'dc': bool(flags[2] & 0x8)
            }

            return (value, unit, meas_type, flags_dict)

        except Exception as e:
            print(f"Parse error in line '{line}': {str(e)}", file=sys.stderr)
            return None

    def get_unit(self, measurement, flags):
        units = {
            1: "V",
            2: "Hz",
            3: "Ω",
            4: "°C" if flags[0] & 0x8 else "°F",
            5: "Ω",
            6: "F",
            9: "A",
            11: "V",
            13: "μA",
            14: "",
            15: "mA",
        }
        return units.get(measurement, "???")

    def get_exponent_offset(self, unit, exponent):
        offsets = {
            "V": -3,
            "Ω": -1,
            "A": -2,
            "mA": -2,
            "μA": -1,
            "F": -12,
        }
        offset = offsets.get(unit, 0)
        if unit == "V" and (exponent & 0x4):
            offset += 2
        return offset

    def close(self):
        if self.device:
            self.device.close()

def pretty_value(value, unit):
    prefixes = {
        -12: 'p',
        -9: 'n',
        -6: 'μ',
        -3: 'm',
        0: '',
        3: 'k',
        6: 'M'
    }
    
    if value == 0:
        return "0.000 " + unit
    
    exponent = 0
    abs_val = abs(value)
    
    while abs_val >= 1000 and exponent <= 6:
        abs_val /= 1000
        exponent += 3
        
    while abs_val < 1 and exponent >= -12:
        abs_val *= 1000
        exponent -= 3
        
    value = abs_val if value > 0 else -abs_val
    return f"{value:.3f} {prefixes.get(exponent, '')}{unit}"

def main():
    parser = argparse.ArgumentParser(description="UT803 Multimeter HID Reader")
    parser.add_argument("-o", "--output", default="-", 
                      help="Output file (default: stdout)")
    parser.add_argument("-v", "--vid", type=lambda x: int(x, 16), default=0x1A86,
                      help="Vendor ID in hex (default: 0x1A86)")
    parser.add_argument("-p", "--pid", type=lambda x: int(x, 16), default=0xE008,
                      help="Product ID in hex (default: 0xE008)")
    parser.add_argument("-m", "--monitor", action="store_true",
                      help="Show live measurements in console")
    parser.add_argument("--debug", action="store_true",
                      help="Show raw data for debugging")
    args = parser.parse_args()

    try:
        meter = UT803_HID(args.vid, args.pid)
        output = sys.stdout if args.output == "-" else open(args.output, "w")
        
        print("Starting measurement...", file=sys.stderr)
        print("# timestamp,value,unit,type,overload,sign,min,max,hold,autorange,ac,dc", 
              file=output)
        
        while True:
            data = meter.read()
            if data:
                value, unit, meas_type, flags = data
                timestamp = time.time()
                
                # Write to output
                output.write(
                    f"{timestamp:.3f},{value:.6f},{unit},{meas_type},"
                    f"{int(flags['overload'])},{int(flags['sign'])},"
                    f"{int(flags['min'])},{int(flags['max'])},"
                    f"{int(flags['hold'])},{int(flags['autorange'])},"
                    f"{int(flags['ac'])},{int(flags['dc'])}\n"
                )
                output.flush()
                
                # Live monitoring
                if args.monitor:
                    value_str = pretty_value(value, unit)
                    active_flags = [f for f, v in flags.items() if v]
                    flags_str = ",".join(active_flags) if active_flags else "none"
                    print(f"\r[{meas_type:10}] {value_str:15} [{flags_str:20}]", end="")
            
            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nMeasurement stopped by user")
    except Exception as e:
        print(f"\nError: {str(e)}", file=sys.stderr)
    finally:
        meter.close()
        if output != sys.stdout:
            output.close()

if __name__ == "__main__":
    main()

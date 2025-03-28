#!/usr/bin/env python3
""" HID readout tool for UNI-T UT803 multimeter Modified version for HID interface (VID=0x1A86, PID=0xE008) """

import sys
import time
import hid
import argparse
from collections import deque

def chr_to_decimal(c):
    """ Convert special UT803 character to decimal number. Characters are consecutive in ASCII table starting from ':' (58). """
    num = ord(c) - 58  # Subtract ASCII code of ':'
    if 0 <= num <= 7:
        return num
    elif c == '?':
        return 15
    raise ValueError(f"Invalid numeric character: {c} (0x{ord(c):02X})")

class UT803_HID:
    MEASUREMENT_TYPES = {
        1: "Diode Test",
        2: "Frequency",
        3: "Resistance",
        4: "Temperature",
        5: "Continuity",
        6: "Capacitance",
        9: "Current (A)",
        11: "Voltage",
        13: "Current (uA)",
        14: "hFE",
        15: "Current (mA)"
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
                print(f" VID: 0x{dev['vendor_id']:04X}, PID: 0x{dev['product_id']:04X}")

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
                # Look for valid packet starting with ASCII character in range 0x30-0x3F
                for i in range(len(self.buffer) - 10):
                    if 0x30 <= self.buffer[i] <= 0x3F:
                        packet = bytes([self.buffer[j] for j in range(i, i + 11)])
                        # Remove processed bytes
                        for _ in range(i + 11):
                            self.buffer.popleft()
                        return packet

                # If no valid packet found, remove first byte
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
            exponent = chr_to_decimal(line[0])  # Exponent (byte 0)
            base_value = ''.join(str(chr_to_decimal(c)) for c in line[1:5])  # Base value (bytes 1-4)
            measurement_type = chr_to_decimal(line[5])  # Measurement type (byte 5)
            flags = [chr_to_decimal(c) for c in line[6:9]]  # Flags (bytes 6-8)

            # Get measurement type name
            meas_type_name = self.MEASUREMENT_TYPES.get(measurement_type, "Unknown")

            # Calculate final value
            value = int(base_value) * (10 ** exponent)

            # Apply sign based on flags
            if flags[0] & 0x4:
                value = -value

            # Interpret flags
            overload = bool(flags[0] & 0x1)
            sign = bool(flags[0] & 0x4)
            min_mode = bool(flags[1] & 0x2)
            max_mode = bool(flags[1] & 0x4)
            hold_mode = bool(flags[1] & 0x8)
            autorange = bool(flags[2] & 0x2)
            ac_mode = bool(flags[2] & 0x4)
            dc_mode = bool(flags[2] & 0x8)

            # Return parsed result
            return {
                'value': value,
                'measurement_type': meas_type_name,
                'overloaded': overload,
                'signed': sign,
                'min_mode': min_mode,
                'max_mode': max_mode,
                'hold_mode': hold_mode,
                'autorange': autorange,
                'ac_mode': ac_mode,
                'dc_mode': dc_mode
            }

        except Exception as e:
            print(f"Parse error in line '{line}': {str(e)}", file=sys.stderr)
            return None

    def close(self):
        if self.device:
            self.device.close()

def pretty_print_measurement(measurement):
    """ Format and print measurement in human-readable form. """
    value = measurement['value']
    measurement_type = measurement['measurement_type']
    overload = measurement['overloaded']
    signed = measurement['signed']
    min_mode = measurement['min_mode']
    max_mode = measurement['max_mode']
    hold_mode = measurement['hold_mode']
    autorange = measurement['autorange']
    ac_mode = measurement['ac_mode']
    dc_mode = measurement['dc_mode']

    # Prepare message
    msg = f"Value: {value}, "
    msg += f"Type: {measurement_type}, "
    msg += f"Overload: {'Yes' if overload else 'No'}, "
    msg += f"Signed: {'Yes' if signed else 'No'}, "
    msg += f"Min Mode: {'On' if min_mode else 'Off'}, "
    msg += f"Max Mode: {'On' if max_mode else 'Off'}, "
    msg += f"Hold Mode: {'On' if hold_mode else 'Off'}, "
    msg += f"Auto Range: {'On' if autorange else 'Off'}, "
    msg += f"AC Mode: {'On' if ac_mode else 'Off'}, "
    msg += f"DC Mode: {'On' if dc_mode else 'Off'}"

    print(msg)

def main():
    parser = argparse.ArgumentParser(description="UT803 Multimeter HID Reader")
    parser.add_argument("-v", "--vid", type=lambda x: int(x, 16), default=0x1A86,
                        help="Vendor ID in hex (default: 0x1A86)")
    parser.add_argument("-p", "--pid", type=lambda x: int(x, 16), default=0xE008,
                        help="Product ID in hex (default: 0xE008)")
    parser.add_argument("-m", "--monitor", action="store_true",
                        help="Show live measurements in console")
    args = parser.parse_args()

    try:
        meter = UT803_HID(args.vid, args.pid)
        print("Starting measurement...")

        while True:
            measurement = meter.read()
            if measurement:
                pretty_print_measurement(measurement)
            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nMeasurement stopped by user")
    except Exception as e:
        print(f"\nError: {str(e)}", file=sys.stderr)
    finally:
        meter.close()

if __name__ == "__main__":
    main()

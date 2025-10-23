import asyncio
import os
import struct
import sys

import requests
import serial_asyncio

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

UART_PORT = '/dev/ttyUSB1'
UART_BAUDRATE = 115200
PACKET_SIZE = 64
START_SEQ_TEMPATURE = bytes([0x01, 0x02, 0x03, 0x04])
START_SEQ_HIGH_TEMPATURE = bytes([0x03, 0x03, 0x03, 0x03])
START_SEQ_TRACTION = bytes([0x05, 0x02, 0x03, 0x04])


def send_uart_data_via_http(sensor_data):
    """Отправляет UART данные через HTTP на main.py"""
    try:
        requests.post(
            'http://127.0.0.1:8080/uart-data',
            json={'type': 'sensor_data', 'data': sensor_data},
            timeout=2,
        )
        print(f"UART data sent via HTTP: {sensor_data}")
    except Exception as e:
        print(f"HTTP send error: {e}")


def calc_crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc


def decode_high_temperature_payload(
    payload: bytes, command: int
) -> tuple[float, float]:
    try:
        high_temp1 = struct.unpack('<f', bytes(payload[0:4]))[0]
        high_temp2 = struct.unpack('<f', bytes(payload[4:8]))[0]
        return high_temp1, high_temp2
    except Exception as e:
        print(f"Error decoding high temperature: {e}")
        return 0.0, 0.0


def decode_temperature_payload(
    payload: bytes, command: int
) -> tuple[float, float]:
    try:
        temp1 = payload[0] | (payload[1] << 8)
        temp2 = payload[2] | (payload[3] << 8)
        return temp1 / 100, temp2 / 100
    except Exception as e:
        print(f"Error decoding temperature: {e}")
        return 0.0, 0.0


def decode_traction_payload(payload: bytes, command: int) -> float:
    try:
        weight = payload[2] | (payload[3] << 8)
        return weight / 1000
    except Exception as e:
        print(f"Error decoding traction: {e}")
        return 0.0


class UARTProtocol(asyncio.Protocol):
    def __init__(self):
        self.buffer = bytearray()
        self.transport = None
        self.connection_ready = asyncio.Event()
        self.waiting_for_packet = False
        self.expected_packet_start = None

    def connection_made(self, transport):
        self.transport = transport
        print("UART connection established")
        self.connection_ready.set()

    def data_received(self, data):
        self.buffer.extend(data)
        while True:
            if not self.waiting_for_packet:
                found = self._find_start_sequence()
                if not found:
                    break
            if self.waiting_for_packet:
                if len(self.buffer) < PACKET_SIZE:
                    break
                self._read_complete_packet()
                if len(self.buffer) < PACKET_SIZE:
                    break

    def _find_start_sequence(self):
        pos_temp = self.buffer.find(START_SEQ_TEMPATURE)
        pos_high_temp = self.buffer.find(START_SEQ_HIGH_TEMPATURE)
        pos_trac = self.buffer.find(START_SEQ_TRACTION)

        positions = []
        if pos_temp != -1:
            positions.append((pos_temp, START_SEQ_TEMPATURE))
        if pos_trac != -1:
            positions.append((pos_trac, START_SEQ_TRACTION))
        if pos_high_temp != -1:
            positions.append((pos_high_temp, START_SEQ_HIGH_TEMPATURE))

        if not positions:
            if len(self.buffer) > 64:
                print(
                    f"No start sequence found. Discarding first 10 bytes. Sample: {self.buffer[:10].hex()}"
                )
                del self.buffer[:10]
            else:
                print(
                    "No start sequence found. Clearing buffer",
                    self.buffer.hex(),
                )
                self.buffer.clear()
            return False

        pos, seq = min(positions, key=lambda x: x[0])
        if pos > 0:
            del self.buffer[:pos]
        self.expected_packet_start = seq
        self.waiting_for_packet = True
        print(f"Start sequence found at position {pos} (type: {seq.hex()})")
        return True

    def _read_complete_packet(self):
        packet = bytes(self.buffer[:PACKET_SIZE])
        if packet[:4] != self.expected_packet_start:
            self.waiting_for_packet = False
            self.expected_packet_start = None
            del self.buffer[0]
            self._find_start_sequence()
            return

        calc_crc = calc_crc16(packet[4:62])
        recv_crc = (packet[62] << 8) | packet[63]
        if calc_crc == recv_crc:
            del self.buffer[:PACKET_SIZE]
            command = packet[4]
            payload_len = packet[6]
            print(
                f"Valid packet received - Command: 0x{command:02X}, Payload length: {payload_len}, Raw: {packet.hex()}"
            )

            sensor_data = {}

            if self.expected_packet_start == START_SEQ_TEMPATURE:
                temp1, temp2 = decode_temperature_payload(
                    packet[7 : 7 + 55], command
                )
                sensor_data['tempNormal1'] = temp1
                sensor_data['tempNormal2'] = temp2
                print(f"Decoded temperatures: temp1={temp1}, temp2={temp2}")

            elif self.expected_packet_start == START_SEQ_TRACTION:
                weight = decode_traction_payload(packet[7 : 7 + 55], command)
                sensor_data['thrust1'] = weight
                print(f"Decoded weight: weight={weight}")

            elif self.expected_packet_start == START_SEQ_HIGH_TEMPATURE:
                high_temp1, high_temp2 = decode_high_temperature_payload(
                    packet[7 : 7 + 55], command
                )
                sensor_data['temp600_1'] = high_temp1
                sensor_data['temp600_2'] = high_temp2
                print(
                    f"Decoded high temperatures: high_temp1={high_temp1}, high_temp2={high_temp2}"
                )

            try:
                send_uart_data_via_http(sensor_data)
            except Exception as e:
                print(f"Error sending via HTTP: {e}")

            self.waiting_for_packet = False
            self.expected_packet_start = None

            if len(self.buffer) > 0:
                self._find_start_sequence()
        else:
            print(
                f"Invalid CRC (got {recv_crc:04X}, calc {calc_crc:04X}), discarding one byte"
            )
            del self.buffer[0]
            self.waiting_for_packet = False
            self.expected_packet_start = None
            self._find_start_sequence()

    def send(self, data: bytes):
        if self.transport:
            self.transport.write(data)
            print(f"Sent {len(data)} bytes: {data.hex()}")
        else:
            print("UART transport not connected")


def build_uart_packet_temprature(command: int) -> bytes:
    DATA_PAYLOAD = 55
    RESP_OK = 0x00

    payload = bytes([0] * DATA_PAYLOAD)
    buffer_crc = bytes([command, RESP_OK, 0]) + payload
    crc_val = calc_crc16(buffer_crc)
    crc_hi = (crc_val >> 8) & 0xFF
    crc_lo = crc_val & 0xFF

    packet = struct.pack(
        f'>4sBBB{DATA_PAYLOAD}sBB',
        START_SEQ_TEMPATURE,
        command,
        RESP_OK,
        0,
        payload,
        crc_hi,
        crc_lo,
    )
    return packet


def build_uart_packet_traction(command: int) -> bytes:
    DATA_PAYLOAD = 55
    RESP_OK = 0x00

    payload = bytes([0] * DATA_PAYLOAD)
    buffer_crc = bytes([command, RESP_OK, 0]) + payload
    crc_val = calc_crc16(buffer_crc)
    crc_hi = (crc_val >> 8) & 0xFF
    crc_lo = crc_val & 0xFF

    packet = struct.pack(
        f'>4sBBB{DATA_PAYLOAD}sBB',
        START_SEQ_TRACTION,
        command,
        RESP_OK,
        0,
        payload,
        crc_hi,
        crc_lo,
    )
    return packet


def build_uart_packet_high_temprature(command: int) -> bytes:
    DATA_PAYLOAD = 55
    RESP_OK = 0x00

    payload = bytes([0] * DATA_PAYLOAD)
    buffer_crc = bytes([command, RESP_OK, 0]) + payload
    crc_val = calc_crc16(buffer_crc)
    crc_hi = (crc_val >> 8) & 0xFF
    crc_lo = crc_val & 0xFF

    packet = struct.pack(
        f'>4sBBB{DATA_PAYLOAD}sBB',
        START_SEQ_HIGH_TEMPATURE,
        command,
        RESP_OK,
        0,
        payload,
        crc_hi,
        crc_lo,
    )
    return packet


async def uart_reader():

    loop = asyncio.get_running_loop()
    protocol_instance = UARTProtocol()
    ports = ['/dev/ttyUSB1', '/dev/ttyUSB0']
    for port in ports:
        try:
            await serial_asyncio.create_serial_connection(
                loop, lambda: protocol_instance, port, baudrate=UART_BAUDRATE
            )
            return protocol_instance
        except:
            print('')


async def periodic_send(protocol: UARTProtocol):
    await protocol.connection_ready.wait()
    print("Starting periodic UART send")

    protocol.send(build_uart_packet_temprature(0x3A))
    await asyncio.sleep(5)

    while True:
        try:
            protocol.send(build_uart_packet_temprature(0x3B))
            print('Temperature')
            await asyncio.sleep(0,1)
            protocol.send(build_uart_packet_traction(0x3B))
            print('Traction')
            await asyncio.sleep(0,5)
            protocol.send(build_uart_packet_high_temprature(0x3B))
            print('High_Temperature')
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            print("Periodic send cancelled")
            break


async def main():
    try:
        protocol = await uart_reader()
        sender_task = asyncio.create_task(periodic_send(protocol))

        await sender_task

    except KeyboardInterrupt:
        print("Program interrupted by user, exiting...")
    except Exception as e:
        print(f"Error in main: {e}")
    finally:
        tasks = [
            t for t in asyncio.all_tasks() if t is not asyncio.current_task()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_when=asyncio.ALL_COMPLETED)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Program interrupted by user, exiting...")

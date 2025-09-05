import asyncio
import struct
import sqlite3
import websockets
from datetime import datetime
import serial_asyncio

UART_PORT = '/dev/ttyUSB0'
UART_BAUDRATE = 115200
WS_URI = 'ws://127.0.0.1:8767'
PACKET_SIZE = 64
START_BYTES = {0xAA, 0xBB}
DB_FILE = 'my_database'

def save_packet_to_db(packet: bytes):
    if len(packet) != PACKET_SIZE:
        return
    start_byte = packet[0]
    command = packet[1]
    status = packet[2]
    payload_len = packet[3]
    payload = packet[4:4+58]
    crc_one = packet[62]
    crc_two = packet[63]
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    con = sqlite3.connect(DB_FILE)
    c = con.cursor()
    c.execute("""
        INSERT INTO uart_packets (timestamp, start_byte, command, status, payload_len, payload, crc_one, crc_two, raw_packet)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (timestamp, start_byte, command, status, payload_len, payload, crc_one, crc_two, packet))
    con.commit()
    con.close()
    print(f"Saved packet at {timestamp}")

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

class UARTProtocol(asyncio.Protocol):
    def __init__(self, queue: asyncio.Queue):
        self.queue = queue
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
                self._find_start_byte()
                if not self.waiting_for_packet:
                    break
            if self.waiting_for_packet:
                if len(self.buffer) < PACKET_SIZE:
                    break
                self._read_complete_packet()
                if len(self.buffer) < PACKET_SIZE:
                    break

    def _find_start_byte(self):
        start_pos = -1
        for i, b in enumerate(self.buffer):
            if b in START_BYTES:
                start_pos = i
                break
        if start_pos == -1:
            if len(self.buffer) > 10:
                print(f"No start byte found. Discarding first 10 bytes. Sample: {self.buffer[:10].hex()}")
                del self.buffer[:10]
            else:
                print("No start byte found. Clearing buffer")
                self.buffer.clear()
            self.waiting_for_packet = False
            self.expected_packet_start = None
        else:
            if start_pos > 0:
                print(f"Discarding {start_pos} bytes before start byte")
                del self.buffer[:start_pos]
            self.expected_packet_start = self.buffer[0]
            self.waiting_for_packet = True

    def _read_complete_packet(self):
        packet = bytes(self.buffer[:PACKET_SIZE])
        if packet[0] != self.expected_packet_start:
            self.waiting_for_packet = False
            self.expected_packet_start = None
            del self.buffer[0]
            self._find_start_byte()
            return
        calc_crc = calc_crc16(packet[1:62])
        recv_crc = (packet[62] << 8) | packet[63]
        if calc_crc == recv_crc:
            del self.buffer[:PACKET_SIZE]
            print(f"Valid packet: {packet.hex()}")
            save_packet_to_db(packet)
            asyncio.create_task(self.queue.put(packet))
            self.waiting_for_packet = False
            self.expected_packet_start = None
            if len(self.buffer) > 0:
                self._find_start_byte()
        else:
            print(f"Invalid CRC (got {recv_crc:04X}, calc {calc_crc:04X}), discard byte")
            del self.buffer[0]
            self.waiting_for_packet = False
            self.expected_packet_start = None
            self._find_start_byte()

    def send(self, data: bytes):
        if self.transport:
            self.transport.write(data)
            print(f"Sent {len(data)} bytes: {data.hex()}")
        else:
            print("UART transport not connected")

async def uart_reader(queue: asyncio.Queue):
    loop = asyncio.get_running_loop()
    protocol_instance = UARTProtocol(queue)
    await serial_asyncio.create_serial_connection(loop, lambda: protocol_instance, UART_PORT, baudrate=UART_BAUDRATE)
    return protocol_instance

def build_uart_packet(command: int, position: int) -> bytes:
    DATA_PAYLOAD = 58
    START_BYTE_LEFT = 0xBB
    START_BYTE_RIGHT = 0xAA
    RESP_OK = 0x00

    start_byte = START_BYTE_LEFT if position == 0 else START_BYTE_RIGHT
    payload = bytes([0] * DATA_PAYLOAD)
    buffer_crc = bytes([command, RESP_OK, 0]) + payload
    crc_val = calc_crc16(buffer_crc)
    crc_hi = (crc_val >> 8) & 0xFF
    crc_lo = crc_val & 0xFF

    packet = struct.pack(f'>BBBB{DATA_PAYLOAD}sBB', start_byte, command, RESP_OK, 0, payload, crc_hi, crc_lo)
    return packet

async def periodic_send(protocol: UARTProtocol):
    await protocol.connection_ready.wait()
    print("Starting periodic UART send")
    protocol.send(build_uart_packet(0x3A, 0))
    await asyncio.sleep(1)
    while True:
        for pos in [0, 1]:
            pkt = build_uart_packet(0x3B, pos)
            protocol.send(pkt)
            print(f"Sent CMD_GET_JOYSTICK_DATA pos={pos}")
            await asyncio.sleep(2)

async def websocket_sender(queue: asyncio.Queue):
    async with websockets.connect(WS_URI) as websocket:
        print("WebSocket connected")
        while True:
            packet = await queue.get()
            await websocket.send(packet)
            print(f"Sent packet over WS: {packet.hex()}")

async def main():
    queue = asyncio.Queue()
    protocol = await uart_reader(queue)
    asyncio.create_task(periodic_send(protocol))
    await websocket_sender(queue)

if __name__ == '__main__':
    asyncio.run(main())

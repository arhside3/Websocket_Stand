import asyncio
import struct
import sqlite3
import websockets
from datetime import datetime
import serial_asyncio
from ctypes import c_int16

UART_PORT = '/dev/ttyUSB0'
UART_BAUDRATE = 115200
WS_URI = 'ws://127.0.0.1:8767'
PACKET_SIZE = 64
START_SEQ_TEMPATURE = bytes([0x01, 0x02, 0x03, 0x04])
START_SEQ_TRACTION = bytes([0x05, 0x02, 0x03, 0x04])
DB_FILE = 'my_database.db'


def save_packet_to_db(packet: bytes):
    if len(packet) != PACKET_SIZE:
        return
    start_bytes = packet[:4]
    command = packet[4]
    status = packet[5]
    payload_len = packet[6]
    payload = packet[7:7 + 55]
    crc_one = packet[62]
    crc_two = packet[63]
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    with sqlite3.connect(DB_FILE) as con:
        c = con.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS uart_packets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                start_bytes BLOB,
                command INTEGER,
                status INTEGER,
                payload_len INTEGER,
                payload BLOB,
                crc_one INTEGER,
                crc_two INTEGER,
                raw_packet BLOB
            );
        """)
        c.execute("""
            INSERT INTO uart_packets (timestamp, start_bytes, command, status, payload_len, payload, crc_one, crc_two, raw_packet)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, start_bytes, command, status, payload_len, payload, crc_one, crc_two, packet))
        con.commit()
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


def decode_temperature_payload(payload: bytes, command: int) -> tuple[float, float]:
    
    temp1 = payload[0] | (payload[1] << 8)
    temp2 = payload[2] | (payload[3] << 8)
    return temp1 / 100, temp2 / 100


def decode_traction_payload(payload: bytes, command: int) -> tuple[float, float]:
    
    weight = payload[2] | (payload[3] << 8)
    return weight / 10


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
        pos_trac = self.buffer.find(START_SEQ_TRACTION)
        
        positions = []
        if pos_temp != -1:
            positions.append((pos_temp, START_SEQ_TEMPATURE))
        if pos_trac != -1:
            positions.append((pos_trac, START_SEQ_TRACTION))
            
        if not positions:
            if len(self.buffer) > 64:
                print(f"No start sequence found. Discarding first 10 bytes. Sample: {self.buffer[:10].hex()}")
                del self.buffer[:10]
            else:
                print("No start sequence found. Clearing buffer")
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
            print(f"Valid packet received - Command: 0x{command:02X}, Payload length: {payload_len}, Raw: {packet.hex()}")
            
            if self.expected_packet_start == START_SEQ_TEMPATURE:
                temp1, temp2 = decode_temperature_payload(packet[7:7+55], command)
                print(f"Decoded temperatures: temp1={temp1}, temp2={temp2}")
            elif self.expected_packet_start == START_SEQ_TRACTION:
                weight = decode_traction_payload(packet[7:7+55], command)
                print(f"Decoded weight: weight={weight}")
                
            save_packet_to_db(packet)
            asyncio.create_task(self.queue.put(packet))
            self.waiting_for_packet = False
            self.expected_packet_start = None
            
            if len(self.buffer) > 0:
                self._find_start_sequence()
        else:
            print(f"Invalid CRC (got {recv_crc:04X}, calc {calc_crc:04X}), discarding one byte")
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

    packet = struct.pack(f'>4sBBB{DATA_PAYLOAD}sBB', START_SEQ_TEMPATURE, command, RESP_OK, 0, payload, crc_hi, crc_lo)
    return packet

def build_uart_packet_traction(command: int) -> bytes:
    DATA_PAYLOAD = 55
    RESP_OK = 0x00

    payload = bytes([0] * DATA_PAYLOAD)
    buffer_crc = bytes([command, RESP_OK, 0]) + payload
    crc_val = calc_crc16(buffer_crc)
    crc_hi = (crc_val >> 8) & 0xFF
    crc_lo = crc_val & 0xFF

    packet = struct.pack(f'>4sBBB{DATA_PAYLOAD}sBB', START_SEQ_TRACTION, command, RESP_OK, 0, payload, crc_hi, crc_lo)
    return packet

async def uart_reader(queue: asyncio.Queue):
    loop = asyncio.get_running_loop()
    protocol_instance = UARTProtocol(queue)
    await serial_asyncio.create_serial_connection(loop, lambda: protocol_instance, UART_PORT, baudrate=UART_BAUDRATE)
    return protocol_instance


async def periodic_send(protocol: UARTProtocol):
    await protocol.connection_ready.wait()
    print("Starting periodic UART send")
    protocol.send(build_uart_packet_temprature(0x3A))
    await asyncio.sleep(5)
    protocol.send(build_uart_packet_traction(0x3A))
    await asyncio.sleep(5)

    while True:
        protocol.send(build_uart_packet_temprature(0x3B))
        print('Temprature')
        await asyncio.sleep(0.1)
        protocol.send(build_uart_packet_traction(0x3B))
        print('Traction')
        await asyncio.sleep(0.1)




async def websocket_sender(queue: asyncio.Queue):
    try:
        async with websockets.connect(WS_URI) as websocket:
            print("WebSocket connected")
            while True:
                packet = await queue.get()
                await websocket.send(packet)
                print(f"Sent packet over WS: {packet.hex()}")
    except asyncio.CancelledError:
        print("WebSocket sender task cancelled")
    except Exception as e:
        print(f"WebSocket connection error: {e}")


async def main():
    queue = asyncio.Queue()
    protocol = await uart_reader(queue)
    sender_task = asyncio.create_task(periodic_send(protocol))
    ws_task = asyncio.create_task(websocket_sender(queue))

    try:
        await ws_task
    except asyncio.CancelledError:
        print("Main task cancelled, shutting down...")
        sender_task.cancel()
        await sender_task


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Program interrupted by user, exiting...")

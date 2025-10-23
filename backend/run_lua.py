import asyncio
import json
import os
import re
import signal
import subprocess
from concurrent.futures import ProcessPoolExecutor

from backend.http_methods import *
from backend.measurement import *
from backend.oscillocsope_visualizer import *
from backend.setup_db import *


def run_lua_script_sync(script_name: str) -> dict:
    """Synchronous version of run_lua_script that runs in a separate process"""
    try:
        env = os.environ.copy()
        env['LUA_PATH'] = '?.lua;' + env.get('LUA_PATH', '')

        process = subprocess.Popen(
            ['lua', script_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            preexec_fn=os.setsid,
        )

        try:
            stdout, stderr = process.communicate(timeout=300)
            return {
                'success': True,
                'output': stdout.decode('utf-8'),
                'error': stderr.decode('utf-8'),
            }
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            return {
                'success': False,
                'error': 'Script execution timed out after 5 minutes',
            }

    except Exception as e:
        return {'success': False, 'error': str(e)}


async def run_lua_script(script_name: str) -> dict:
    """Asynchronous wrapper for run_lua_script_sync"""
    loop = asyncio.get_running_loop()
    with ProcessPoolExecutor() as pool:
        return await loop.run_in_executor(
            pool, run_lua_script_sync, script_name
        )


def run_lua_script_stream(
    script_name: str, on_line, websocket=None, loop=None
) -> bool:
    try:
        env = os.environ.copy()
        env['LUA_PATH'] = '?.lua;' + env.get('LUA_PATH', '')
        process = subprocess.Popen(
            ['lua', script_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            preexec_fn=os.setsid,
            bufsize=1,
            universal_newlines=True,
        )
        multimeter_regex = re.compile(
            r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})\] ([\d.]+) В (DC|AC) AUTO \[Вольтметр\]'
        )
        for line in process.stdout:
            on_line(line.rstrip())
            if websocket and loop:
                match = multimeter_regex.search(line)
                if match:
                    data = {
                        'timestamp': match.group(1),
                        'value': match.group(2),
                        'unit': 'В',
                        'mode': match.group(3),
                        'range_str': 'AUTO',
                        'measure_type': 'Вольтметр',
                    }
                    asyncio.run_coroutine_threadsafe(
                        websocket.send(
                            json.dumps({'type': 'multimeter', 'data': data})
                        ),
                        loop,
                    )
        process.wait()
        return process.returncode == 0
    except Exception as e:
        on_line(f"[ERROR] {e}")
        return False


async def run_lua_script_stream_async(script_name, websocket):
    loop = asyncio.get_running_loop()

    def send_line(line):
        asyncio.run_coroutine_threadsafe(
            websocket.send(json.dumps({'type': 'lua_output', 'line': line})),
            loop,
        )

    success = await loop.run_in_executor(
        None, run_lua_script_stream, script_name, send_line, websocket, loop
    )
    await websocket.send(
        json.dumps({'type': 'lua_status', 'success': success})
    )


async def run_lua_test_parallel_async(script_name, websocket):
    """Запускает main.lua, разбирает вывод и отправляет данные по типу устройства в WebSocket"""
    process = await asyncio.create_subprocess_exec(
        'lua',
        script_name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            decoded = line.decode('utf-8').rstrip()
            if decoded.startswith('[OSC]'):
                await websocket.send(
                    json.dumps(
                        {'type': 'oscilloscope', 'line': decoded[5:].lstrip()}
                    )
                )
            elif decoded.startswith('[MULT]'):
                await websocket.send(
                    json.dumps(
                        {'type': 'multimeter', 'line': decoded[6:].lstrip()}
                    )
                )
            else:
                await websocket.send(
                    json.dumps({'type': 'lua_output', 'line': decoded})
                )
        returncode = await process.wait()
        await websocket.send(
            json.dumps({'type': 'lua_status', 'success': returncode == 0})
        )
    except Exception as e:
        await websocket.send(
            json.dumps(
                {'type': 'lua_status', 'success': False, 'error': str(e)}
            )
        )

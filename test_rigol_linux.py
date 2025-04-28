import pyvisa
import numpy as np
import matplotlib.pyplot as plt
import time
import asyncio
import websockets
import json
import sys

WEBSOCKET_URI = "ws://localhost:8765"


def connect_to_oscilloscope(resource_manager, resource_string):
    try:
        resources = resource_manager.list_resources()
        print("Available VISA resources:", resources)
        
        if not resources:
            print("No VISA resources found. Please check if the oscilloscope is connected.")
            return None
            
        target_resource = None
        for resource in resources:
            if ('USB' in resource and ('6833::1230' in resource or '1AB1::04CE' in resource)):
                target_resource = resource
                break
                
        if not target_resource:
            print("Rigol oscilloscope not found. Please check the connection.")
            return None
            
        print(f"Found oscilloscope at: {target_resource}")
        oscilloscope = resource_manager.open_resource(target_resource)
        print(f"Connected to oscilloscope: {oscilloscope.query('*IDN?')}")
        return oscilloscope
    except pyvisa.errors.VisaIOError as e:
        print(f"Error connecting to oscilloscope: {e}")
        print("Please make sure:")
        print("1. The oscilloscope is connected via USB")
        print("2. You have installed pyvisa-py: pip install pyvisa-py")
        print("3. You have proper permissions (try running with sudo or add user to plugdev group)")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None

def setup_oscilloscope(oscilloscope, channel=1, volts_per_div=1.0, time_per_div='100us'):
    try:

        oscilloscope.write(f':CHAN{channel}:DISP ON') 
        oscilloscope.write(f':CHAN{channel}:VOLT/DIV {volts_per_div}')

        oscilloscope.write(f':TIM:SCAL {time_per_div}')
        oscilloscope.write(':TIM:MODE NORM')


        oscilloscope.write(':TRIG:MODE EDGE')
        oscilloscope.write(f':TRIG:EDGE:SOUR CHAN{channel}')
        oscilloscope.write(':TRIG:EDGE:SLOP POS')
        oscilloscope.write(':TRIG:LEV 1.0')

        print("Осциллограф настроен.")
    except pyvisa.errors.VisaIOError as e:
        print(f"Ошибка настройки осциллографа: {e}")

def get_waveform_data(oscilloscope, channel=1):
    try:

        oscilloscope.write(f':WAV:SOUR CHAN{channel}')
        oscilloscope.write(':WAV:MODE RAW')
        oscilloscope.write(':WAV:FORM BYTE')

        preamble = oscilloscope.query(':WAV:PRE?')
        print("Преамбула:", preamble)


        preamble_values = preamble.split(',')
        y_increment = float(preamble_values[7])
        y_origin = float(preamble_values[8])
        x_increment = float(preamble_values[4])
        x_origin = float(preamble_values[5])

        oscilloscope.write(':WAV:DATA?')

        raw_data = oscilloscope.read_raw()


        waveform_data = np.frombuffer(raw_data[11:], dtype=np.uint8)


        voltage_data = (waveform_data - y_origin) * y_increment


        time_data = np.arange(0, len(voltage_data) * x_increment, x_increment) + x_origin

        return time_data, voltage_data
    except pyvisa.errors.VisaIOError as e:
        print(f"Ошибка получения данных: {e}")
        return None, None


async def send_data_to_server(time_data, voltage_data):
    try:
        async with websockets.connect(WEBSOCKET_URI) as websocket:

            data = {
                'time': time_data.tolist(),
                'voltage': voltage_data.tolist()
            }

            message = json.dumps(data)

            await websocket.send(message)
            print("Данные отправлены на сервер.")

    except Exception as e:
        print(f"Ошибка отправки данных на сервер: {e}")

def plot_waveform(time_data, voltage_data):
    plt.figure(figsize=(10, 6))
    plt.plot(time_data, voltage_data)
    plt.title('Сигнал с осциллографа')
    plt.xlabel('Время (с)')
    plt.ylabel('Напряжение (В)')
    plt.grid()
    plt.show()

def main():
    try:
        rm = pyvisa.ResourceManager('@py')
        print("Using pyvisa-py backend")
        
        oscilloscope = connect_to_oscilloscope(rm, None)
        
        if oscilloscope:
            setup_oscilloscope(oscilloscope, channel=1, volts_per_div=0.5, time_per_div='100us')
            
            time.sleep(2)
            time_data, voltage_data = get_waveform_data(oscilloscope, channel=1)
            
            if time_data is not None and voltage_data is not None:
                asyncio.run(send_data_to_server(time_data, voltage_data))
                plot_waveform(time_data, voltage_data)
            else:
                print("No data available to send to server.")
            
            oscilloscope.close()
            print("Oscilloscope connection closed.")
        else:
            print("Failed to connect to oscilloscope.")
            sys.exit(1)
            
    except Exception as e:
        print(f"Error in main: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

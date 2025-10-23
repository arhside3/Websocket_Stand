import asyncio

http_event_loop = asyncio.get_event_loop()

current_uart_data = {
    'temp600_1': 0.0,
    'temp600_2': 0.0,
    'tempNormal1': 0.0,
    'tempNormal2': 0.0,
    'thrust1': 0.0,
}


HTTP_PORT = 8080

global_multimeter = None
last_multimeter_values = {}
is_measurement_active = True

is_multimeter_running = True
oscilloscope_task = None
multimeter_task = None

current_test_number = None

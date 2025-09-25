import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import traceback


class CustomHTTPRequestHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.error_message_format = '''
        <html>
            <head>
                <meta charset="utf-8">
                <title>Error %(code)d</title>
            </head>
            <body>
                <h1>Error %(code)d</h1>
                <p>%(message)s</p>
            </body>
        </html>
        '''
        super().__init__(*args, **kwargs)

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        try:
            parsed_path = urlparse(self.path)
            path = parsed_path.path
            query = parse_qs(parsed_path.query)

            if path == '/':
                self.serve_file('index.html', 'text/html')
            elif path.endswith('.js'):
                self.serve_file(path[1:], 'text/javascript')
            elif path.endswith('.css'):
                self.serve_file(path[1:], 'text/css')
            elif path.endswith('.html'):
                self.serve_file(path[1:], 'text/html')
            elif path == '/db/oscilloscope':
                from backend.setup_db import get_oscilloscope_data_paginated
                page = int(query.get('page', ['1'])[0])
                per_page = int(query.get('per_page', ['50'])[0])
                self.send_json_response(
                    get_oscilloscope_data_paginated(
                        page=page, per_page=per_page
                    )
                )
            elif path == '/db/multimeter':
                from backend.setup_db import get_multimeter_data_paginated
                page = int(query.get('page', ['1'])[0])
                per_page = int(query.get('per_page', ['50'])[0])
                self.send_json_response(
                    get_multimeter_data_paginated(page=page, per_page=per_page)
                )
            elif path == '/history/oscilloscope':
                from backend.measurement import get_oscilloscope_history
                period = query.get('period', ['hour'])[0]
                self.send_json_response(get_oscilloscope_history(period))
            elif path == '/history/multimeter':
                from backend.measurement import get_multimeter_history
                period = query.get('period', ['hour'])[0]
                self.send_json_response(get_multimeter_history(period))
            elif path == '/db/oscilloscope_history':
                from backend.oscillocsope_visualizer import get_channel_history
                channel = query.get('channel', [None])[0]
                limit = int(query.get('limit', [20])[0])
                if channel:
                    time_arr, voltage_arr = get_channel_history(channel, limit)
                    self.send_json_response(
                        {
                            'channel': channel,
                            'time': time_arr,
                            'voltage': voltage_arr,
                        }
                    )
                else:
                    self.send_error(400, "Channel not specified")
            elif path == '/tests':
                from backend.setup_db import get_test_list
                self.send_json_response(get_test_list())
            elif path.startswith('/tests/'):
                try:
                    from backend.setup_db import get_test_data
                    test_number = int(path.split('/')[-1])
                    data_type = query.get('type', [None])[0]
                    limit = int(query.get('limit', [100])[0])
                    page = int(query.get('page', [1])[0])
                    result = get_test_data(test_number, data_type, limit, page)
                    self.send_json_response(result)
                except ValueError:
                    self.send_error(400, "Invalid test number")
            else:
                self.send_error(404, "File not found")
        except Exception as e:
            print(f"Ошибка при обработке GET запроса: {e}")
            traceback.print_exc()
            self.send_error(500, "Internal server error")

    def do_POST(self):
        """Обработка POST запросов для сохранения данных в БД"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)

            if self.path == '/save_data':
                try:
                    data = json.loads(post_data.decode('utf-8'))
                    data_type = data.get('type')
                    data_content = data.get('data', {})

                    success = False
                    if data_type == 'oscilloscope':
                        from backend.measurement import save_oscilloscope_data
                        success = save_oscilloscope_data(data_content)
                    elif data_type == 'multimeter':
                        from backend.measurement import save_multimeter_data
                        success = save_multimeter_data(data_content)

                    self.send_json_response({'success': success})
                except json.JSONDecodeError:
                    print("Ошибка декодирования JSON данных")
                    self.send_error(400, "Invalid JSON data")
                except Exception as e:
                    print(f"Ошибка при обработке POST данных: {e}")
                    traceback.print_exc()
                    self.send_error(500, "Internal server error")
            else:
                self.send_error(404, "Endpoint not found")
        except Exception as e:
            print(f"Ошибка при обработке POST запроса: {e}")
            traceback.print_exc()
            self.send_error(500, "Internal server error")

    def send_json_response(self, data):
        """Отправляет JSON-ответ"""
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(data).encode('utf-8'))
        except Exception as e:
            print(f"Ошибка при отправке JSON ответа: {e}")
            self.send_error(500, "Internal server error")

    def serve_file(self, filename, content_type):
        try:
            with open(filename, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', f'{content_type}; charset=utf-8')
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404, "File not found")
        except Exception as e:
            print(f"Ошибка при отправке файла {filename}: {e}")
            self.send_error(500, "Internal server error")

    def log_message(self, format, *args):
        pass

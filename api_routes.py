import json
import datetime
import subprocess
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from main import Session, OscilloscopeData

DATABASE_URL = 'sqlite:///my_database.db'
engine = create_engine(DATABASE_URL, echo=False)

router = APIRouter()

class OscilloscopeDataResponse(BaseModel):
    id: int
    timestamp: datetime
    channel: int
    voltage_data: List[float]
    time_data: List[float]

@router.get("/data/latest", response_model=OscilloscopeDataResponse)
def get_latest_data():
    session = Session()
    try:
        latest_data = session.query(OscilloscopeData).order_by(OscilloscopeData.timestamp.desc()).first()
        if not latest_data:
            raise HTTPException(status_code=404, detail="Данные не найдены")
        return latest_data
    finally:
        session.close()

@router.get("/data/range")
def get_data_range(start_time: datetime, end_time: datetime):
    session = Session()
    try:
        data = session.query(OscilloscopeData).filter(
            OscilloscopeData.timestamp.between(start_time, end_time)
        ).all()
        return data
    finally:
        session.close()

@router.get("/data/channel/{channel_id}")
def get_channel_data(channel_id: int, limit: Optional[int] = 100):
    session = Session()
    try:
        data = session.query(OscilloscopeData).filter(
            OscilloscopeData.channel == channel_id
        ).order_by(OscilloscopeData.timestamp.desc()).limit(limit).all()
        return data
    finally:
        session.close()

@router.get("/data/paginated")
def get_paginated_data(page: int = 1, per_page: int = 10):
    session = Session()
    try:
        # Calculate offset
        offset = (page - 1) * per_page
        
        # Get total count
        total_count = session.query(OscilloscopeData).count()
        
        # Get paginated data
        data = session.query(OscilloscopeData)\
            .order_by(OscilloscopeData.timestamp.desc())\
            .offset(offset)\
            .limit(per_page)\
            .all()
            
        return {
            "data": data,
            "total": total_count,
            "page": page,
            "per_page": per_page,
            "total_pages": (total_count + per_page - 1) // per_page
        }
    finally:
        session.close()

class APIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Обработка GET-запросов"""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        query_params = parse_qs(parsed_path.query)
        
        if path == '/history/oscilloscope':
            self.handle_oscilloscope_history(query_params)
        elif path == '/history/multimeter':
            self.handle_multimeter_history(query_params)
        elif path == '/db/oscilloscope':
            self.handle_oscilloscope_db()
        elif path == '/db/multimeter':
            self.handle_multimeter_db()
        elif path == '/run_lua':
            self.handle_run_lua(query_params)
        elif path == '/' or path.endswith('.html') or path.endswith('.js'):
            self.serve_static_file(path)
        else:
            self.send_error(404, "Страница не найдена")
    
    def handle_oscilloscope_history(self, query_params):
        """Получение исторических данных осциллографа"""
        period = query_params.get('period', ['hour'])[0]
        
        try:
            with engine.connect() as conn:
                now = datetime.now()
                if period == 'hour':
                    start_time = now - timedelta(hours=1)
                elif period == 'day':
                    start_time = now - timedelta(days=1)
                else:  # week
                    start_time = now - timedelta(weeks=1)
                
                query = text("""
                    SELECT timestamp, voltage
                    FROM осциллограф
                    WHERE timestamp > :start_time
                    ORDER BY timestamp
                """)
                
                result = conn.execute(query, {"start_time": start_time.strftime("%Y-%m-%d %H:%M:%S")})
                
                timestamps = []
                voltages = []
                for row in result:
                    timestamps.append(row[0])
                    voltages.append(row[1])
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                
                self.wfile.write(json.dumps({
                    'timestamps': timestamps,
                    'voltages': voltages
                }).encode('utf-8'))
        
        except Exception as e:
            print(f"Ошибка при получении истории осциллографа: {e}")
            self.send_error(500, f"Внутренняя ошибка сервера: {e}")
    
    def handle_multimeter_history(self, query_params):
        """Получение исторических данных мультиметра"""
        period = query_params.get('period', ['hour'])[0]
        
        try:
            with engine.connect() as conn:

                now = datetime.now()
                if period == 'hour':
                    start_time = now - timedelta(hours=1)
                elif period == 'day':
                    start_time = now - timedelta(days=1)
                else:  
                    start_time = now - timedelta(weeks=1)
                
                query = text("""
                    SELECT timestamp, value, raw_data
                    FROM мультиметр
                    WHERE timestamp > :start_time
                    ORDER BY timestamp
                """)
                
                result = conn.execute(query, {"start_time": start_time.strftime("%Y-%m-%d %H:%M:%S")})
                
                timestamps = []
                values = []
                raw_data_list = []
                for row in result:
                    timestamps.append(row[0])
                    try:
                        value = float(row[1]) if row[1] != "OL" else None
                        values.append(value)
                        raw_data_list.append(row[2] if row[2] else None)
                    except (ValueError, TypeError):
                        values.append(None)
                        raw_data_list.append(None)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                
                self.wfile.write(json.dumps({
                    'timestamps': timestamps,
                    'values': values,
                    'raw_data': raw_data_list
                }).encode('utf-8'))
        
        except Exception as e:
            print(f"Ошибка при получении истории мультиметра: {e}")
            self.send_error(500, f"Внутренняя ошибка сервера: {e}")
    
    def handle_oscilloscope_db(self):
        """Получение данных осциллографа из БД с пагинацией"""
        try:
            query_params = parse_qs(urlparse(self.path).query)
            page = int(query_params.get('page', ['1'])[0])
            per_page = int(query_params.get('per_page', ['50'])[0])
            offset = (page - 1) * per_page

            with engine.connect() as conn:
                # Получаем общее количество записей
                count_query = text("SELECT COUNT(*) FROM осциллограф")
                total_count = conn.execute(count_query).scalar()
                print(f"[DEBUG] Всего записей в осциллографе: {total_count}")

                # Получаем нужную страницу данных
                query = text("""
                    SELECT id, timestamp, channel, voltage, frequency
                    FROM осциллограф
                    ORDER BY id DESC
                    LIMIT :limit OFFSET :offset
                """)
                result = conn.execute(query, {"limit": per_page, "offset": offset})

                data = []
                for row in result:
                    data.append({
                        'id': row[0],
                        'timestamp': row[1],
                        'channel': row[2],
                        'voltage': row[3],
                        'frequency': row[4]
                    })

                response = {
                    'data': data,
                    'total': total_count,
                    'page': page,
                    'per_page': per_page,
                    'total_pages': (total_count + per_page - 1) // per_page
                }

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode('utf-8'))

        except Exception as e:
            print(f"Ошибка при получении данных осциллографа: {e}")
            self.send_error(500, f"Внутренняя ошибка сервера: {e}")
    
    def handle_multimeter_db(self):
        """Получение данных мультиметра из БД с пагинацией"""
        try:
            query_params = parse_qs(urlparse(self.path).query)
            page = int(query_params.get('page', ['1'])[0])
            per_page = int(query_params.get('per_page', ['50'])[0])
            offset = (page - 1) * per_page

            with engine.connect() as conn:
                # Получаем общее количество записей
                count_query = text("SELECT COUNT(*) FROM мультиметр")
                total_count = conn.execute(count_query).scalar()
                print(f"[DEBUG] Всего записей в мультиметре: {total_count}")

                # Получаем нужную страницу данных
                query = text("""
                    SELECT id, timestamp, value, raw_data
                    FROM мультиметр
                    ORDER BY id DESC
                    LIMIT :limit OFFSET :offset
                """)
                result = conn.execute(query, {"limit": per_page, "offset": offset})

                data = []
                for row in result:
                    data.append({
                        'id': row[0],
                        'timestamp': row[1],
                        'value': row[2],
                        'raw_data': row[3]
                    })

                response = {
                    'data': data,
                    'total': total_count,
                    'page': page,
                    'per_page': per_page,
                    'total_pages': (total_count + per_page - 1) // per_page
                }

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode('utf-8'))

        except Exception as e:
            print(f"Ошибка при получении данных мультиметра: {e}")
            self.send_error(500, f"Внутренняя ошибка сервера: {e}")
    
    def handle_run_lua(self, query_params):
        """Запуск Lua-скрипта"""
        script = query_params.get('script', ['main.lua'])[0]
        
        try:
            process = subprocess.Popen(['lua', script], 
                                     stdout=subprocess.PIPE, 
                                     stderr=subprocess.PIPE,
                                     text=True)
            
            stdout, stderr = process.communicate(timeout=5)
            
            response = {
                'success': process.returncode == 0,
                'output': stdout,
                'error': stderr if process.returncode != 0 else None
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            self.wfile.write(json.dumps(response).encode('utf-8'))
        
        except Exception as e:
            print(f"Ошибка при запуске Lua-скрипта: {e}")
            self.send_error(500, f"Внутренняя ошибка сервера: {e}")
    
    def serve_static_file(self, path):
        """Обслуживание статических файлов"""
        if path == '/':
            path = '/index.html'
        
        try:
            content_type = 'text/html'
            if path.endswith('.js'):
                content_type = 'text/javascript'
            elif path.endswith('.css'):
                content_type = 'text/css'
            
            with open('.' + path, 'rb') as file:
                content = file.read()

            self.send_response(200)
            self.send_header('Content-type', content_type)
            self.end_headers()
            
            self.wfile.write(content)
        
        except FileNotFoundError:
            self.send_error(404, "Файл не найден")
        except Exception as e:
            print(f"Ошибка при обслуживании статического файла: {e}")
            self.send_error(500, f"Внутренняя ошибка сервера: {e}")

def run_http_server(port=8080):
    """Запуск HTTP-сервера"""
    server_address = ('', port)
    httpd = HTTPServer(server_address, APIHandler)
    print(f"HTTP-сервер запущен на порту {port}")
    httpd.serve_forever()

if __name__ == "__main__":
    run_http_server()
import asyncio
import json

active_websockets = set()


async def send_to_all_websocket_clients(message):
    global active_websockets
    if active_websockets:
        websockets_to_remove = []
        send_tasks = []
        for client in active_websockets:
            try:
                if hasattr(client, 'open') and client.open:
                    send_task = asyncio.create_task(
                        client.send(json.dumps(message))
                    )
                    send_tasks.append(send_task)
                else:
                    websockets_to_remove.append(client)
            except Exception as e:
                print(f"Ошибка отправки сообщения клиенту: {e}")
                websockets_to_remove.append(client)
        for client in websockets_to_remove:
            if client in active_websockets:
                active_websockets.remove(client)
        if send_tasks:
            await asyncio.wait(send_tasks, return_when=asyncio.ALL_COMPLETED)

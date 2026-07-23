#!/usr/bin/env python3
"""Glupia rura: broadcast WebSocket na localhost:8765. Zero persystencji."""
import asyncio
import os
import websockets

PORT = int(os.environ.get("CHAT_PORT", 8765))

clients = set()


async def handler(websocket):
    clients.add(websocket)
    print(f"[+] connected {websocket.remote_address} (total={len(clients)})", flush=True)
    try:
        async for message in websocket:
            print(f"[>] {websocket.remote_address}: {message}", flush=True)
            others = clients - {websocket}
            if others:
                await asyncio.gather(
                    *(ws.send(message) for ws in others), return_exceptions=True
                )
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        clients.discard(websocket)
        print(f"[-] disconnected {websocket.remote_address} (total={len(clients)})", flush=True)


async def main():
    async with websockets.serve(handler, "localhost", PORT):
        print(f"server listening on ws://localhost:{PORT}", flush=True)
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())

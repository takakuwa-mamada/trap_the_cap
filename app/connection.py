import os
import json
import asyncio
from fastapi import WebSocket
from redis.asyncio import Redis
from app.models import GameState, ActionLog
from app.engine import init_game, add_player, roll_dice, apply_move

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, List[WebSocket]] = {} # room_id -> [ws]
        self.redis = Redis.from_url(REDIS_URL, decode_responses=True)

    async def connect(self, websocket: WebSocket, room_id: str):
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        self.active_connections[room_id].append(websocket)

    def disconnect(self, websocket: WebSocket, room_id: str):
        if room_id in self.active_connections:
            self.active_connections[room_id].remove(websocket)

    async def get_state(self, room_id: str) -> GameState:
        data = await self.redis.get(f"room:{room_id}")
        if data:
            return GameState.model_validate_json(data)
        return None

    async def save_state(self, state: GameState):
        await self.redis.set(f"room:{state.room_id}", state.model_dump_json(), ex=3600)

    async def broadcast(self, room_id: str, state: GameState):
        if room_id not in self.active_connections: return
        
        # 全員にJSONを送る（本来はPlayerごとに可視情報をフィルタすべきだがMVPは全公開）
        json_data = state.model_dump_json()
        for connection in self.active_connections[room_id]:
            try:
                await connection.send_text(json_data)
            except:
                pass

manager = ConnectionManager()
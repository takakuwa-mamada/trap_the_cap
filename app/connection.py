import os
import json
import asyncio
import logging
from typing import Optional, Dict, List
from fastapi import WebSocket
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from app.models import GameState, ActionLog, GameConfig, Board
from app.engine import (
    init_game, add_player, roll_dice, apply_move,
    get_legal_stacks, get_legal_directions
)

logger = logging.getLogger(__name__)

class InMemoryStore:
    """In-memory fallback for local development without Redis"""
    def __init__(self):
        self.store: Dict[str, str] = {}
        logger.info("Using in-memory store (Redis not available)")
    
    async def get(self, key: str) -> Optional[str]:
        return self.store.get(key)
    
    async def set(self, key: str, value: str, ex: Optional[int] = None):
        self.store[key] = value
    
    async def delete(self, key: str):
        self.store.pop(key, None)
    
    async def close(self):
        pass

# RenderのRedisは 'REDIS_URL' で渡ってきますが、念のためチェック
REDIS_URL = os.getenv("REDIS_URL")

class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, List[WebSocket]] = {} # room_id -> [ws]
        
        # Redisが利用可能な場合は使う、そうでなければインメモリ
        if REDIS_URL:
            try:
                self.redis = Redis.from_url(REDIS_URL, decode_responses=True)
                logger.info(f"Connected to Redis at {REDIS_URL}")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}. Using in-memory store.")
                self.redis = InMemoryStore()
        else:
            logger.info("REDIS_URL not set. Using in-memory store for local development.")
            self.redis = InMemoryStore()

    async def connect(self, websocket: WebSocket, room_id: str):
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        self.active_connections[room_id].append(websocket)

    def disconnect(self, websocket: WebSocket, room_id: str):
        if room_id in self.active_connections:
            self.active_connections[room_id].remove(websocket)

    async def get_state(self, room_id: str) -> Optional[GameState]:
        try:
            data = await self.redis.get(f"room:{room_id}")
            if data:
                return GameState.model_validate_json(data)
        except RedisConnectionError as e:
            logger.error(f"Redis connection error: {e}")
        return None

    async def save_state(self, state: GameState):
        try:
            await self.redis.set(f"room:{state.room_id}", state.model_dump_json(), ex=3600)
        except RedisConnectionError as e:
            logger.error(f"Redis save error: {e}")

    async def broadcast(self, room_id: str, state: GameState):
        if room_id not in self.active_connections:
            logger.warning(f"No active connections for room: {room_id}")
            return
        
        # 全員にJSONを送る（本来はPlayerごとに可視情報をフィルタすべきだがMVPは全公開）
        json_data = state.model_dump_json()
        logger.info(f"Broadcasting to {len(self.active_connections[room_id])} clients in room {room_id}")
        
        for connection in self.active_connections[room_id]:
            try:
                await connection.send_text(json_data)
                logger.debug(f"Sent state update to client")
            except Exception as e:
                logger.error(f"Failed to send to client: {e}")
    
    async def close(self):
        """Cleanup resources"""
        try:
            await self.redis.close()
        except Exception as e:
            logger.error(f"Error closing Redis: {e}")

manager = ConnectionManager()
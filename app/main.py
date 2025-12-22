import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from app.connection import manager
from app.models import ClientAction, GameConfig
from app.engine import init_game, add_player, roll_dice, apply_move

app = FastAPI()
app.mount("/static", StaticFiles(directory="static", html=True), name="static")

@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")

@app.websocket("/ws/{room_id}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, player_id: str):
    await manager.connect(websocket, room_id)
    
    # ルーム初期化チェック
    state = await manager.get_state(room_id)
    if not state:
        # Load board data
        with open("app/data/board_4p.json") as f:
            board_data = json.load(f)
        state = init_game(room_id, board_data, GameConfig())
        # Bot補充タスク起動
        asyncio.create_task(bot_filler_task(room_id))
    
    # プレイヤー参加
    state = add_player(state, player_id, f"Player {player_id[:4]}")
    await manager.save_state(state)
    await manager.broadcast(room_id, state)

    try:
        while True:
            data = await websocket.receive_text()
            action_dict = json.loads(data)
            action = ClientAction(**action_dict)
            
            # Redisロック（簡易版）
            async with manager.redis.lock(f"lock:{room_id}", timeout=2):
                state = await manager.get_state(room_id)
                
                if action.type == "ROLL":
                    state = roll_dice(state, player_id)
                elif action.type == "MOVE":
                    move_id = action.payload.get("move_id")
                    state = apply_move(state, player_id, move_id)
                elif action.type == "RESET": # デバッグ用
                     pass 

                await manager.save_state(state)
                await manager.broadcast(room_id, state)
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)

async def bot_filler_task(room_id: str):
    """一定時間後に足りない人数分Botを追加する"""
    await asyncio.sleep(5) # デモ用に短く5秒
    
    async with manager.redis.lock(f"lock:{room_id}", timeout=5):
        state = await manager.get_state(room_id)
        if not state: return
        
        missing = state.config.max_players - len(state.players)
        if missing > 0:
            for i in range(missing):
                state = add_player(state, f"bot_{i}", f"Bot {i}", is_bot=True)
            await manager.save_state(state)
            await manager.broadcast(room_id, state)

    # Bot Loop (簡易実装: 自分の番が来たら動く)
    # 本来は別プロセスまたはループで監視するが、ここで簡易ループさせる
    while True:
        await asyncio.sleep(2)
        state = await manager.get_state(room_id)
        if not state or state.phase == "FINISHED": break
        
        current_p = state.players.get(state.current_player_id)
        if current_p and current_p.is_bot:
            async with manager.redis.lock(f"lock:{room_id}", timeout=2):
                # 最新状態再取得
                state = await manager.get_state(room_id)
                if state.current_player_id != current_p.id: continue
                
                if state.phase == "ROLL":
                    state = roll_dice(state, current_p.id)
                elif state.phase == "SELECT" and state.legal_moves:
                    # 戦略: 捕獲できる手があればそれを選ぶ、なければランダム
                    best_move = state.legal_moves[0]
                    for m in state.legal_moves:
                        if "Capture" in m.description:
                            best_move = m
                            break
                    state = apply_move(state, current_p.id, best_move.move_id)
                elif state.phase == "SELECT" and not state.legal_moves:
                     # 手がない場合（roll_diceで処理されるはずだが念のため）
                     pass

                await manager.save_state(state)
                await manager.broadcast(room_id, state)
"""Coppit Online - FastAPIアプリケーションのメインモジュール.

WebSocketサーバー、静的ファイル配信、ゲームロジックの統合を行います。
"""
import asyncio
import json
import os
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse
from app.connection import manager
from app.models import ClientAction, GameConfig, Board, GamePhase, Stack, Direction, PlayerColor
from app.engine import (
    init_game, add_player, roll_dice, apply_move, 
    get_legal_stacks, get_legal_directions, advance_turn,
    get_legal_destination_nodes, calculate_path
)
from app.bot import execute_bot_turn, bot_think_delay

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# 盤面データを起動時にロード（環境に依存しないパス）
BASE_DIR = Path(__file__).resolve().parent.parent
BOARD_PATH = BASE_DIR / "app" / "data" / "board_4p_coppit.json"

print(f"[Startup] Loading board from: {BOARD_PATH}")
print(f"[Startup] File exists: {BOARD_PATH.exists()}")

if not BOARD_PATH.exists():
    # フォールバック: カレントディレクトリからの相対パス
    BOARD_PATH = Path("app/data/board_4p_coppit.json")
    print(f"[Startup] Trying fallback path: {BOARD_PATH}")

BOARD_COPPIT = Board.from_json_file(str(BOARD_PATH))
print(f"[Startup] Board loaded successfully: {len(BOARD_COPPIT.nodes)} nodes")

# Bot監視タスク
BOT_TASKS = {}


async def bot_watcher_task(room_id: str):
    """Botの自動プレイを監視"""
    try:
        while True:
            await asyncio.sleep(1)
            
            state = await manager.get_state(room_id)
            if not state or state.phase == GamePhase.GAME_OVER:
                break
            
            current_player = state.current_player
            if current_player and current_player.is_bot:
                await bot_think_delay()
                
                if state.phase == GamePhase.ROLL:
                    roll_dice(state)
                    state.phase = GamePhase.SELECT_PIECE
                
                # Bot自動実行
                new_state = execute_bot_turn(state, current_player.id)
                await manager.save_state(new_state)
                await manager.broadcast(room_id, new_state)
    except Exception as e:
        print(f"[Bot Watcher] Error in room {room_id}: {e}")
        import traceback
        traceback.print_exc()

@app.get("/")
async def root():
    """ロビー画面（ルーム選択）"""
    return FileResponse("static/index.html")

@app.get("/game.html")
async def game():
    """ゲーム画面"""
    return FileResponse("static/game.html")

@app.websocket("/ws/{room_id}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, player_id: str):
    print(f"[WebSocket] New connection: room={room_id}, player={player_id}")
    await manager.connect(websocket, room_id)
    print(f"[WebSocket] Connected to manager")
    
    # ルーム初期化チェック
    state = await manager.get_state(room_id)
    print(f"[WebSocket] State exists: {state is not None}")
    
    if not state:
        print(f"[WebSocket] Creating new game")
        state = init_game(room_id, BOARD_COPPIT, GameConfig())
        # Bot監視タスク起動
        if room_id not in BOT_TASKS:
            BOT_TASKS[room_id] = asyncio.create_task(bot_watcher_task(room_id))
            print(f"[WebSocket] Bot watcher task started")
    
    # プレイヤー参加
    print(f"[WebSocket] Adding player {player_id}")
    
    # 既に参加済みかチェック
    if player_id not in state.players:
        # 色名マッピング
        color_names = {
            "RED": "赤",
            "BLUE": "青", 
            "YELLOW": "黄",
            "GREEN": "緑"
        }
        
        # 色を取得
        used_colors = {p.color for p in state.players.values()}
        available_colors = [c for c in PlayerColor if c not in used_colors]
        if available_colors:
            player_color = available_colors[0]
            color_name = color_names.get(player_color.value, player_color.value)
            # プレイヤーを追加
            state = add_player(state, player_id, color_name)
            
            # プレイヤーが少ない場合、Botを自動追加してゲームを開始可能にする
            while len(state.players) < state.config.max_players and state.phase == GamePhase.WAITING:
                bot_used_colors = {p.color for p in state.players.values()}
                bot_available_colors = [c for c in PlayerColor if c not in bot_used_colors]
                if bot_available_colors:
                    bot_color = bot_available_colors[0]
                    bot_name = f"Bot {color_names.get(bot_color.value, bot_color.value)}"
                    bot_id = f"bot_{bot_color.value.lower()}"
                    state = add_player(state, bot_id, bot_name, is_bot=True)
                    print(f"[WebSocket] Auto-added bot: {bot_id} ({bot_name})")
                else:
                    break
    
    await manager.save_state(state)
    print(f"[WebSocket] State saved, players: {len(state.players)}, stacks: {len(state.stacks)}")
    await manager.broadcast(room_id, state)
    print(f"[WebSocket] Initial broadcast complete")

    try:
        while True:
            data = await websocket.receive_text()
            action_dict = json.loads(data)
            action = ClientAction(**action_dict)
            print(f"[Action] Received: {action.type} from {player_id}")
            
            state = await manager.get_state(room_id)
            if not state:
                continue
            
            # 手番プレイヤーチェック
            if state.current_player_id != player_id:
                print(f"[Action] Not player's turn: current={state.current_player_id}, requesting={player_id}")
                await websocket.send_json({"error": "Not your turn"})
                continue
            
            if action.type == "roll":
                print(f"[Action] Rolling dice for {player_id}")
                roll_dice(state)
                print(f"[Action] Dice value: {state.dice_value}")
                state.phase = GamePhase.SELECT_PIECE
                
                # 合法手判定
                legal_stacks = get_legal_stacks(state, player_id)
                print(f"[Action] Legal stacks count: {len(legal_stacks)}")
                
                state.selected_stack = None
                # クライアントに合法手を送信（空の場合もメッセージを送信）
                await websocket.send_json({
                    "type": "legal_pieces",
                    "stacks": [s.model_dump() for s in legal_stacks],
                    "dice_value": state.dice_value
                })
                
                if not legal_stacks:
                    # 移動不可の場合、1秒後にスキップ（ユーザーにサイコロ結果を見せる）
                    print(f"[Action] No legal moves, will advance turn after delay")
                    await asyncio.sleep(1.5)
                    advance_turn(state)
                
            elif action.type == "select_piece":
                print(f"[Action] Selecting piece")
                stack_data = action.payload.get("stack")
                if stack_data:
                    state.selected_stack = Stack(**stack_data)
                    print(f"[Action] Selected stack at node: {state.selected_stack.node_id}")
                    
                    # 移動可能な到着ノードを取得
                    destination_nodes = get_legal_destination_nodes(state, state.selected_stack)
                    print(f"[Action] Legal destination nodes: {destination_nodes}")
                    
                    if len(destination_nodes) > 0:
                        # 候補がある場合、クライアントに送信（1つでも表示）
                        state.phase = GamePhase.SELECT_DIRECTION
                        await websocket.send_json({
                            "type": "legal_destinations",
                            "nodes": destination_nodes
                        })
                    else:
                        print(f"[Action] No valid destinations")
            
            elif action.type == "reset":
                print(f"[Action] Resetting game for room {room_id}")
                # ゲームを初期状態にリセット
                state = init_game(room_id, BOARD_COPPIT, GameConfig())
                
                # 既存のプレイヤーを再追加
                player_ids = list(manager.active_connections.get(room_id, []))
                color_names = {"RED": "赤", "BLUE": "青", "YELLOW": "黄", "GREEN": "緑"}
                
                for pid in player_ids:
                    used_colors = {p.color for p in state.players.values()}
                    available_colors = [c for c in PlayerColor if c not in used_colors]
                    if available_colors:
                        player_color = available_colors[0]
                        color_name = color_names.get(player_color.value, player_color.value)
                        state = add_player(state, pid, color_name)
                
                # Botを自動追加
                while len(state.players) < state.config.max_players and state.phase == GamePhase.WAITING:
                    bot_used_colors = {p.color for p in state.players.values()}
                    bot_available_colors = [c for c in PlayerColor if c not in bot_used_colors]
                    if bot_available_colors:
                        bot_color = bot_available_colors[0]
                        bot_id = f"bot_{bot_color.value.lower()}"
                        bot_name = f"Bot{color_names.get(bot_color.value, bot_color.value)}"
                        state = add_player(state, bot_id, bot_name, is_bot=True)
                    else:
                        break
                
                print(f"[Action] Game reset complete. Players: {len(state.players)}")
                
            elif action.type == "select_destination":
                print(f"[Action] Selecting destination node")
                destination_node = action.payload.get("node_id")
                print(f"[Action] Destination node: {destination_node}")
                
                if state.selected_stack and destination_node:
                    # どの経路でこのノードに到達できるか探索
                    chosen_direction = None
                    chosen_path = None
                    
                    # BOXからの出撃の場合
                    if state.selected_stack.node_id.startswith("box_"):
                        player = state.current_player
                        if player:
                            from app.engine import find_deployment_node, get_all_possible_paths
                            deploy_node = find_deployment_node(state.board, player.color)
                            if deploy_node:
                                # サイコロ1の場合、出撃地点に配置
                                if state.dice_value == 1:
                                    if deploy_node == destination_node:
                                        chosen_direction = Direction.CW  # ダミー
                                        chosen_path = [deploy_node]
                                else:
                                    # サイコロ2以上の場合、出撃地点から(目-1)マス進む
                                    actual_distance = state.dice_value - 1
                                    for direction in [Direction.CW, Direction.CCW]:
                                        all_paths = get_all_possible_paths(state.board, deploy_node, actual_distance, direction)
                                        for path in all_paths:
                                            if path and path[-1] == destination_node:
                                                chosen_direction = direction
                                                chosen_path = path
                                                break
                                        if chosen_direction:
                                            break
                    else:
                        # 通常の移動の場合（交差点での分岐を考慮）
                        from app.engine import get_all_possible_paths
                        directions = get_legal_directions(state, state.selected_stack)
                        
                        for direction in directions:
                            all_paths = get_all_possible_paths(state.board, state.selected_stack.node_id, state.dice_value, direction)
                            for path in all_paths:
                                if path and path[-1] == destination_node:
                                    chosen_direction = direction
                                    chosen_path = path
                                    break
                            if chosen_direction:
                                break
                    
                    print(f"[Action] Applying move with direction: {chosen_direction}, path: {chosen_path}, target: {destination_node}")
                    new_state = apply_move(state, state.selected_stack, chosen_direction, destination_node)
                    await manager.save_state(new_state)
                    await manager.broadcast(room_id, new_state)
                    continue
            
            elif action.type == "select_direction":
                print(f"[Action] Selecting direction")
                direction_str = action.payload.get("direction")
                direction = Direction(direction_str) if direction_str else None
                print(f"[Action] Direction: {direction}")
                
                if state.selected_stack and direction:
                    print(f"[Action] Applying move with direction")
                    new_state = apply_move(state, state.selected_stack, direction)
                    await manager.save_state(new_state)
                    await manager.broadcast(room_id, new_state)
                    continue
            
            await manager.save_state(state)
            await manager.broadcast(room_id, state)
            await manager.broadcast(room_id, state)
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)

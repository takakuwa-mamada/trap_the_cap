import random
import uuid
from typing import List, Tuple, Optional
from app.models import (
    GameState, GamePhase, PlayerColor, Stack, Hat, 
    LegalMove, ActionLog, GameConfig
)

def init_game(room_id: str, board_data: dict, config: GameConfig) -> GameState:
    nodes = {n['id']: Node(**n) for n in board_data['nodes']}
    return GameState(
        room_id=room_id,
        config=config,
        nodes=nodes,
        stacks={},
        players={},
        turn_order=[]
    )

def add_player(state: GameState, player_id: str, name: str, is_bot: bool = False) -> GameState:
    if len(state.players) >= state.config.max_players:
        return state
    
    # 色割り当て
    used_colors = {p.color for p in state.players.values() if p.color}
    available_colors = [c for c in PlayerColor if c not in used_colors]
    if not available_colors: return state # Should not happen if max=4

    color = available_colors[0]
    player = Player(id=player_id, name=name, color=color, is_bot=is_bot)
    state.players[player_id] = player
    
    # ターン順追加
    state.turn_order.append(player_id)
    
    # 全員揃ったらゲーム開始準備
    if len(state.players) == state.config.max_players:
        _setup_board(state)
        state.phase = GamePhase.ROLL
    
    return state

def _setup_board(state: GameState):
    # 各プレイヤーのホームに初期コマを配置
    hat_count = 0
    for p in state.players.values():
        home_nodes = [n for n in state.nodes.values() 
                      if n.home_color == p.color.value]
        start_node = home_nodes[0].id if home_nodes else list(state.nodes.keys())[0]
        
        for _ in range(state.config.hats_per_player):
            hat_id = f"h_{hat_count}"
            stack_id = f"s_{hat_count}"
            hat = Hat(id=hat_id, color=p.color, owner=p.color)
            stack = Stack(id=stack_id, node_id=start_node, pieces=[hat])
            state.stacks[stack_id] = stack
            hat_count += 1

def roll_dice(state: GameState, player_id: str) -> GameState:
    if state.phase != GamePhase.ROLL: return state
    if state.current_player_id != player_id: return state

    # 乱数生成
    roll = random.randint(1, 6)
    state.dice_value = roll
    state.logs.append(ActionLog(timestamp=0, player_id=player_id, action_type="ROLL", details={"value": roll}))
    
    # 合法手計算
    state.legal_moves = _calculate_legal_moves(state, roll)
    
    if not state.legal_moves:
        # 手がない場合はスキップ
        _next_turn(state)
    else:
        state.phase = GamePhase.SELECT

    return state

def _calculate_legal_moves(state: GameState, steps: int) -> List[LegalMove]:
    moves = []
    player = state.players[state.current_player_id]
    
    # 自分のコントロールするスタックを探す
    my_stacks = [s for s in state.stacks.values() if s.controller == player.color]
    
    move_idx = 0
    for stack in my_stacks:
        # BFS/DFSで経路探索
        # ここでは簡易的に「後戻りなし」または「グラフ探索」を行う
        # 重い処理を防ぐため、単純なDFSでsteps分のパスを探す
        paths = _find_paths(state, stack.node_id, steps, visited=set())
        
        for path in paths:
            # pathは [start, n1, n2, ... end]
            # スタート地点は含まなくて良い
            actual_path = path[1:]
            end_node_id = actual_path[-1]
            end_node = state.nodes[end_node_id]
            
            desc = f"Move to {end_node_id}"
            
            # 捕獲判定プレビュー
            target_stack = _get_stack_at(state, end_node_id)
            if target_stack and target_stack.controller != player.color:
                if "SAFE" not in end_node.tags:
                    desc = f"Capture {target_stack.controller.value} at {end_node_id}"
            
            # ホーム判定
            if "HOME" in end_node.tags and end_node.home_color == player.color.value:
                desc = "Enter Home"

            moves.append(LegalMove(
                move_id=move_idx,
                stack_id=stack.id,
                path=actual_path,
                description=desc
            ))
            move_idx += 1
            
    return moves

def _find_paths(state: GameState, current_node_id: str, steps: int, visited: set) -> List[List[str]]:
    if steps == 0:
        return [[current_node_id]]
    
    paths = []
    current_node = state.nodes[current_node_id]
    
    for neighbor_id in current_node.neighbors:
        # 単純な往復禁止（オプション）
        # ここではグラフ上の探索を行う
        # 完全なルール実装には、スタックの移動履歴も考慮する必要があるが、
        # MVPとしては「1ターンの移動中に同じマスを通らない」制約をつける
        if neighbor_id in visited: continue
        
        # ホーム侵入制限：他人のホームには入れない
        neighbor = state.nodes[neighbor_id]
        if "HOME" in neighbor.tags:
            owner_color = state.players[state.current_player_id].color.value
            if neighbor.home_color != owner_color:
                continue

        sub_paths = _find_paths(state, neighbor_id, steps - 1, visited | {current_node_id})
        for sub in sub_paths:
            paths.append([current_node_id] + sub)
            
    return paths

def _get_stack_at(state: GameState, node_id: str) -> Optional[Stack]:
    for s in state.stacks.values():
        if s.node_id == node_id:
            return s
    return None

def apply_move(state: GameState, player_id: str, move_id: int) -> GameState:
    if state.phase != GamePhase.SELECT: return state
    
    # 選択されたmoveを取得
    selected_move = next((m for m in state.legal_moves if m.move_id == move_id), None)
    if not selected_move: return state

    stack = state.stacks[selected_move.stack_id]
    current_player_color = state.players[player_id].color

    # 移動と捕獲処理
    for step_node_id in selected_move.path:
        stack.node_id = step_node_id
        
        # 移動先にあるスタックを確認
        target_stack = _get_stack_at(state, step_node_id)
        
        # 自分自身のスタックとは合体しない（ルールによるが、MVPではスキップ）
        if target_stack and target_stack.id != stack.id:
            # 敵スタックの場合
            target_node = state.nodes[step_node_id]
            is_safe = "SAFE" in target_node.tags or "HOME" in target_node.tags
            
            if not is_safe:
                # 捕獲発生：敵スタックを自分の下に吸収する
                # コピットのルールでは「被せる」。つまり自分のスタックが上に来る。
                # target_stackのpiecesをstackのpiecesの下に入れるか、stackをtargetの上に置くか。
                # データモデル上は、target_stackのpiecesをstackに結合し、target_stackを消す。
                
                # Stack.pieces = [Bottom ... Top]
                # Attacker (stack) comes ON TOP of Defender (target_stack)
                # New pieces = Defender.pieces + Attacker.pieces
                stack.pieces = target_stack.pieces + stack.pieces
                del state.stacks[target_stack.id]
                
                state.logs.append(ActionLog(
                    timestamp=0, player_id=player_id, action_type="CAPTURE", 
                    details={"at": step_node_id}
                ))

    # ゴール判定（ホームで止まった場合）
    final_node = state.nodes[stack.node_id]
    if "HOME" in final_node.tags and final_node.home_color == current_player_color.value:
        # Bank処理：スタック内の捕虜(owner != myself)をスコアにする
        # 自分のコマは盤面に残すか、再利用するか。
        # MVP: 全てスコア化して盤面から消滅させる（Offensive Mode風）
        banked_count = len(stack.pieces)
        state.players[player_id].score += banked_count
        del state.stacks[stack.id]
        state.logs.append(ActionLog(
            timestamp=0, player_id=player_id, action_type="BANK", 
            details={"count": banked_count}
        ))
        
        # 勝利判定チェック
        active_stacks = [s for s in state.stacks.values() if s.controller != current_player_color]
        if not active_stacks and len(state.players) > 1: # 敵全滅
             state.winner = player_id
             state.phase = GamePhase.FINISHED
             return state

    # 次のターンへ
    if state.config.extra_roll_on_6 and state.dice_value == 6:
        state.phase = GamePhase.ROLL
        state.dice_value = None
        state.legal_moves = []
    else:
        _next_turn(state)

    return state

def _next_turn(state: GameState):
    state.current_turn_index = (state.current_turn_index + 1) % len(state.turn_order)
    state.phase = GamePhase.ROLL
    state.dice_value = None
    state.legal_moves = []
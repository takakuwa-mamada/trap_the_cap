"""
Coppit Game Engine - Pure Functions
Complete rewrite based on SPEC_v3_COPPIT.md
"""

import random
import uuid
from typing import List, Tuple, Optional, Set
from copy import deepcopy

from app.models import (
    GameState, GamePhase, PlayerColor, Stack, Hat, 
    Player, GameConfig, Board, BoardNode, Direction,
    ActionLog, create_initial_hats
)


# =============================================================================
# Initialization
# =============================================================================

def init_game(room_id: str, board: Board, config: GameConfig) -> GameState:
    """ゲーム初期化"""
    return GameState(
        room_id=room_id,
        config=config,
        board=board,
        players={},
        turn_order=[],
        stacks=[],
        phase=GamePhase.WAITING
    )


def add_player(state: GameState, player_id: str, name: str, is_bot: bool = False) -> GameState:
    """プレイヤー追加"""
    if len(state.players) >= state.config.max_players:
        return state
    
    # 色割り当て
    used_colors = {p.color for p in state.players.values()}
    available_colors = [c for c in PlayerColor if c not in used_colors]
    if not available_colors:
        return state

    color = available_colors[0]
    player = Player(id=player_id, name=name, color=color, is_bot=is_bot)
    state.players[player_id] = player
    state.turn_order.append(player_id)
    
    # 初回のみ全スタッククリア
    is_first_player = len(state.stacks) == 0
    
    # このプレイヤーの駒を生成してBOXに配置
    hats = create_initial_hats(player.color, state.config.hats_per_player)
    for hat in hats:
        player.add_to_box(hat)
    
    # BOXノードにスタックを作成（盤面上に表示するため）
    box_node_id = f"box_{player.color.value.lower()}"
    if state.board.get_node(box_node_id):
        box_stack = Stack(node_id=box_node_id, pieces=list(player.box_hats))
        state.stacks.append(box_stack)
    
    # 4人揃ったらゲーム開始（最初のプレイヤーをランダムに選択）
    if len(state.players) == state.config.max_players and state.phase == GamePhase.WAITING:
        # 開始プレイヤーをランダムに決定
        state.current_turn_index = random.randint(0, len(state.turn_order) - 1)
        state.phase = GamePhase.ROLL
        print(f"[init_game] Game starting with player {state.turn_order[state.current_turn_index]}")
    elif is_first_player:
        state.phase = GamePhase.ROLL
    
    return state


def setup_initial_board(state: GameState) -> None:
    """初期盤面セットアップ（全帽子をBOXに配置）"""
    state.stacks = []
    
    for player_id, player in state.players.items():
        # 各プレイヤーの帽子を生成
        hats = create_initial_hats(player.color, state.config.hats_per_player)
        
        # 全てBOXに配置（初期状態）
        for hat in hats:
            player.add_to_box(hat)
        
        # BOXノードにスタックを作成（盤面上に表示するため）
        box_node_id = f"box_{player.color.value.lower()}"
        if state.board.get_node(box_node_id):
            # BOX内の帽子をスタックとして配置
            box_stack = Stack(node_id=box_node_id, pieces=list(player.box_hats))
            state.stacks.append(box_stack)


# =============================================================================
# Dice & Turn Flow
# =============================================================================

def roll_dice(state: GameState, seed: Optional[int] = None) -> int:
    """サイコロを振る"""
    if seed is not None:
        random.seed(seed)
    value = random.randint(1, 6)
    state.dice_value = value
    state.add_log(
        player_id=state.current_player_id or "",
        action_type="roll",
        details={"value": value},
        result={}
    )
    return value


def advance_turn(state: GameState) -> None:
    """次の手番へ進む"""
    state.current_turn_index = (state.current_turn_index + 1) % len(state.turn_order)
    state.turn_count += 1
    state.dice_value = None
    state.selected_stack = None
    state.selected_direction = None
    state.phase = GamePhase.ROLL


# =============================================================================
# Legal Moves
# =============================================================================

def get_legal_stacks(state: GameState, player_id: str) -> List[Stack]:
    """移動可能なスタック一覧（同じ色の全ての駒を含む）"""
    player = state.players.get(player_id)
    if not player or state.dice_value is None:
        return []
    
    legal = []
    
    # BOXから出撃可能か判定
    can_deploy = player.box_hats and (not state.config.require_6_to_deploy or state.dice_value == 6)
    
    if can_deploy:
        # BOXのノードを特定
        box_node_id = f"box_{player.color.value.lower()}"
        # BOXのスタックを探す（複数ある可能性は低いが一応全て追加）
        for stack in state.stacks:
            if stack.node_id == box_node_id and len(stack.pieces) > 0:
                legal.append(stack)
                # BOXは通常1つだけだがbreakを削除して全て追加
    
    # 盤面上の自分のスタックで、移動可能なもの（全て）
    for stack in state.stacks:
        # BOXスタックは上で処理済み
        if stack.node_id.startswith("box_"):
            continue
        if stack.controller == player.color:
            # 移動先が存在するかチェック
            if can_move_stack(state, stack, state.dice_value):
                legal.append(stack)
                # 同じ位置に複数のスタックがある場合も全て追加
    
    return legal


def can_move_stack(state: GameState, stack: Stack, distance: int) -> bool:
    """スタックが指定距離で移動可能か"""
    node = state.board.get_node(stack.node_id)
    if not node:
        return False
    
    # 外周ノード（outer_）の場合、常に移動可能（CW/CCWのどちらかで進める）
    if stack.node_id.startswith("outer_"):
        return True
    
    # 分岐点（JUNCTION）の場合、方向選択が必要
    if node.is_junction():
        return True  # 方向選択後に判定
    
    # 中央Xノードの場合も常に移動可能
    if "cross_" in stack.node_id:
        return True
    
    # 単純パスの場合、経路が存在するかチェック
    path = get_simple_path(state.board, stack.node_id, distance)
    return len(path) > 0


def get_simple_path(board: Board, start_node_id: str, distance: int) -> List[str]:
    """単純経路取得（分岐なし）"""
    path = [start_node_id]
    current = start_node_id
    
    for _ in range(distance):
        node = board.get_node(current)
        if not node or not node.neighbors:
            return []
        
        # 分岐点の場合、ここで中断
        if node.is_junction():
            return []
        
        # 次のノード
        next_node = node.neighbors[0] if node.neighbors else None
        if not next_node:
            return []
        
        path.append(next_node)
        current = next_node
    
    return path


def get_legal_directions(state: GameState, stack: Stack) -> List[Direction]:
    """移動方向の選択肢"""
    node = state.board.get_node(stack.node_id)
    if not node:
        return []
    
    # BOXノードの場合
    if node.is_box():
        return [Direction.CW, Direction.CCW]
    
    # 外周ノード（outer_）の場合、CW/CCWの2方向
    if stack.node_id.startswith("outer_"):
        return [Direction.CW, Direction.CCW]
    
    # 中央Xの分岐点
    if "cross_" in node.id:
        return [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]
    
    # JUNCTIONタグの場合（外周→中央Xへの入口）
    if node.is_junction():
        # 外周方向 + 中央X方向
        return [Direction.CW, Direction.CCW]  # 簡易実装、後で拡張
    
    return []


def get_legal_destination_nodes(state: GameState, stack: Stack) -> List[str]:
    """移動可能な到着ノードのリスト（コピット正式ルール準拠）"""
    if state.dice_value is None:
        return []
    
    distance = state.dice_value
    start_node = stack.node_id
    
    # BOXから出撃の場合
    if start_node.startswith("box_"):
        player = state.current_player
        if not player:
            return []
        
        # 出撃地点を取得
        deploy_node = find_deployment_node(state.board, player.color)
        if not deploy_node:
            return []
        
        print(f"[get_legal_destination_nodes] Deploy node: {deploy_node}, distance: {distance}")
        
        # サイコロ1の場合、出撃地点のみ
        if distance == 1:
            print(f"[get_legal_destination_nodes] BOX deploy with dice=1: {deploy_node}")
            return [deploy_node]
        
        # サイコロ2以上の場合、出撃地点から(目-1)マス進んだ全ての経路を取得
        destinations = set()
        actual_distance = distance - 1
        for direction in [Direction.CW, Direction.CCW]:
            all_paths = get_all_possible_paths(state.board, deploy_node, actual_distance, direction)
            for path in all_paths:
                if len(path) > 0:
                    dest = path[-1]
                    destinations.add(dest)
                    print(f"[get_legal_destination_nodes] BOX deploy: {direction.value} -> {dest}, path: {path}")
        
        return list(destinations)
    
    # 盤面上の駒の移動（BOXへの帰還を含む）
    destinations = set()
    directions = get_legal_directions(state, stack)
    
    # BOXへの帰還ルートをチェック
    if stack.controller:
        box_node_id = f"box_{stack.controller.value.lower()}"
        box_distance = calculate_distance_to_box(state.board, start_node, box_node_id)
        if box_distance is not None and box_distance == distance:
            # サイコロの目とBOXまでの距離が一致する場合、BOXへの帰還が可能
            destinations.add(box_node_id)
            print(f"[get_legal_destination_nodes] Can return to {box_node_id} (distance={box_distance})")
    
    if not directions:
        # 方向選択不要な場合（一本道）
        path = get_simple_path(state.board, start_node, distance)
        if path and len(path) > 1:
            destinations.add(path[-1])
    else:
        # 各方向を試す（交差点での分岐も考慮）
        for direction in directions:
            all_paths = get_all_possible_paths(state.board, start_node, distance, direction)
            for path in all_paths:
                if len(path) > 1:
                    dest = path[-1]
                    destinations.add(dest)
                    print(f"[get_legal_destination_nodes] From {start_node}: {direction.value if direction else 'NO_DIR'} -> {dest}, path: {path}")
    
    return list(destinations)


def calculate_distance_to_box(board: Board, start_node_id: str, box_node_id: str) -> Optional[int]:
    """start_nodeからbox_nodeまでの最短距離を計算
    
    Returns:
        距離（マス数）、または到達不可能の場合はNone
    """
    # BFSで最短経路を探索
    from collections import deque
    
    queue = deque([(start_node_id, 0)])  # (node_id, distance)
    visited = {start_node_id}
    
    while queue:
        current_id, distance = queue.popleft()
        
        if current_id == box_node_id:
            return distance
        
        node = board.get_node(current_id)
        if not node:
            continue
        
        for neighbor_id in node.neighbors:
            if neighbor_id not in visited:
                visited.add(neighbor_id)
                queue.append((neighbor_id, distance + 1))
    
    return None  # 到達不可能


def calculate_path_to_box(board: Board, start_node_id: str, box_node_id: str, target_distance: int) -> Optional[List[str]]:
    """BOXへの帰還経路を計算（指定された距離でBOXに到達する経路）
    
    Returns:
        経路（ノードIDのリスト）、または到達不可能の場合はNone
    """
    from collections import deque
    
    # BFSで経路を探索
    queue = deque([(start_node_id, [start_node_id])])  # (node_id, path)
    visited = {(start_node_id, 0)}  # (node_id, distance)
    
    while queue:
        current_id, path = queue.popleft()
        current_distance = len(path) - 1
        
        # 目的地に到達
        if current_id == box_node_id and current_distance == target_distance:
            print(f"[calculate_path_to_box] Found path to {box_node_id}: {path}")
            return path
        
        # まだ距離が足りない場合、探索を続ける
        if current_distance < target_distance:
            node = board.get_node(current_id)
            if not node:
                continue
            
            for neighbor_id in node.neighbors:
                state_key = (neighbor_id, current_distance + 1)
                if state_key not in visited:
                    visited.add(state_key)
                    new_path = path + [neighbor_id]
                    queue.append((neighbor_id, new_path))
    
    print(f"[calculate_path_to_box] No path found from {start_node_id} to {box_node_id} with distance {target_distance}")
    return None


# =============================================================================
# Movement
# =============================================================================

def apply_move(state: GameState, stack: Stack, direction: Optional[Direction] = None, target_node_id: Optional[str] = None) -> GameState:
    """移動を適用（純粋関数）
    
    Args:
        state: ゲーム状態
        stack: 移動するスタック
        direction: 移動方向（オプション）
        target_node_id: 目的地ノードID（指定された場合、このノードに到達する経路を使用）
    """
    new_state = deepcopy(state)
    
    if new_state.dice_value is None:
        return new_state
    
    distance = new_state.dice_value
    
    # BOXから出撃
    if stack.node_id.startswith("box_"):
        deploy_from_box(new_state, stack, direction or Direction.CW)
        # 出撃後は必ず手番を回す（6でも再ロールしない）
        advance_turn(new_state)
        return new_state
    
    # 通常移動：target_node_idが指定されている場合、そこに到達する経路を探す
    path = None
    
    # BOXへの帰還を試みる場合
    if target_node_id and target_node_id.startswith("box_"):
        path = calculate_path_to_box(new_state.board, stack.node_id, target_node_id, distance)
        print(f"[apply_move] BOX return path: {path}")
    elif target_node_id and direction:
        # 指定された方向で目的地に到達する経路を探す
        all_paths = get_all_possible_paths(new_state.board, stack.node_id, distance, direction)
        for p in all_paths:
            if p and p[-1] == target_node_id:
                path = p
                break
    
    # パスが見つからない場合は、通常の経路計算
    if not path:
        path = calculate_path(new_state.board, stack.node_id, distance, direction)
    
    if not path or len(path) < 2:
        print(f"[apply_move] No valid path found")
        return new_state
    
    # スタック移動（移動後のスタック参照を取得）
    moved_stack = move_stack_along_path(new_state, stack, path)
    
    if not moved_stack:
        print(f"[apply_move] WARNING: Could not find moved stack after movement")
        return new_state
    
    # 捕獲判定（移動後のスタックを渡す）
    resolve_captures(new_state, moved_stack)
    
    # BOX帰還判定（移動後のスタックを渡す）
    resolve_box_return(new_state, moved_stack)
    
    # 終了判定
    check_game_over(new_state)
    
    # 次の手番へ（6でも必ず手番を回す）
    advance_turn(new_state)
    
    return new_state


def get_all_possible_paths(board: Board, start: str, distance: int, direction: Optional[Direction] = None) -> List[List[str]]:
    """交差点での分岐を考慮した全ての可能な経路を取得"""
    if distance == 0:
        return [[start]]
    
    all_paths = []
    
    def explore_paths(current: str, remaining: int, path: List[str]):
        """再帰的に全ての経路を探索"""
        if remaining == 0:
            all_paths.append(path.copy())
            return
        
        node = board.get_node(current)
        if not node:
            return
        
        # 交差点（JUNCTION）の処理
        if node.is_junction():
            # オプション1: 外周を維持（outer_X → outer_Y）
            # オプション2: 十字路に入る（outer_X → cross_X_entry）
            for neighbor_id in node.neighbors:
                neighbor = board.get_node(neighbor_id)
                if not neighbor:
                    continue
                
                # 方向チェック
                if neighbor_id.startswith("outer_") and direction:
                    # 外周を進む場合、方向を確認
                    current_num = int(current.split("_")[1])
                    neighbor_num = int(neighbor_id.split("_")[1])
                    
                    if direction == Direction.CW:
                        expected = (current_num + 1) % 48
                        if neighbor_num == expected:
                            path.append(neighbor_id)
                            explore_paths(neighbor_id, remaining - 1, path)
                            path.pop()
                    else:  # CCW
                        expected = (current_num - 1) % 48
                        if neighbor_num == expected:
                            path.append(neighbor_id)
                            explore_paths(neighbor_id, remaining - 1, path)
                            path.pop()
                
                elif neighbor_id.startswith("cross_"):
                    # 十字路に入る
                    path.append(neighbor_id)
                    explore_paths(neighbor_id, remaining - 1, path)
                    path.pop()
        
        # 外周での通常移動（JUNCTIONでない場合）
        elif current.startswith("outer_") and direction:
            current_num = int(current.split("_")[1])
            
            if direction == Direction.CW:
                next_num = (current_num + 1) % 48
            else:  # CCW
                next_num = (current_num - 1) % 48
            
            next_id = f"outer_{next_num}"
            if board.get_node(next_id):
                path.append(next_id)
                explore_paths(next_id, remaining - 1, path)
                path.pop()
        
        # 十字路での移動
        elif current.startswith("cross_"):
            for neighbor_id in node.neighbors:
                if neighbor_id in path:  # 訪問済みはスキップ
                    continue
                
                neighbor = board.get_node(neighbor_id)
                if neighbor:
                    path.append(neighbor_id)
                    explore_paths(neighbor_id, remaining - 1, path)
                    path.pop()
    
    explore_paths(start, distance, [start])
    return all_paths


def calculate_path(board: Board, start: str, distance: int, direction: Optional[Direction]) -> List[str]:
    """経路計算（単一経路）"""
    if distance == 0:
        return [start]
    
    if direction is None:
        return get_simple_path(board, start, distance)
    
    # 外周リングでの移動（交差点がない場合）
    if start.startswith("outer_"):
        try:
            start_num = int(start.split("_")[1])
            
            # 経路を生成しながら交差点をチェック
            path = [start]
            current_num = start_num
            current_id = start
            
            for _ in range(distance):
                if direction == Direction.CW:
                    current_num = (current_num + 1) % 48
                else:
                    current_num = (current_num - 1) % 48
                
                current_id = f"outer_{current_num}"
                path.append(current_id)
            
            return path
        except (ValueError, IndexError):
            pass
    
    # その他の場合（中央Xなど）
    path = [start]
    current = start
    
    for step in range(distance):
        node = board.get_node(current)
        if not node:
            break
        
        # 隣接ノードから方向に合うものを選択
        next_node = select_next_node(board, current, direction, path)
        if not next_node:
            break
        
        path.append(next_node)
        current = next_node
    
    return path


def select_next_node(board: Board, current: str, direction: Direction, visited: List[str]) -> Optional[str]:
    """方向に基づいて次ノード選択"""
    node = board.get_node(current)
    if not node:
        return None
    
    # 簡易実装: 隣接ノードから未訪問を選択
    for neighbor in node.neighbors:
        if neighbor not in visited:
            return neighbor
    
    return None


def deploy_from_box(state: GameState, stack: Stack, direction: Direction) -> None:
    """BOXから出撃（出撃地点からサイコロの目の分だけ進む）"""
    player = state.current_player
    if not player or not player.box_hats or state.dice_value is None:
        return
    
    # BOXから1つ取り出し
    hat = player.box_hats.pop(0)
    
    # BOXスタックを更新
    box_node_id = f"box_{player.color.value.lower()}"
    for i, s in enumerate(state.stacks):
        if s.node_id == box_node_id:
            # BOX内の駒を更新
            state.stacks[i] = Stack(node_id=box_node_id, pieces=list(player.box_hats))
            break
    
    # 出撃地点（各色のスタート地点）
    entry_node_id = find_deployment_node(state.board, player.color)
    if not entry_node_id:
        return
    
    # サイコロの目に応じて配置位置を決定
    # サイコロ1 → 出撃地点に配置（1マス動く）
    # サイコロ2以上 → 出撃地点から(目-1)マス進む
    if state.dice_value == 1:
        # サイコロ1の場合、出撃地点に直接配置
        final_node_id = entry_node_id
        path = [entry_node_id]
        distance = 0
    else:
        # サイコロ2以上の場合、出撃地点から(目-1)マス進む
        distance = state.dice_value - 1
        path = calculate_path(state.board, entry_node_id, distance, direction)
        final_node_id = path[-1] if path else entry_node_id
    
    print(f"[deploy_from_box] Entry: {entry_node_id}, Distance: {distance}, Direction: {direction.value}, Path: {path}, Final: {final_node_id}")
    
    # 新規スタック作成
    new_stack = Stack(node_id=final_node_id, pieces=[hat])
    state.stacks.append(new_stack)
    print(f"[deploy_from_box] Created new stack at {final_node_id} with hat {hat.id}")
    
    state.add_log(
        player_id=player.id,
        action_type="deploy",
        details={"hat_id": hat.id, "node_id": entry_node_id},
        result={}
    )


def find_deployment_node(board: Board, color: PlayerColor) -> Optional[str]:
    """出撃ノード取得（BOXの隣接ノード）"""
    box_node_id = f"box_{color.value.lower()}"
    box_node = board.get_node(box_node_id)
    
    if box_node and box_node.neighbors:
        # BOXの最初の隣接ノードが出撃地点
        deploy_node_id = box_node.neighbors[0]
        print(f"[find_deployment_node] Found deployment node for {color.value}: {deploy_node_id} (from {box_node_id})")
        return deploy_node_id
    
    print(f"[find_deployment_node] No deployment node found for {color.value}")
    return None


def move_stack_along_path(state: GameState, stack: Stack, path: List[str]) -> Stack:
    """スタックを経路に沿って移動
    
    Returns:
        移動後のスタック（state.stacks内の参照）
    """
    destination = path[-1]
    source_node = stack.node_id
    
    print(f"[move_stack_along_path] Moving stack from {source_node} to {destination}")
    print(f"[move_stack_along_path] Stack pieces: {[f'{p.color.value}({p.id})' for p in stack.pieces]}")
    
    # 移動元のスタックを探して位置を更新
    moved_stack = None
    for i, s in enumerate(state.stacks):
        if s.node_id == source_node and s.controller == stack.controller:
            # pieces が一致するスタックを探す（より確実な識別）
            if len(s.pieces) == len(stack.pieces) and all(p1.id == p2.id for p1, p2 in zip(s.pieces, stack.pieces)):
                state.stacks[i].node_id = destination
                moved_stack = state.stacks[i]
                print(f"[move_stack_along_path] Found and moved stack at index {i}")
                break
    
    if not moved_stack:
        print(f"[move_stack_along_path] WARNING: Stack not found in state.stacks")
    
    return moved_stack


# =============================================================================
# Capture & Safety
# =============================================================================

def is_safe(state: GameState, stack: Stack, node_id: str) -> bool:
    """スタックが安全地帯にいるか"""
    node = state.board.get_node(node_id)
    if not node:
        return False
    
    # 色マスSAFE（同色のみ）
    if state.config.safe_by_color and node.is_safe_color():
        return node.color == stack.controller
    
    # BOX内は常に安全
    if node.is_box():
        return True
    
    return False


def resolve_captures(state: GameState, moving_stack: Stack) -> None:
    """捕獲処理（スタックの結合ロジック）
    
    仕様: 移動先に駒がある場合、先にいたスタックの上に後から来たスタックを結合
    結合順序: [...先にいた駒, ...後から来た駒]
    結果: 後から来た駒が一番上に来る（支配権を持つ）
    セーフスクエア: その色のスタックは捕獲から保護される
    """
    dest_node_id = moving_stack.node_id
    
    print(f"[resolve_captures] Checking captures at {dest_node_id}")
    print(f"[resolve_captures] Moving stack pieces: {[f'{p.color.value}({p.id})' for p in moving_stack.pieces]}")
    
    # 同じノードの他の全スタックを取得（移動してきたスタック以外）
    stacks_at_dest = [s for s in state.stacks if s.node_id == dest_node_id and s is not moving_stack]
    
    if not stacks_at_dest:
        print(f"[resolve_captures] No other stacks at {dest_node_id}")
        return  # 移動先に他のスタックがない場合は何もしない
    
    print(f"[resolve_captures] Found {len(stacks_at_dest)} other stacks at {dest_node_id}")
    
    # セーフスクエアのチェック
    node = state.board.get_node(dest_node_id)
    if node and node.is_safe_color():
        # セーフスクエアでは、その色のスタックは保護される
        print(f"[resolve_captures] Node {dest_node_id} is SAFE_COLOR ({node.color})")
        
        # 移動してきたスタックがセーフ色と一致する場合、捕獲なし
        if moving_stack.controller == node.color:
            print(f"[resolve_captures] Moving stack is protected by SAFE_COLOR")
            return
        
        # 既存のスタックがセーフ色と一致する場合、そのスタックは捕獲されない
        protected_stacks = [s for s in stacks_at_dest if s.controller == node.color]
        if protected_stacks:
            print(f"[resolve_captures] {len(protected_stacks)} stack(s) protected by SAFE_COLOR")
            # 保護されたスタックは捕獲リストから除外
            stacks_at_dest = [s for s in stacks_at_dest if s.controller != node.color]
            if not stacks_at_dest:
                print(f"[resolve_captures] All stacks are protected, no captures")
                return
    
    # 移動してきたスタックのインデックスを探す
    moving_stack_idx = None
    for i, s in enumerate(state.stacks):
        if s is moving_stack:
            moving_stack_idx = i
            print(f"[resolve_captures] Found moving_stack at index {i}")
            break
    
    if moving_stack_idx is None:
        print(f"[resolve_captures] ERROR: moving_stack not found in state.stacks")
        print(f"[resolve_captures] State has {len(state.stacks)} stacks")
        for i, s in enumerate(state.stacks):
            print(f"  Stack {i}: {s.node_id}, controller={s.controller}, pieces={[p.id for p in s.pieces]}")
        return
    
    # 全てのスタックを結合（移動してきたスタックが一番上に来る）
    for other_stack in stacks_at_dest:
        print(f"[resolve_captures] ===== MERGING STACKS =====")
        print(f"[resolve_captures] Existing stack (will be bottom): {[f'{p.color.value}({p.id})' for p in other_stack.pieces]}")
        print(f"[resolve_captures] Moving stack (will be top): {[f'{p.color.value}({p.id})' for p in state.stacks[moving_stack_idx].pieces]}")
        
        # 重要: 後から来た駒が上に来るように結合
        # Stack のデータモデル: pieces[0]=底、pieces[-1]=天辺
        # 結果: [...先にいた駒, ...後から来た駒]
        # つまり: other_stack（既存）を底、moving_stack（新規）を天辺
        combined_pieces = other_stack.pieces + state.stacks[moving_stack_idx].pieces
        state.stacks[moving_stack_idx].pieces = combined_pieces
        
        print(f"[resolve_captures] Combined stack (bottom→top): {[f'{p.color.value}({p.id})' for p in state.stacks[moving_stack_idx].pieces]}")
        print(f"[resolve_captures] Controller (top piece): {state.stacks[moving_stack_idx].controller}")
        print(f"[resolve_captures] ===========================")
        
        action_type = "capture" if other_stack.controller != moving_stack.controller else "merge"
        
        # マージされたスタックを削除
        state.stacks.remove(other_stack)
        
        state.add_log(
            player_id=state.current_player_id or "",
            action_type="capture" if other_stack.controller != moving_stack.controller else "merge",
            details={"other_stack": {"node": dest_node_id, "controller": other_stack.controller.value if other_stack.controller else None}},
            result={}
        )


def resolve_box_return(state: GameState, stack: Stack) -> None:
    """BOX帰還処理（敵の駒を持ち帰った場合はポイント加算）"""
    node = state.board.get_node(stack.node_id)
    if not node or not node.is_box():
        print(f"[resolve_box_return] Node {stack.node_id} is not a BOX")
        return
    
    player = state.current_player
    if not player:
        print(f"[resolve_box_return] No current player")
        return
    
    if node.color != player.color:
        print(f"[resolve_box_return] BOX color {node.color} does not match player color {player.color}")
        return
    
    print(f"[resolve_box_return] Player {player.color} returning to box with stack: {[f'{p.color.value}({p.id})' for p in stack.pieces]}")
    print(f"[resolve_box_return] Player box_hats before: {len(player.box_hats)}")
    
    # 自色BOXに帰還
    points_earned = 0
    for hat in stack.pieces:
        player.add_to_box(hat)
        
        # 敵の駒（捕獲した駒）は確保してポイント加算
        if hat.color != player.color:
            player.bank_captive(hat)
            points_earned += 1
            print(f"[resolve_box_return] Banked enemy piece: {hat.color.value}({hat.id}) -> +1 point")
    
    print(f"[resolve_box_return] Player box_hats after: {len(player.box_hats)}")
    
    if points_earned > 0:
        print(f"[resolve_box_return] {player.color} earned {points_earned} point(s)! Total banked: {len(player.banked_hats)}")
    
    # スタック削除
    state.stacks = [s for s in state.stacks if s != stack]
    print(f"[resolve_box_return] Stack removed, remaining stacks: {len(state.stacks)}")
    
    state.add_log(
        player_id=player.id,
        action_type="box_return",
        details={
            "pieces_returned": len(stack.pieces),
            "points_earned": points_earned,
            "total_points": player.points
        },
        result={}
    )


# =============================================================================
# Game Over
# =============================================================================

def check_game_over(state: GameState) -> None:
    """終了判定"""
    # 盤上1色のみ
    colors_on_board = state.get_colors_on_board()
    if len(colors_on_board) <= 1:
        determine_winner(state)
        return
    
    # ターン上限
    if state.config.max_turns and state.turn_count >= state.config.max_turns:
        determine_winner(state)
        return


def determine_winner(state: GameState) -> None:
    """勝者決定"""
    scores = {p.id: p.score for p in state.players.values()}
    max_score = max(scores.values())
    winners = [pid for pid, score in scores.items() if score == max_score]
    
    state.winner = winners[0] if len(winners) == 1 else winners
    state.phase = GamePhase.GAME_OVER
    
    state.add_log(
        player_id="system",
        action_type="game_over",
        details={"winner": state.winner, "scores": scores},
        result={}
    )


# =============================================================================
# Utility
# =============================================================================

def get_game_summary(state: GameState) -> dict:
    """ゲーム状態サマリ"""
    return {
        "room_id": state.room_id,
        "phase": state.phase.value,
        "turn": state.turn_count,
        "current_player": state.current_player_id,
        "dice_value": state.dice_value,
        "players": {
            p.id: {
                "name": p.name,
                "color": p.color.value,
                "score": p.score,
                "box_count": len(p.box_hats),
                "banked_count": len(p.banked_hats)
            }
            for p in state.players.values()
        },
        "stacks_count": len(state.stacks)
    }

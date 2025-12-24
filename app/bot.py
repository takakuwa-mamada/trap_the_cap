"""
Coppit Bot Player
ヒューリスティック戦略によるAI実装
"""

import random
from typing import List, Optional
from app.models import GameState, Stack, Direction, PlayerColor
from app.engine import (
    get_legal_stacks,
    get_legal_directions,
    apply_move
)


class BotPlayer:
    """ボットプレイヤー"""
    
    def __init__(self, player_id: str, difficulty: str = "heuristic"):
        self.player_id = player_id
        self.difficulty = difficulty
    
    def choose_piece(self, state: GameState) -> Optional[Stack]:
        """移動する駒を選択"""
        legal_stacks = get_legal_stacks(state, self.player_id)
        if not legal_stacks:
            return None
        
        # ヒューリスティック戦略
        return self._evaluate_stacks(state, legal_stacks)
    
    def choose_direction(self, state: GameState, stack: Stack) -> Optional[Direction]:
        """移動方向を選択"""
        legal_directions = get_legal_directions(state, stack)
        if not legal_directions:
            return None
        
        # ヒューリスティック戦略
        return self._evaluate_directions(state, stack, legal_directions)
    
    def _evaluate_stacks(self, state: GameState, stacks: List[Stack]) -> Stack:
        """スタック評価（優先度順）"""
        player = state.players.get(self.player_id)
        if not player:
            return stacks[0]
        
        # 優先度1: BOXから出撃（6の場合）
        box_stacks = [s for s in stacks if s.node_id.startswith("box_")]
        if box_stacks:
            return box_stacks[0]
        
        # 優先度2: 捕虜を連れているスタック（BOXへ帰還を目指す）
        carrying_captives = [s for s in stacks if s.has_captives()]
        if carrying_captives:
            # BOXに近いものを選ぶ（簡易実装: ランダム）
            return self._select_closest_to_box(state, carrying_captives, player.color)
        
        # 優先度3: 敵を捕獲できる位置にいるスタック
        # （実装簡略化: ここでは単純にランダム）
        
        # デフォルト: ランダム選択
        return random.choice(stacks)
    
    def _evaluate_directions(self, state: GameState, stack: Stack, directions: List[Direction]) -> Direction:
        """方向評価"""
        player = state.players.get(self.player_id)
        if not player:
            return directions[0]
        
        # BOX出撃の場合、時計回り優先
        if stack.node_id.startswith("box_"):
            if Direction.CW in directions:
                return Direction.CW
        
        # 捕虜を連れている場合、BOX方向を目指す（簡易実装）
        if stack.has_captives():
            # TODO: 経路計算でBOXに近い方向を選ぶ
            pass
        
        # デフォルト: ランダム
        return random.choice(directions)
    
    def _select_closest_to_box(self, state: GameState, stacks: List[Stack], color: PlayerColor) -> Stack:
        """BOXに最も近いスタックを選択（簡易実装）"""
        # TODO: 実際の距離計算
        return stacks[0]


def execute_bot_turn(state: GameState, player_id: str) -> GameState:
    """ボットのターンを実行"""
    bot = BotPlayer(player_id)
    
    # 1. サイコロを振る（既にroll_diceが呼ばれている前提）
    if state.dice_value is None:
        return state
    
    # 2. 駒を選択
    stack = bot.choose_piece(state)
    if not stack:
        # 移動可能な駒がない場合、スキップ
        from app.engine import advance_turn
        advance_turn(state)
        return state
    
    # 3. 方向選択（必要な場合）
    direction = None
    if get_legal_directions(state, stack):
        direction = bot.choose_direction(state, stack)
    
    # 4. 移動実行
    new_state = apply_move(state, stack, direction)
    
    return new_state


async def bot_think_delay():
    """ボットの思考時間をシミュレート"""
    import asyncio
    await asyncio.sleep(random.uniform(0.5, 1.5))

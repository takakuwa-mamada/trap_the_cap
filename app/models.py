"""
Coppit Game Models - Pydantic v2
Complete rewrite based on SPEC_v3_COPPIT.md
"""

from enum import Enum
from typing import List, Dict, Optional, Any, Union
from pydantic import BaseModel, Field
import time
import json


# =============================================================================
# Enums
# =============================================================================

class PlayerColor(str, Enum):
    RED = "RED"
    GREEN = "GREEN"
    BLUE = "BLUE"
    YELLOW = "YELLOW"


class GamePhase(str, Enum):
    WAITING = "WAITING"                # プレイヤー待ち
    ROLL = "ROLL"                      # サイコロを振る
    SELECT_PIECE = "SELECT_PIECE"      # 駒を選ぶ
    SELECT_DIRECTION = "SELECT_DIRECTION"  # 方向を選ぶ
    MOVE = "MOVE"                      # 移動中
    RESOLVE = "RESOLVE"                # 捕獲・確保処理
    GAME_OVER = "GAME_OVER"            # ゲーム終了


class Direction(str, Enum):
    CW = "CW"               # 時計回り (Clockwise)
    CCW = "CCW"             # 反時計回り (Counter-Clockwise)
    NORTH = "NORTH"         # 中央X: 北
    EAST = "EAST"           # 中央X: 東
    SOUTH = "SOUTH"         # 中央X: 南
    WEST = "WEST"           # 中央X: 西


# =============================================================================
# Board Models
# =============================================================================

class BoardNode(BaseModel):
    """盤面のノード（マス）"""
    id: str
    x: float
    y: float
    neighbors: List[str]
    tags: List[str] = []  # ["NORMAL", "BOX", "SAFE_COLOR", "CROSS", "JUNCTION", "CENTER"]
    color: Optional[PlayerColor] = None  # SAFE_COLORの場合

    def has_tag(self, tag: str) -> bool:
        return tag in self.tags

    def is_box(self) -> bool:
        return self.has_tag("BOX")

    def is_safe_color(self) -> bool:
        return self.has_tag("SAFE_COLOR")

    def is_junction(self) -> bool:
        return self.has_tag("JUNCTION")


class Board(BaseModel):
    """盤面全体"""
    meta: Dict[str, Any] = {}
    nodes: Dict[str, BoardNode]  # node_id -> BoardNode

    @classmethod
    def from_json_file(cls, filepath: str) -> "Board":
        """JSONファイルから盤面を読み込む"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        nodes = {n['id']: BoardNode(**n) for n in data['nodes']}
        return cls(meta=data.get('meta', {}), nodes=nodes)

    def get_node(self, node_id: str) -> Optional[BoardNode]:
        return self.nodes.get(node_id)

    def get_neighbors(self, node_id: str) -> List[str]:
        node = self.get_node(node_id)
        return node.neighbors if node else []


# =============================================================================
# Piece Models
# =============================================================================

class Hat(BaseModel):
    """帽子（駒）"""
    id: str  # "red_1", "blue_2", etc.
    color: PlayerColor
    owner: PlayerColor  # 初期所有者（統計用）

    def is_owned_by(self, color: PlayerColor) -> bool:
        return self.color == color or self.owner == color


class Stack(BaseModel):
    """スタック（重なった帽子の束）"""
    node_id: str  # 現在位置のノードID
    pieces: List[Hat] = []  # index 0が底、-1が最上位

    @property
    def controller(self) -> Optional[PlayerColor]:
        """操作主体（最上位の帽子の色）"""
        return self.pieces[-1].color if self.pieces else None

    @property
    def size(self) -> int:
        return len(self.pieces)

    def has_captives(self) -> bool:
        """捕虜を連れているか"""
        return len(self.pieces) > 1

    def captives(self) -> List[Hat]:
        """捕虜の一覧（最上位以外）"""
        return self.pieces[:-1]

    def has_captive_of_color(self, color: PlayerColor) -> bool:
        """指定色の捕虜を含むか"""
        return any(h.color == color for h in self.captives())

    def add_on_top(self, hat: Hat) -> None:
        """帽子を最上位に追加"""
        self.pieces.append(hat)

    def merge_underneath(self, other_stack: "Stack") -> None:
        """別のスタックを下に統合"""
        self.pieces = other_stack.pieces + self.pieces


# =============================================================================
# Player Models
# =============================================================================

class Player(BaseModel):
    """プレイヤー"""
    id: str  # "p_1", "p_2", etc.
    name: str
    color: PlayerColor
    is_bot: bool = False
    connected: bool = True
    box_hats: List[Hat] = []  # BOX内の帽子
    banked_hats: List[Hat] = []  # 確保した捕虜

    @property
    def score(self) -> int:
        """BOX内の自色帽子数（勝利判定用）"""
        return len([h for h in self.box_hats if h.color == self.color])
    
    @property
    def points(self) -> int:
        """ポイント（確保した敵の駒の数）"""
        return len([h for h in self.banked_hats if h.color != self.color])

    def add_to_box(self, hat: Hat) -> None:
        """BOXに帽子を追加"""
        self.box_hats.append(hat)

    def bank_captive(self, hat: Hat) -> None:
        """捕虜を確保"""
        self.banked_hats.append(hat)


# =============================================================================
# Config
# =============================================================================

class GameConfig(BaseModel):
    """ゲーム設定"""
    max_players: int = 4
    hats_per_player: int = 6  # 公式ルール: 2-4人用では各6個
    require_6_to_deploy: bool = False
    extra_roll_on_6: bool = True
    capture_on_pass: bool = False
    safe_by_color: bool = True
    safe_by_gray: bool = True
    allow_box_invasion: bool = False
    auto_bank_on_return: bool = True
    allow_respawn: bool = False
    win_mode: str = "box_count"
    max_turns: Optional[int] = None
    bot_fill_timeout_sec: int = 30
    allow_backward: bool = True
    direction_lock: bool = True
    box_exit_bidirectional: bool = True
    max_stack_height: Optional[int] = None
    turn_order_method: str = "fixed"
    bot_difficulty: str = "heuristic"


# =============================================================================
# Game State
# =============================================================================

class ActionLog(BaseModel):
    """アクションログ（リプレイ用）"""
    timestamp: float
    turn: int
    player_id: str
    action_type: str
    details: Dict[str, Any]
    result: Dict[str, Any] = {}


class GameState(BaseModel):
    """ゲーム状態（全体）"""
    room_id: str
    config: GameConfig
    board: Board
    players: Dict[str, Player]  # player_id -> Player
    turn_order: List[str] = []  # player_ids
    current_turn_index: int = 0
    phase: GamePhase = GamePhase.WAITING
    dice_value: Optional[int] = None
    selected_stack: Optional[Stack] = None
    selected_direction: Optional[Direction] = None
    stacks: List[Stack] = []  # 盤面上の全スタック
    logs: List[ActionLog] = []
    winner: Optional[Union[str, List[str]]] = None
    created_at: float = Field(default_factory=time.time)
    random_seed: Optional[int] = None
    turn_count: int = 0

    @property
    def current_player_id(self) -> Optional[str]:
        """現在の手番プレイヤーID"""
        if not self.turn_order:
            return None
        return self.turn_order[self.current_turn_index]

    @property
    def current_player(self) -> Optional[Player]:
        """現在の手番プレイヤー"""
        pid = self.current_player_id
        return self.players.get(pid) if pid else None

    def get_stacks_at_node(self, node_id: str) -> List[Stack]:
        """指定ノードのスタック一覧"""
        return [s for s in self.stacks if s.node_id == node_id]

    def get_player_stacks(self, player_id: str) -> List[Stack]:
        """指定プレイヤーが操作できるスタック一覧"""
        player = self.players.get(player_id)
        if not player:
            return []
        return [s for s in self.stacks if s.controller == player.color]

    def get_all_hats_on_board(self) -> List[Hat]:
        """盤面上の全帽子"""
        hats = []
        for stack in self.stacks:
            hats.extend(stack.pieces)
        return hats

    def get_colors_on_board(self) -> set[PlayerColor]:
        """盤面上に残っている色の集合"""
        hats = self.get_all_hats_on_board()
        return set(h.color for h in hats)

    def add_log(self, player_id: str, action_type: str, details: Dict[str, Any], result: Dict[str, Any] = None) -> None:
        """ログ追加"""
        log = ActionLog(
            timestamp=time.time(),
            turn=self.turn_count,
            player_id=player_id,
            action_type=action_type,
            details=details,
            result=result or {}
        )
        self.logs.append(log)


# =============================================================================
# Messages (WebSocket)
# =============================================================================

class ClientAction(BaseModel):
    """クライアント→サーバのアクション"""
    type: str  # "roll", "select_piece", "select_direction", "chat", etc.
    payload: Dict[str, Any] = {}


class ServerEvent(BaseModel):
    """サーバ→クライアントのイベント"""
    type: str  # "state_update", "legal_pieces", "error", etc.
    payload: Dict[str, Any] = {}

    @classmethod
    def state_update(cls, game_state: GameState) -> "ServerEvent":
        return cls(type="state_update", payload={"game_state": game_state.model_dump()})

    @classmethod
    def legal_pieces(cls, stacks: List[Stack]) -> "ServerEvent":
        return cls(type="legal_pieces", payload={"stacks": [s.model_dump() for s in stacks]})

    @classmethod
    def legal_directions(cls, directions: List[Direction]) -> "ServerEvent":
        return cls(type="legal_directions", payload={"directions": [d.value for d in directions]})

    @classmethod
    def turn_start(cls, player_id: str, phase: GamePhase) -> "ServerEvent":
        return cls(type="turn_start", payload={"player_id": player_id, "phase": phase.value})

    @classmethod
    def dice_rolled(cls, value: int, player_id: str) -> "ServerEvent":
        return cls(type="dice_rolled", payload={"value": value, "player_id": player_id})

    @classmethod
    def game_over(cls, winner: Union[str, List[str]], scores: Dict[str, int]) -> "ServerEvent":
        return cls(type="game_over", payload={"winner": winner, "final_scores": scores})

    @classmethod
    def error(cls, message: str, details: Dict[str, Any] = None) -> "ServerEvent":
        return cls(type="error", payload={"message": message, "details": details or {}})

    @classmethod
    def chat(cls, player_id: str, name: str, message: str) -> "ServerEvent":
        return cls(type="chat", payload={"player_id": player_id, "name": name, "message": message})


# =============================================================================
# Helper Functions
# =============================================================================

def create_hat(color: PlayerColor, index: int) -> Hat:
    """帽子を生成"""
    return Hat(
        id=f"{color.value.lower()}_{index}",
        color=color,
        owner=color
    )


def create_initial_hats(color: PlayerColor, count: int) -> List[Hat]:
    """初期帽子を生成"""
    return [create_hat(color, i) for i in range(1, count + 1)]

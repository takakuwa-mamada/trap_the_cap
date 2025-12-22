from enum import Enum
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
import time

class PlayerColor(str, Enum):
    RED = "RED"
    BLUE = "BLUE"
    YELLOW = "YELLOW"
    GREEN = "GREEN"

class GamePhase(str, Enum):
    WAITING = "WAITING"
    ROLL = "ROLL"
    SELECT = "SELECT"
    RESOLVE = "RESOLVE"
    FINISHED = "FINISHED"

class Node(BaseModel):
    id: str
    x: float
    y: float
    neighbors: List[str]
    tags: List[str] = []
    home_color: Optional[str] = None

class Hat(BaseModel):
    id: str
    color: PlayerColor
    owner: PlayerColor # 初期所有者

class Stack(BaseModel):
    id: str
    node_id: str
    pieces: List[Hat] # index 0 is bottom, -1 is top (controller)

    @property
    def controller(self) -> PlayerColor:
        return self.pieces[-1].color if self.pieces else self.pieces[0].owner

class Player(BaseModel):
    id: str
    name: str
    color: Optional[PlayerColor] = None
    is_bot: bool = False
    score: int = 0 # Banked hats
    connected: bool = True

class GameConfig(BaseModel):
    max_players: int = 4
    hats_per_player: int = 4
    extra_roll_on_6: bool = True
    capture_on_pass: bool = False
    steal_back_enabled: bool = True
    bot_fill_delay: int = 15 # 秒

class LegalMove(BaseModel):
    move_id: int
    stack_id: str
    path: List[str] # node ids
    description: str # UI表示用 (例: "Capture Blue", "Enter Home")

class ActionLog(BaseModel):
    timestamp: float
    player_id: str
    action_type: str
    details: Dict[str, Any]

class GameState(BaseModel):
    room_id: str
    config: GameConfig
    nodes: Dict[str, Node]
    stacks: Dict[str, Stack]
    players: Dict[str, Player]
    turn_order: List[str] # player_ids
    current_turn_index: int = 0
    phase: GamePhase = GamePhase.WAITING
    dice_value: Optional[int] = None
    legal_moves: List[LegalMove] = []
    logs: List[ActionLog] = []
    winner: Optional[str] = None
    created_at: float = Field(default_factory=time.time)

    @property
    def current_player_id(self) -> Optional[str]:
        if not self.turn_order: return None
        return self.turn_order[self.current_turn_index]

# Actions
class ClientAction(BaseModel):
    type: str
    payload: Dict[str, Any] = {}
# Coppit 実装計画 - Python/FastAPI/WebSocket

**作成日**: 2025-12-23  
**対象**: trap_the_cap プロジェクト  
**技術スタック**: Python 3.11+, FastAPI, Uvicorn, Redis, Pydantic v2

---

## 1. アーキテクチャ概要

### 1.1 レイヤー構造

```
┌─────────────────────────────────────┐
│  Frontend (Static HTML/JS/CSS)     │
│  - Canvas board rendering           │
│  - WebSocket client                 │
│  - User input handling              │
└────────────┬────────────────────────┘
             │ WebSocket
┌────────────▼────────────────────────┐
│  FastAPI Application (main.py)      │
│  - WebSocket endpoint               │
│  - HTTP endpoints (health, static)  │
│  - CORS middleware                  │
└────────────┬────────────────────────┘
             │
┌────────────▼────────────────────────┐
│  Connection Manager (connection.py) │
│  - WebSocket lifecycle              │
│  - Redis state management           │
│  - Room broadcasting                │
└────────────┬────────────────────────┘
             │
┌────────────▼────────────────────────┐
│  Game Engine (engine.py)            │
│  - Pure functions                   │
│  - State transitions                │
│  - Rule enforcement                 │
└────────────┬────────────────────────┘
             │
┌────────────▼────────────────────────┐
│  Data Models (models.py)            │
│  - Pydantic v2 models               │
│  - Type safety                      │
│  - JSON serialization               │
└─────────────────────────────────────┘
```

### 1.2 データフロー

```
Client Action (JSON)
    ↓
WebSocket Endpoint
    ↓
Connection Manager
    ↓
Game Engine (state transformation)
    ↓
Redis (state persistence)
    ↓
Connection Manager (broadcast)
    ↓
All Clients (JSON)
```

---

## 2. ファイル構成

```
trap_the_cap/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, WebSocket endpoint
│   ├── models.py            # Pydantic models (完全改修)
│   ├── engine.py            # ルールエンジン (完全改修)
│   ├── connection.py        # ConnectionManager (部分改修)
│   ├── bot.py               # Bot AI (新規)
│   ├── utils.py             # ヘルパー関数 (新規)
│   ├── data/
│   │   ├── board_4p_coppit.json  # 盤面データ (新規作成済み)
│   │   └── board_4p.json         # 旧版 (削除予定)
│   └── tests/
│       ├── __init__.py
│       ├── test_models.py        # モデルテスト (新規)
│       ├── test_engine.py        # エンジンテスト (完全改修)
│       ├── test_integration.py   # 統合テスト (新規)
│       └── conftest.py           # pytest fixtures (新規)
├── static/
│   ├── index.html           # UI (改修)
│   ├── game.js              # Canvas rendering + WS client (改修)
│   └── style.css            # スタイル (改修)
├── requirements.txt         # 依存関係
├── render.yaml              # Render Blueprint
├── README.md                # プロジェクト説明
├── SPEC_v3_COPPIT.md        # 仕様書 (作成済み)
├── GAP_LIST.md              # Gap List (作成済み)
└── .env.example             # 環境変数サンプル
```

---

## 3. データモデル（models.py）

### 3.1 Enum定義

```python
from enum import Enum

class PlayerColor(str, Enum):
    RED = "RED"
    BLUE = "BLUE"
    YELLOW = "YELLOW"
    GREEN = "GREEN"

class GamePhase(str, Enum):
    WAITING = "WAITING"           # プレイヤー待ち
    ROLL = "ROLL"                 # サイコロを振る
    SELECT_PIECE = "SELECT_PIECE" # 駒を選ぶ
    SELECT_DIRECTION = "SELECT_DIRECTION"  # 方向を選ぶ
    MOVE = "MOVE"                 # 移動中
    RESOLVE = "RESOLVE"           # 捕獲・確保処理
    GAME_OVER = "GAME_OVER"       # ゲーム終了

class Direction(str, Enum):
    CW = "CW"             # 時計回り (Clockwise)
    CCW = "CCW"           # 反時計回り (Counter-Clockwise)
    NORTH = "NORTH"       # 中央X: 北
    EAST = "EAST"         # 中央X: 東
    SOUTH = "SOUTH"       # 中央X: 南
    WEST = "WEST"         # 中央X: 西
```

### 3.2 Board関連

```python
class BoardNode(BaseModel):
    id: str
    x: float
    y: float
    neighbors: List[str]
    tags: List[str]  # ["NORMAL", "BOX", "SAFE_COLOR", "CROSS", "JUNCTION", "CENTER"]
    color: Optional[PlayerColor] = None  # SAFE_COLORの場合

class Board(BaseModel):
    meta: Dict[str, Any]
    nodes: Dict[str, BoardNode]  # node_id -> BoardNode
    
    @classmethod
    def from_json_file(cls, filepath: str) -> "Board":
        with open(filepath, 'r') as f:
            data = json.load(f)
        nodes = {n['id']: BoardNode(**n) for n in data['nodes']}
        return cls(meta=data.get('meta', {}), nodes=nodes)
```

### 3.3 Piece (Hat)

```python
class Hat(BaseModel):
    id: str  # "red_1", "blue_2", etc.
    color: PlayerColor
    owner: PlayerColor  # 初期所有者（統計用）

class Stack(BaseModel):
    node_id: str  # 現在位置
    pieces: List[Hat]  # index 0が底、-1が最上位
    
    @property
    def controller(self) -> PlayerColor:
        """操作主体（最上位の帽子の色）"""
        return self.pieces[-1].color if self.pieces else None
    
    @property
    def is_captive(self, color: PlayerColor) -> bool:
        """指定色が捕虜として含まれているか"""
        return any(h.color == color for h in self.pieces[:-1])
```

### 3.4 Player

```python
class Player(BaseModel):
    id: str  # "p_1", "p_2", etc.
    name: str
    color: PlayerColor
    is_bot: bool = False
    connected: bool = True
    box_hats: List[Hat] = []  # BOX内の帽子
    banked_hats: List[Hat] = []  # 確保した捕虜
    
    @property
    def score(self) -> int:
        """BOX内の自色帽子数"""
        return len([h for h in self.box_hats if h.color == self.color])
```

### 3.5 GameConfig

```python
class GameConfig(BaseModel):
    max_players: int = 4
    hats_per_player: int = 6
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
```

### 3.6 GameState

```python
class GameState(BaseModel):
    room_id: str
    config: GameConfig
    board: Board
    players: Dict[str, Player]  # player_id -> Player
    turn_order: List[str]  # player_ids
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
    
    @property
    def current_player(self) -> Optional[Player]:
        if not self.turn_order:
            return None
        return self.players[self.turn_order[self.current_turn_index]]
    
    def get_stacks_at_node(self, node_id: str) -> List[Stack]:
        return [s for s in self.stacks if s.node_id == node_id]
    
    def get_player_stacks(self, player_id: str) -> List[Stack]:
        color = self.players[player_id].color
        return [s for s in self.stacks if s.controller == color]
```

### 3.7 Actions & Events

```python
class ClientAction(BaseModel):
    type: str  # "roll", "select_piece", "select_direction", etc.
    payload: Dict[str, Any] = {}

class ActionLog(BaseModel):
    timestamp: float
    turn: int
    player_id: str
    action_type: str
    details: Dict[str, Any]
    result: Dict[str, Any]  # 結果（捕獲発生等）

class ServerEvent(BaseModel):
    type: str  # "state_update", "legal_moves", "error", etc.
    payload: Dict[str, Any]
```

---

## 4. ルールエンジン（engine.py）

### 4.1 設計原則
- **純粋関数中心**: 副作用なし、入力→出力のみ
- **Immutable更新**: 元のstateを変更せず、新しいstateを返す
- **テスト可能**: pytest で完全にカバー

### 4.2 主要関数

```python
# 初期化
def init_game(room_id: str, board: Board, config: GameConfig, seed: Optional[int] = None) -> GameState:
    """ゲーム初期化"""

def add_player(state: GameState, player_id: str, name: str, color: PlayerColor, is_bot: bool = False) -> GameState:
    """プレイヤー追加"""

def start_game(state: GameState) -> GameState:
    """ゲーム開始（全員揃った後）"""

# サイコロ
def roll_dice(state: GameState) -> Tuple[GameState, int]:
    """サイコロを振る（乱数生成）"""

# 合法手
def get_legal_pieces(state: GameState) -> List[Stack]:
    """選択可能な駒（スタック）一覧"""

def get_legal_directions(state: GameState, stack: Stack) -> List[Direction]:
    """選択可能な方向一覧"""

def get_path_for_move(state: GameState, stack: Stack, direction: Direction, dice_value: int) -> List[str]:
    """移動経路（ノードID列）を計算"""

# 移動
def apply_move(state: GameState, stack: Stack, direction: Direction) -> GameState:
    """移動を適用"""

def move_stack_along_path(state: GameState, stack: Stack, path: List[str]) -> GameState:
    """経路に沿ってスタックを移動"""

# 捕獲・SAFE判定
def is_safe(state: GameState, node_id: str, stack: Stack) -> bool:
    """SAFEマス判定"""

def can_capture(state: GameState, attacker: Stack, target: Stack, node_id: str) -> bool:
    """捕獲可能か判定"""

def capture_stack(state: GameState, attacker: Stack, target: Stack) -> GameState:
    """捕獲実行"""

# BOX・確保
def is_box_node(node: BoardNode, color: PlayerColor) -> bool:
    """指定色のBOXか判定"""

def bank_prisoners(state: GameState, player_id: str, stack: Stack) -> GameState:
    """捕虜を確保"""

# 終了判定
def check_game_over(state: GameState) -> Optional[Union[str, List[str]]]:
    """終了条件チェック、勝者を返す"""

# 次手番
def advance_turn(state: GameState) -> GameState:
    """次のプレイヤーへ"""

# 不変条件チェック
def validate_invariants(state: GameState) -> None:
    """不変条件を検証（assert）"""
```

### 4.3 重要アルゴリズム

#### 経路計算（BFS）
```python
def get_path_for_move(state: GameState, stack: Stack, direction: Direction, dice_value: int) -> List[str]:
    """
    BFS でdice_value分の経路を探索
    - direction_lock = true なら方向固定
    - BOX侵入制限
    - ループ対応（外周）
    """
    current = stack.node_id
    path = [current]
    remaining = dice_value
    
    while remaining > 0:
        next_nodes = get_next_nodes(state, current, direction, path)
        if not next_nodes:
            break
        current = next_nodes[0]  # 最初の候補を選択
        path.append(current)
        remaining -= 1
    
    return path
```

#### SAFE判定
```python
def is_safe(state: GameState, node_id: str, stack: Stack) -> bool:
    node = state.board.nodes[node_id]
    
    # BOXは自色にとってSAFE
    if "BOX" in node.tags and node.color == stack.controller:
        return True
    
    # グレーマス（存在する場合）
    if state.config.safe_by_gray and "SAFE_GRAY" in node.tags:
        return True
    
    # 同色マス
    if state.config.safe_by_color and "SAFE_COLOR" in node.tags:
        if node.color == stack.controller:
            return True
    
    return False
```

---

## 5. WebSocket API

### 5.1 接続フロー

```
Client                          Server
  |                               |
  |-- WS Connect (/ws)----------->|
  |                               |
  |<-- Connected -----------------|
  |                               |
  |-- hello {name} -------------->|
  |                               |
  |<-- room_joined {room_id} -----|
  |<-- state_update {GameState}--|
  |                               |
```

### 5.2 Client → Server メッセージ

```json
// ルーム作成
{
  "type": "create_room",
  "payload": {
    "config": { ... }
  }
}

// ルーム参加
{
  "type": "join_room",
  "payload": {
    "room_id": "room_123"
  }
}

// サイコロを振る
{
  "type": "roll"
}

// 駒選択
{
  "type": "select_piece",
  "payload": {
    "stack_index": 0  // get_legal_pieces() の戻り値のindex
  }
}

// 方向選択
{
  "type": "select_direction",
  "payload": {
    "direction": "CW"  // or "CCW", "NORTH", etc.
  }
}

// チャット
{
  "type": "chat",
  "payload": {
    "message": "Good game!"
  }
}
```

### 5.3 Server → Client メッセージ

```json
// 状態更新
{
  "type": "state_update",
  "payload": {
    "game_state": { ... }  // GameState の JSON
  }
}

// 合法手通知
{
  "type": "legal_pieces",
  "payload": {
    "stacks": [ ... ]  // 選択可能なStack一覧
  }
}

{
  "type": "legal_directions",
  "payload": {
    "directions": ["CW", "CCW"]
  }
}

// 手番開始
{
  "type": "turn_start",
  "payload": {
    "player_id": "p_1",
    "phase": "ROLL"
  }
}

// 出目通知
{
  "type": "dice_rolled",
  "payload": {
    "value": 4,
    "player_id": "p_1"
  }
}

// ゲーム終了
{
  "type": "game_over",
  "payload": {
    "winner": "p_2",  // or ["p_1", "p_2"] for tie
    "final_scores": {
      "p_1": 3,
      "p_2": 4,
      "p_3": 2,
      "p_4": 1
    }
  }
}

// エラー
{
  "type": "error",
  "payload": {
    "message": "Invalid move",
    "details": { ... }
  }
}

// チャット
{
  "type": "chat",
  "payload": {
    "player_id": "p_1",
    "name": "Alice",
    "message": "Good game!"
  }
}
```

---

## 6. Redis 設計

### 6.1 キー構造

```
room:{room_id}              → JSON(GameState)
room:{room_id}:lock         → SETNX用ロック
player:{player_id}:room     → room_id（再接続用）
active_rooms                → SET(room_ids)
room:{room_id}:connections  → SET(ws_connection_ids)
```

### 6.2 Pub/Sub（将来のマルチインスタンス対応）

```
channel: room:{room_id}     → イベント配信
```

---

## 7. Bot 実装

### 7.1 BotPlayer

```python
class BotPlayer:
    def __init__(self, player_id: str, color: PlayerColor, difficulty: str = "heuristic"):
        self.player_id = player_id
        self.color = color
        self.difficulty = difficulty
    
    def choose_piece(self, legal_pieces: List[Stack], state: GameState) -> Stack:
        """駒選択"""
        if self.difficulty == "random":
            return random.choice(legal_pieces)
        else:
            return self._heuristic_piece(legal_pieces, state)
    
    def choose_direction(self, legal_directions: List[Direction], state: GameState, stack: Stack) -> Direction:
        """方向選択"""
        if self.difficulty == "random":
            return random.choice(legal_directions)
        else:
            return self._heuristic_direction(legal_directions, state, stack)
    
    def _heuristic_piece(self, legal_pieces: List[Stack], state: GameState) -> Stack:
        """ヒューリスティック：捕獲できる駒を優先"""
        # 優先度:
        # 1. 捕獲が起きる駒
        # 2. BOXに帰還できる駒
        # 3. 捕虜を多く連れている駒
        # 4. ランダム
        ...
```

---

## 8. テスト計画

### 8.1 ユニットテスト（pytest）

```python
# test_models.py
def test_stack_controller():
    """スタックの操作主体が正しいか"""

def test_player_score():
    """スコア計算が正しいか"""

# test_engine.py
def test_init_game():
    """初期化が正しいか"""

def test_roll_dice_deterministic():
    """同じseedで同じ出目になるか"""

def test_get_legal_pieces():
    """合法手が正しく列挙されるか"""

def test_capture():
    """捕獲処理が正しいか"""

def test_safe_by_color():
    """同色SAFE判定が正しいか"""

def test_bank_prisoners():
    """確保処理が正しいか"""

def test_game_over_condition():
    """終了条件が正しいか"""

def test_invariants():
    """不変条件が保たれるか"""
```

### 8.2 統合テスト

```python
# test_integration.py
def test_full_game_simulation():
    """ゲーム開始〜終了まで通るか"""

def test_websocket_flow():
    """WebSocket通信が正しいか"""
```

---

## 9. デプロイ（Render）

### 9.1 render.yaml

```yaml
services:
  - type: web
    name: coppit-game
    env: python
    buildCommand: "pip install -r requirements.txt"
    startCommand: "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
    envVars:
      - key: REDIS_URL
        fromService:
          name: coppit-redis
          type: redis
          property: connectionString
      - key: APP_ENV
        value: production

  - type: redis
    name: coppit-redis
    plan: starter
    maxmemoryPolicy: noeviction
```

---

## 10. 実装順序

1. ✅ **仕様書・盤面JSON** (完了)
2. ✅ **Gap List** (完了)
3. ✅ **実装計画** (このドキュメント)
4. 🚧 **models.py 完全改修**
5. 🚧 **engine.py 完全改修**
6. 🚧 **connection.py 部分改修**
7. 🚧 **bot.py 新規作成**
8. 🚧 **tests/ テスト作成**
9. 🚧 **main.py WebSocketエンドポイント改修**
10. 🚧 **static/ フロントエンド改修**

---

**END OF IMPLEMENTATION PLAN**

# Coppit (コピット) オンライン対戦版

ボードゲーム「Coppit」のPython実装（FastAPI + WebSocket）

## 📋 実装状況

### ✅ 完了
- **データモデル** ([models.py](app/models.py))
  - GamePhase 7種（WAITING, ROLL, SELECT_PIECE, SELECT_DIRECTION, MOVE, RESOLVE, GAME_OVER）
  - Direction 6種（CW, CCW, NORTH, EAST, SOUTH, WEST）
  - Board/BoardNode/Stack/Player/GameConfig/GameState
  - WebSocketメッセージ（ClientAction/ServerEvent）

- **ゲームエンジン** ([engine.py](app/engine.py))
  - init_game, add_player, setup_initial_board
  - roll_dice, advance_turn
  - get_legal_stacks, get_legal_directions, can_move_stack
  - apply_move, calculate_path, deploy_from_box
  - is_safe, resolve_captures, resolve_box_return
  - check_game_over, determine_winner

- **Bot実装** ([bot.py](app/bot.py))
  - BotPlayerクラス（ヒューリスティック戦略）
  - choose_piece, choose_direction
  - execute_bot_turn（自動プレイ）

- **サーバー** ([main.py](app/main.py))
  - FastAPI + WebSocket
  - InMemoryStore（Redis不要でローカル実行可能）
  - Bot監視タスク（自動プレイ）

- **盤面データ** ([board_4p_coppit.json](app/data/board_4p_coppit.json))
  - 61ノード（外周48 + 中央X 9 + BOX 4）
  - 正確な座標・隣接関係
  - 色マス（SAFE_COLOR）12個

- **テスト** ([tests/test_engine.py](tests/test_engine.py))
  - 基本的なユニットテスト
  - GameInitialization, DiceRoll, Movement, Safety, GameOver

- **ドキュメント**
  - [SPEC_v3_COPPIT.md](SPEC_v3_COPPIT.md) - 完全仕様書（14セクション）
  - [GAP_LIST.md](GAP_LIST.md) - 不明点リスト（P1/P2分類）
  - [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) - 実装計画（10セクション）

### 🚧 今後の作業
1. フロントエンド（static/）の新仕様対応
2. 経路計算の完全実装（方向選択時のパス探索）
3. 中央Xの詳細ルール実装
4. エンドツーエンドテスト
5. UI改善（盤面描画、アニメーション）

## 🚀 起動方法

### 1. 依存パッケージインストール
```bash
pip install fastapi uvicorn websockets pydantic redis
```

### 2. サーバー起動
```bash
cd trap_the_cap
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 3. ブラウザでアクセス
```
http://127.0.0.1:8000
```

### 4. 動作確認スクリプト
```bash
python test_basic.py
```

## 📖 ゲームルール（P0確定）

### 基本ルール
- プレイヤー: 2-4人
- 帽子: 各色6個（合計24個）
- 初期配置: 全帽子がBOXで待機

### 手番の流れ
1. **サイコロを振る**（1-6）
2. **駒を選ぶ**（6ならBOXから出撃可能）
3. **方向を選ぶ**（分岐点の場合）
4. **移動実行**（捕獲・帰還判定）

### 特殊ルール
- **6で追加ロール**: 6を出したらもう一度サイコロを振れる
- **色マスSAFE**: 同色マスにいる自色帽子は捕獲されない
- **捕虜確保**: BOXに帰還すると連れている捕虜を確保
- **終了条件**: 盤上に1色のみ残った時点

### 盤面構造
- **外周**: 48マス（時計回り/反時計回り）
- **中央X**: 9マス（4方向 + 中心）
- **BOX**: 4箇所（各色の待機所）
- **色マス**: 各色6個（外周4 + 中央X 2）

## 🛠️ 技術スタック
- **Backend**: Python 3.12 + FastAPI + WebSocket
- **Frontend**: HTML5 Canvas + JavaScript
- **Data**: Pydantic v2（型安全）
- **State**: InMemoryStore（Redis optional）
- **Test**: pytest

## 📁 ディレクトリ構造
```
trap_the_cap/
├── app/
│   ├── models.py          # データモデル
│   ├── engine.py          # ゲームエンジン
│   ├── bot.py             # Bot実装
│   ├── connection.py      # WebSocket管理
│   ├── main.py            # FastAPIアプリ
│   └── data/
│       └── board_4p_coppit.json  # 盤面データ
├── static/
│   ├── index.html         # フロントエンド
│   ├── game.js            # ゲームロジック
│   └── style.css
├── tests/
│   └── test_engine.py     # ユニットテスト
├── SPEC_v3_COPPIT.md      # 完全仕様書
├── GAP_LIST.md            # 不明点リスト
├── IMPLEMENTATION_PLAN.md # 実装計画
└── test_basic.py          # 動作確認スクリプト
```

## 📝 開発メモ

### 2025-12-23
- models.py完全書き換え（Direction/GamePhase拡張/Board/GameConfig）
- engine.py完全書き換え（純粋関数15個）
- bot.py新規作成（ヒューリスティック戦略）
- main.py完成（WebSocketハンドラ + Bot監視）
- tests/test_engine.py作成
- 基本動作確認成功 ✅

### 次のマイルストーン
1. フロントエンドの新仕様対応
2. 経路計算の完全実装
3. エンドツーエンドテスト
4. デプロイ準備（render.yaml）

## 🎮 WebSocket API

### Client → Server
- `{"type": "roll", "payload": {}}`
- `{"type": "select_piece", "payload": {"stack": {...}}}`
- `{"type": "select_direction", "payload": {"direction": "CW"}}`

### Server → Client
- `{"type": "state_update", "payload": {"game_state": {...}}}`
- `{"type": "legal_pieces", "payload": {"stacks": [...]}}`
- `{"type": "legal_directions", "payload": {"directions": ["CW", "CCW"]}}`
- `{"type": "dice_rolled", "payload": {"value": 6, "player_id": "p1"}}`
- `{"type": "game_over", "payload": {"winner": "p1", "final_scores": {...}}}`

## 🔗 参考リンク
- 公式ルール解説: https://yama.kitashirakawa.jp/yama-blog/?p=1980
- 盤面画像: SPEC_v3_COPPIT.md参照

---

**Status**: 🟢 基本実装完了・動作確認OK

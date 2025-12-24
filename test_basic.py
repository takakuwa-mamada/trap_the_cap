"""
簡易動作確認スクリプト
ゲームの基本フローをテスト
"""

import sys
sys.path.insert(0, '.')

from app.models import GameConfig, Board
from app.engine import (
    init_game, add_player, roll_dice, 
    get_legal_stacks, advance_turn
)

def test_game_flow():
    """基本的なゲームフローをテスト"""
    print("=== Coppit Game Test ===\n")
    
    # 1. 盤面読み込み
    print("1. Loading board...")
    board = Board.from_json_file("app/data/board_4p_coppit.json")
    print(f"   Board nodes: {len(board.nodes)}")
    
    # 2. ゲーム初期化
    print("\n2. Initializing game...")
    config = GameConfig()
    state = init_game("test_room", board, config)
    print(f"   Room: {state.room_id}")
    print(f"   Phase: {state.phase.value}")
    
    # 3. プレイヤー追加
    print("\n3. Adding players...")
    state = add_player(state, "p1", "Alice", is_bot=False)
    state = add_player(state, "p2", "Bob", is_bot=True)
    print(f"   Players: {len(state.players)}")
    for pid, player in state.players.items():
        print(f"   - {player.name} ({player.color.value}): {len(player.box_hats)} hats in BOX")
    
    # 4. ゲーム開始確認
    print(f"\n4. Game phase: {state.phase.value}")
    print(f"   Current player: {state.current_player_id}")
    
    # 5. サイコロを振る
    print("\n5. Rolling dice...")
    dice_value = roll_dice(state, seed=42)
    print(f"   Dice: {dice_value}")
    
    # 6. 合法手確認
    print("\n6. Checking legal moves...")
    legal = get_legal_stacks(state, state.current_player_id)
    print(f"   Legal stacks: {len(legal)}")
    
    if dice_value == 6:
        print("   ✓ Can deploy from BOX!")
    else:
        print("   ✗ No pieces on board, need 6 to deploy")
    
    # 7. ターン進行
    print("\n7. Advancing turn...")
    advance_turn(state)
    print(f"   Next player: {state.current_player_id}")
    print(f"   Turn count: {state.turn_count}")
    
    print("\n=== Test Complete ===")
    return True

if __name__ == "__main__":
    try:
        success = test_game_flow()
        if success:
            print("\n✅ All tests passed!")
            sys.exit(0)
        else:
            print("\n❌ Tests failed!")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

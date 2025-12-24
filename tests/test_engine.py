"""
Coppit Engine Tests
ゲームエンジンの基本動作テスト
"""

import pytest
from app.models import (
    GameState, GamePhase, PlayerColor, GameConfig, Board,
    Stack, Hat, Player, create_hat, create_initial_hats
)
from app.engine import (
    init_game, add_player, setup_initial_board,
    roll_dice, get_legal_stacks, apply_move,
    is_safe, check_game_over
)


@pytest.fixture
def test_board():
    """テスト用盤面"""
    return Board.from_json_file("app/data/board_4p_coppit.json")


@pytest.fixture
def test_config():
    """テスト用設定"""
    return GameConfig(
        max_players=4,
        hats_per_player=6,
        extra_roll_on_6=True
    )


@pytest.fixture
def initialized_game(test_board, test_config):
    """初期化済みゲーム"""
    state = init_game("test_room", test_board, test_config)
    state = add_player(state, "p1", "Player 1", is_bot=False)
    state = add_player(state, "p2", "Player 2", is_bot=True)
    return state


class TestGameInitialization:
    """ゲーム初期化テスト"""
    
    def test_init_game(self, test_board, test_config):
        """ゲーム初期化"""
        state = init_game("room1", test_board, test_config)
        assert state.room_id == "room1"
        assert state.phase == GamePhase.WAITING
        assert len(state.players) == 0
        assert len(state.stacks) == 0
    
    def test_add_player(self, test_board, test_config):
        """プレイヤー追加"""
        state = init_game("room1", test_board, test_config)
        state = add_player(state, "p1", "Alice")
        
        assert len(state.players) == 1
        assert "p1" in state.players
        assert state.players["p1"].name == "Alice"
        assert state.players["p1"].color == PlayerColor.RED
    
    def test_game_starts_with_two_players(self, test_board, test_config):
        """2人でゲーム開始"""
        state = init_game("room1", test_board, test_config)
        state = add_player(state, "p1", "Alice")
        state = add_player(state, "p2", "Bob")
        
        assert state.phase == GamePhase.ROLL
        assert len(state.players) == 2
        # 全帽子がBOXにある
        total_hats = sum(len(p.box_hats) for p in state.players.values())
        assert total_hats == test_config.hats_per_player * 2


class TestDiceRoll:
    """サイコロテスト"""
    
    def test_roll_dice(self, initialized_game):
        """サイコロを振る"""
        state = initialized_game
        value = roll_dice(state, seed=42)
        
        assert value >= 1 and value <= 6
        assert state.dice_value == value
        assert len(state.logs) > 0
    
    def test_roll_produces_different_values(self, initialized_game):
        """異なる値が出る"""
        state = initialized_game
        values = set()
        for i in range(20):
            roll_dice(state, seed=i)
            values.add(state.dice_value)
        
        # 20回で少なくとも3種類は出るはず
        assert len(values) >= 3


class TestMovement:
    """移動テスト"""
    
    def test_get_legal_stacks_empty_board(self, initialized_game):
        """盤面が空の場合"""
        state = initialized_game
        roll_dice(state, seed=1)
        
        legal = get_legal_stacks(state, "p1")
        
        # サイコロが6でなければ、盤面に駒がないので移動不可
        if state.dice_value == 6:
            assert len(legal) > 0  # BOXから出撃可能
        else:
            assert len(legal) == 0
    
    def test_deploy_from_box_on_six(self, initialized_game):
        """6でBOXから出撃"""
        state = initialized_game
        state.dice_value = 6
        
        legal = get_legal_stacks(state, "p1")
        assert len(legal) > 0
        
        # 出撃実行
        virtual_stack = legal[0]
        assert virtual_stack.node_id.startswith("box_")


class TestSafety:
    """安全地帯テスト"""
    
    def test_color_safe_zone(self, test_board, test_config):
        """同色マスは安全"""
        state = init_game("room1", test_board, test_config)
        state = add_player(state, "p1", "Player1")
        setup_initial_board(state)
        
        # REDプレイヤーの帽子
        red_hat = create_hat(PlayerColor.RED, 1)
        red_stack = Stack(node_id="test", pieces=[red_hat])
        
        # REDの色マス（SAFE_COLOR）を探す
        red_safe_node = None
        for node_id, node in test_board.nodes.items():
            if node.is_safe_color() and node.color == PlayerColor.RED:
                red_safe_node = node_id
                break
        
        if red_safe_node:
            assert is_safe(state, red_stack, red_safe_node) == True
    
    def test_box_is_always_safe(self, test_board, test_config):
        """BOXは常に安全"""
        state = init_game("room1", test_board, test_config)
        state = add_player(state, "p1", "Player1")
        
        hat = create_hat(PlayerColor.RED, 1)
        stack = Stack(node_id="box_red", pieces=[hat])
        
        assert is_safe(state, stack, "box_red") == True


class TestGameOver:
    """ゲーム終了テスト"""
    
    def test_game_over_single_color_on_board(self, initialized_game):
        """盤上1色のみで終了"""
        state = initialized_game
        
        # 盤面に1色のみ配置
        red_hat = create_hat(PlayerColor.RED, 1)
        state.stacks = [Stack(node_id="outer_0", pieces=[red_hat])]
        
        check_game_over(state)
        
        # 1色なので終了判定
        assert state.phase == GamePhase.GAME_OVER
        assert state.winner is not None


class TestHelperFunctions:
    """ヘルパー関数テスト"""
    
    def test_create_hat(self):
        """帽子生成"""
        hat = create_hat(PlayerColor.RED, 1)
        assert hat.id == "red_1"
        assert hat.color == PlayerColor.RED
        assert hat.owner == PlayerColor.RED
    
    def test_create_initial_hats(self):
        """初期帽子生成"""
        hats = create_initial_hats(PlayerColor.BLUE, 6)
        assert len(hats) == 6
        assert all(h.color == PlayerColor.BLUE for h in hats)
        assert hats[0].id == "blue_1"
        assert hats[5].id == "blue_6"


class TestStack:
    """スタッククラステスト"""
    
    def test_stack_controller(self):
        """最上位の色が操作権"""
        red_hat = create_hat(PlayerColor.RED, 1)
        blue_hat = create_hat(PlayerColor.BLUE, 1)
        
        stack = Stack(node_id="test", pieces=[red_hat, blue_hat])
        assert stack.controller == PlayerColor.BLUE
    
    def test_stack_captives(self):
        """捕虜判定"""
        red_hat = create_hat(PlayerColor.RED, 1)
        blue_hat = create_hat(PlayerColor.BLUE, 1)
        
        stack = Stack(node_id="test", pieces=[red_hat, blue_hat])
        assert stack.has_captives() == True
        assert len(stack.captives()) == 1
        assert stack.captives()[0].color == PlayerColor.RED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

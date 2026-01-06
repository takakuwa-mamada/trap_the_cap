# 🎩 Coppit Online (コピット オンライン)

オンライン対戦可能なボードゲーム「Coppit（コピット）」の実装です。  
4人プレイヤーで帽子を奪い合う戦略的なボードゲームをブラウザで楽しめます。

[![Play Now](https://img.shields.io/badge/Play-Now-blue?style=for-the-badge)](https://trap-the-cap.onrender.com)

## 🎮 ゲームの遊び方

### 目的
相手の帽子（駒）を捕まえて、自分のBOX（スタート地点）に持ち帰ることが目標です！  
最も多くのポイントを獲得したプレイヤーが勝利します。

### 基本ルール

1. **サイコロを振る**  
   - 自分のターンになったら「🎲 サイコロを振る」ボタンをクリック
   - 1〜6の目が出ます

2. **駒を選ぶ**  
   - 黄色く光っている駒（帽子の山）をクリックして選択
   - サイコロの目の数だけ移動できます

3. **方向を選ぶ**  
   - 複数の移動先がある場合は、方向選択ボタンが表示されます
   - ↻ 時計回り / ↺ 反時計回り / → 中心へ / ← 外側へ

4. **相手を捕獲する**  
   - 相手の駒がいるマスに入ると、その駒を捕獲できます
   - 捕獲した駒は自分の駒の上に重なります

5. **BOXに帰還する**  
   - 捕獲した駒を持ったまま、サイコロの目とBOXまでの距離がピッタリ一致すると帰還できます
   - 帰還すると敵の駒1個につき1ポイント獲得！

### 特別ルール

- **🎲 6の目**: BOXから新しい駒を出せます（最大4個まで）
- **🛡️ セーフスクエア**: 自分の色のマス（赤・青・黄・緑）は安全地帯で、そこにいる駒は捕獲されません
- **🤖 Bot自動追加**: 1人でプレイする場合、残りの3人は自動的にBotが追加されます

## 🚀 遊び方

### オンラインでプレイ（推奨）
デプロイ済みサイトで今すぐプレイできます：  
👉 **https://trap-the-cap.onrender.com**

1. ルーム名を入力（例: `room123`）
2. 友達に同じルーム名を共有
3. 全員が集まったらゲームスタート！

### ローカル環境で起動

```bash
# 1. リポジトリをクローン
git clone https://github.com/takakuwa-mamada/trap_the_cap.git
cd trap_the_cap

# 2. 必要なパッケージをインストール
pip install -r requirements.txt

# 3. サーバーを起動
uvicorn app.main:app --reload --host 0.0.0.0 --port 8005

# 4. ブラウザでアクセス
# http://localhost:8005
```

## 🛠️ 技術スタック

### バックエンド
- **Python 3.12+**
- **FastAPI**: 高速なWebフレームワーク
- **WebSocket**: リアルタイム通信
- **Redis**: ゲーム状態の永続化（オプション）
- **Pydantic**: データバリデーション

### フロントエンド
- **HTML5 Canvas**: ボード描画
- **Vanilla JavaScript**: ゲームロジック
- **WebSocket API**: サーバー通信
- **レスポンシブデザイン**: スマホ・PC対応

### デプロイ
- **Render.com**: サーバーホスティング
- **GitHub**: ソースコード管理

## 📁 プロジェクト構造

```
trap_the_cap/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPIアプリケーション
│   ├── connection.py     # WebSocket接続管理
│   ├── models.py         # ゲームデータモデル
│   ├── engine.py         # ゲームロジック（900+ lines）
│   ├── bot.py            # Bot AI実装
│   └── data/
│       └── board_4p_coppit.json  # ボード定義
├── static/
│   ├── index.html        # ロビー画面
│   ├── game.html         # ゲーム画面
│   ├── game.js           # クライアントロジック（600+ lines）
│   └── style.css         # スタイリング
├── tests/
│   └── test_engine.py    # ユニットテスト
├── docs/                 # 開発ドキュメント
├── requirements.txt      # Python依存パッケージ
├── render.yaml           # Renderデプロイ設定
└── README.md             # このファイル
```

## 🎯 実装された主要機能

### ゲームシステム
- ✅ 4人プレイヤー対戦（人間 + Bot）
- ✅ サイコロによるターン制移動
- ✅ 駒の捕獲システム
- ✅ BOX帰還とポイント計算
- ✅ セーフスクエア（安全地帯）
- ✅ 勝利条件判定

### マルチプレイヤー
- ✅ ルームベースのマッチング
- ✅ WebSocketリアルタイム通信
- ✅ Bot自動追加（1人でもプレイ可能）
- ✅ ゲームリセット機能

### UI/UX
- ✅ レスポンシブデザイン（スマホ・PC対応）
- ✅ タッチ操作サポート
- ✅ Canvas動的リサイズ
- ✅ 盤面固定表示（スクロール対応）
- ✅ 折りたたみ式ルール説明
- ✅ ゲームログ表示
- ✅ プレイヤー情報表示

## 🧪 テスト

```bash
# ユニットテストを実行
pytest tests/

# カバレッジレポート生成
pytest --cov=app tests/
```

## 🌐 デプロイ

### Render.com へのデプロイ

1. GitHubリポジトリと連携
2. `render.yaml`が自動的に検出されます
3. 環境変数を設定（オプション）:
   - `REDIS_URL`: Redis接続URL（利用する場合）

### 環境変数

| 変数名 | 説明 | デフォルト |
|--------|------|-----------|
| `REDIS_URL` | Redis接続URL | なし（インメモリストア使用） |

## 🤝 貢献

プルリクエスト大歓迎です！以下の流れで貢献できます：

1. このリポジトリをフォーク
2. 新しいブランチを作成 (`git checkout -b feature/amazing-feature`)
3. 変更をコミット (`git commit -m 'Add amazing feature'`)
4. ブランチにプッシュ (`git push origin feature/amazing-feature`)
5. プルリクエストを作成

## 📝 ライセンス

このプロジェクトはMITライセンスの下で公開されています。

## 🎲 ゲームの歴史

Coppitは1960年代にドイツで生まれたボードゲームです。  
シンプルながら戦略性の高いゲームプレイで、世界中で愛されています。

このプロジェクトは、古典的なボードゲームを現代のWeb技術で再現し、  
オンラインで友達と楽しめるようにすることを目的としています。

## 📞 お問い合わせ

質問や提案がある場合は、[Issues](https://github.com/takakuwa-mamada/trap_the_cap/issues)で報告してください。

---

**Made with ❤️ by [takakuwa-mamada](https://github.com/takakuwa-mamada)**

🎮 **今すぐプレイ**: https://trap-the-cap.onrender.com

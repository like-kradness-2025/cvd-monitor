# cvd-monitor

Coinalyze `buy_volume` ベースの CVD (Cumulative Volume Delta) 監視ダッシュボード。

## セットアップ

```bash
cp .env.example .env
# COINALYZE_API_KEY を設定
pip install -r requirements.txt
```

## 使用方法

```bash
# データ取得
python -m cvd_monitor receive --once --interval 5min --lookback-hours 6

# CVD特徴量計算（日次ローリング）
python -m cvd_monitor compute --interval 5min --rolling-hours 24

# チャート描画
python -m cvd_monitor render --interval 5min --window-hours 6 --output out/cvd.png

# ワンショット実行
python -m cvd_monitor run-once --interval 5min --lookback-hours 6 --output out/cvd.png

# テスト
pytest -q
```

## 機能

- Coinalyze OHLCV データ受信
- `buy_volume` ベースの CVD 計算（日次ローリング対応）
- matplotlib ダッシュボード描画
- Discord 通知（オプション）
- Core20 ユニバース対応

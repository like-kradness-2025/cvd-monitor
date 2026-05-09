# cvd-monitor

BTC の CVD (Cumulative Volume Delta) を CoinAlYZe API から取得し、SQLite に保存してダッシュボード化するための雛形です。

## 構成
- `src/cvd_monitor/coinalyze.py` : API クライアント
- `src/cvd_monitor/cvd_calculator.py` : CVD 計算
- `src/cvd_monitor/database.py` : SQLite 保存
- `src/cvd_monitor/dashboard.py` : matplotlib によるチャート生成
- `src/cvd_monitor/discord_sender.py` : Discord 送信

## セットアップ
1. `.env.example` を `.env` にコピー
2. `pip install -r requirements.txt`
3. 必要に応じて scheduler を起動

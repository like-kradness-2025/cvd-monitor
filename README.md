# cvd-monitor

BTC の CVD（Cumulative Volume Delta）を CoinAlYze API から取得・近似計算し、SQLite に保存してチャート化し、必要に応じて Discord に送信するための小さな監視ツールです。

> 現状の CVD は OHLCV ローソク足の方向を使った **近似 CVD** です。約定単位の buy/sell delta ではありません。

## 構成

```text
src/cvd_monitor/
  coinalyze.py        CoinAlYze API クライアント
  cvd_calculator.py   近似 CVD 計算
  database.py         SQLite 保存・取得
  dashboard.py        matplotlib によるチャート生成
  discord_sender.py   Discord webhook 送信
  markets.py          マーケット抽出ヘルパー
  scheduler.py        取得 → 保存 → 描画 → 送信の実行役
```

## セットアップ

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# .env に COINALYZE_API_KEY と DISCORD_WEBHOOK_URL を設定
```

## 最小実行例

```python
from cvd_monitor.scheduler import Scheduler, SchedulerConfig

scheduler = Scheduler(SchedulerConfig.from_env())
scheduler.run_once()
```

## 主な環境変数

| 変数 | 既定値 | 説明 |
|---|---:|---|
| `COINALYZE_API_KEY` | 空 | CoinAlYze API キー |
| `DISCORD_WEBHOOK_URL` | 空 | Discord 送信用 webhook |
| `DATABASE_PATH` | `data/cvd_monitor.sqlite3` | SQLite DB |
| `CVD_SYMBOL` | `BTCUSDT` | 監視対象シンボル |
| `CVD_TIMEFRAME` | `1h` | 取得足 |
| `CVD_HISTORY_CANDLES` | `500` | 1回の取得本数 |
| `CVD_INTERVAL_SECONDS` | `3600` | 常駐実行時の待機秒数 |
| `CVD_DASHBOARD_PATH` | `artifacts/dashboard.png` | 出力画像 |

## 注意

CoinAlYze API は `api_key` ヘッダーまたはクエリパラメータで認証します。このツールではヘッダー方式を使います。

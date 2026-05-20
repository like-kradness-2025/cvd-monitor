# cvd-monitor

Core20 用の Coinalyze CVD 監視ツールです。

## できること
- `receive`: Coinalyze OHLCV を取得して SQLite に保存
- `compute`: 保存済み raw OHLCV から CVD 特徴量を計算
- `render`: Core20 universe のスマホ向け縦長PNGを生成
- `run-once`: `receive -> compute -> render -> Discord` を1回実行

## 前提
- `market_key` を内部 ID として扱う
- 表示ラベルは `display_pair` / `symbol_on_exchange` から取得する
- `BTCUSD.A` の表示は `BTC/USDT`
- `FDUSDUSD.A` の表示は `FDUSD/USDT`
- 未完了キャンドルは除外する
- 重複は upsert で処理する
- 41 universe は残す


## 経路整理済み版

このZIPは直下に `cvd_monitor/` がある構成です。前回の `cvd_phone/cvd_monitor/` ネストは廃止しました。

必ずZIP直下で実行してください。

```bash
python -m cvd_monitor render --interval 5min --window-hours 24 --cum-window-hours 72 --universe config/universe.core20.yml --output out/cvd_core20_latest.png
```

成功時のCLI出力に以下が出ます。

```text
layout=phone_portrait_wide_label_margin_24h_rolling_cum_delta_v12_cleanroot
```

これが出ない場合は古いフォルダか、古いインストール済みパッケージを読んでいます。
`run_phone_portrait.sh` は自分の場所へ `cd` してから実行する確認用ショートカットです。

## セットアップ
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## 環境変数
| 変数 | 説明 | 既定 |
|---|---|---|
| `COINALYZE_API_KEY` | Coinalyze API key | 空 |
| `DISCORD_WEBHOOK_URL` | Discord webhook | 空なら送信しない |
| `DB_PATH` | SQLite DB | `data/cvd_monitor.sqlite` |
| `MARKETS_CONFIG_PATH` | universe 設定 | `config/universe.generated.yml` |
| `OUTPUT_DIR` | 出力先 | `out` |
| `REQUEST_TIMEOUT_SECONDS` | HTTP timeout | `20` |
| `LOG_LEVEL` | log level | `INFO` |


## 表示ロジック
- 画像はスマホ確認を優先したコンパクト縦長レイアウト（1280 x 1920px目安）
- 4段構成: BTC価格 / 現物CVD累積デルタ / 先物CVD累積デルタ / ステーブルCVD累積デルタ
- CVDパネルは各足の `ΔCVD` を市場ごとに正規化し、既定では72hのローリング文脈で累積して、表示は直近24hに絞る
- `delta_quote` を優先し、サイズ差を無視しやすいよう市場ごとに robust scale 正規化する
- 目的は「絶対量の大きさ」ではなく「その市場にとって買い/売り圧が累積しているか」を見ること

## Core20 autorun
```bash
python -m cvd_monitor run-once \
  --interval 5min \
  --lookback-hours 72 \
  --universe config/universe.core20.yml \
  --output out/cvd_core20_latest.png \
  --discord
```

### 挙動
- `--discord` があっても webhook 未設定なら安全にスキップ
- Discord 失敗は non-fatal
- 出力画像と短い要約を送る
- `run-once` は失敗シンボルを返す

## 単体実行
```bash
python -m cvd_monitor receive --once --interval 5min --lookback-hours 72 --universe config/universe.core20.yml
python -m cvd_monitor compute --interval 5min --universe config/universe.core20.yml
python -m cvd_monitor render --interval 5min --window-hours 24 --cum-window-hours 72 --universe config/universe.core20.yml --output out/cvd_core20_latest.png
```


## 今回の修正メモ
- `out/cvd_core20_latest.png` 自体をスマホ縦長レイアウトに更新済み
- 古い横長プレビューと間違えないよう、同梱PNGは最新系だけに整理
- `cvd_core20_latest_phone_portrait.png` は確認用エイリアス

## テスト
```bash
pytest -q
```

## レポート
- `docs/CORE20_AUTORUN_REVIEW.md`
- `docs/CORE20_DATA_COVERAGE_REVIEW.md`

## 注意
- secret はログに出さない
- package は clean extraction で実行できることを前提にする


## compact portrait v3
- 前回の 1080x2400 系は縦に長すぎたため、1280x1920 目安へ圧縮。
- `savefig(..., bbox_inches='tight')` を廃止し、出力サイズが毎回ブレないように固定。
- 実行時表示: `layout=phone_portrait_wide_label_margin_24h_rolling_cum_delta_v12_cleanroot`


## endpoint labels v6
- 従来の凡例を廃止。
- 各ラインの最新値付近、チャート右端の内側に、同色のシンボル名ラベルを直接表示。
- 縦軸は右側のまま維持。
- 実行時表示: `layout=phone_portrait_wide_label_margin_24h_rolling_cum_delta_v12_cleanroot`


## pair color labels v8
- CVDライン色は `BASE/QUOTE` の共通キーで固定。
- 現物/先物を跨いでも、同じ対象ペアなら同じ色。例: BTC/USDT spot と BTC/USDT perp。
- 取引所差は右端ラベルと補助的な線種で識別。
- 実行時表示: `layout=phone_portrait_wide_label_margin_24h_rolling_cum_delta_v12_cleanroot`


## venue-pair color labels v9

- 同じ `取引所 + BASE/QUOTE` は現物/先物をまたいでも同じライン色。
- 例: Binance BTC/USDT spot と Binance BTC/USDT perp は同色。
- 例: Binance BTC/USDT と OKX BTC/USDT は別色。
- 変更対象はライン色のみ。線種・線幅・右端ラベル仕様はスマホ向けのまま固定。
- 実行時表示: `layout=phone_portrait_wide_label_margin_24h_rolling_cum_delta_v12_cleanroot`


## venue-pair color labels v10

- 色キーを `BASE/QUOTE` から `exchange + BASE/QUOTE` に修正。
- 取引所が同じで、BTC/ステーブル系ペアも同じなら、現物パネルと先物パネルで同じライン色にする。
- 取引所が違う同一ペアは同色にしない。
- 線種・線幅・ラベル位置は変更せず、ライン色だけを修正。
- 実行時表示: `layout=phone_portrait_wide_label_margin_24h_rolling_cum_delta_v12_cleanroot`


## v11: 24h表示 + rolling cumulative ΔCVD + 右端ラベル余白
- 表示範囲はデフォルトで直近24h。
- CVD累積は全期間ではなく、デフォルト72hのローリング文脈から積み上げて、最後の24hだけ描画する。Rolling VWAP的に「直近の圧力状態」を残すため。
- 右端ラベル用に未来側の余白を追加し、ライン終端がラベルで隠れにくいようにした。
- Coinbase `USDC/USD` は従来の core20 universe に存在しなかったため表示されていなかった。今回 `coinbase:usdcusd.c` / `USDCUSD.C` を universe に追加。もしCoinalyze側で取得できない場合でも、receiverはバッチ全体を落とさず個別リトライで隔離する。
- 実行時表示: `layout=phone_portrait_wide_label_margin_24h_rolling_cum_delta_v12_cleanroot`

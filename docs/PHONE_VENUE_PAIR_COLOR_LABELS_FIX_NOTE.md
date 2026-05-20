# PHONE_VENUE_PAIR_COLOR_LABELS_FIX_NOTE

## 修正内容

ライン色の統一キーを `BASE/QUOTE` から `exchange + BASE/QUOTE` に変更した。

## 意図

- 同じ取引所の同じBTC/ステーブル系ペアは、現物と先物で同じ色にする。
- 取引所が違う同一ペアは、別の色にする。
- 線種・線幅・右端ラベル仕様は変更しない。

## 例

- Binance BTC/USDT spot と Binance BTC/USDT perp: 同色
- Binance BTC/USDT と OKX BTC/USDT: 別色

## 実行時識別子

```text
layout=phone_portrait_wide_venue_pair_color_labels_cum_delta_v10
```

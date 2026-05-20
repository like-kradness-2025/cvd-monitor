# Coinalyze market universe report

## summary
- missing desired core markets: none

## counts by group
- btc_spot: 10
- btc_perp: 10
- stable_stable: 10
- stable_fiat: 11

## selected table by group
| group | symbol | exchange | type | priority | warning |
|---|---|---|---|---:|---|
| btc_spot | BTCUSD.C | Coinbase | spot | 100 |  |
| btc_spot | BTCUSD.A | Binance | spot | 100 |  |
| btc_spot | BTCUSDC.A | Binance | spot | 100 |  |
| btc_spot | BTCFDUSD.A | Binance | spot | 100 |  |
| btc_spot | BTCUSD.K | Kraken | spot | 100 |  |
| btc_spot | BTCUSDT.K | Kraken | spot | 100 |  |
| btc_spot | BTCUSDC.K | Kraken | spot | 100 |  |
| btc_spot | BTCUSD.F | Bitfinex | spot | 100 |  |
| btc_spot | BTCUSDT.F | Bitfinex | spot | 100 |  |
| btc_spot | BTCEUR.C | Coinbase | spot | 100 |  |
| btc_perp | BTCUSDT_PERP.A | Binance | future | 100 |  |
| btc_perp | BTCUSD_PERP.A | Binance | future | 100 |  |
| btc_perp | BTCUSDC_PERP.A | Binance | future | 100 |  |
| btc_perp | BTCUSDT.6 | Bybit | future | 100 |  |
| btc_perp | BTCUSD.6 | Bybit | future | 100 |  |
| btc_perp | BTCUSDT_PERP.3 | OKX | future | 100 |  |
| btc_perp | BTCUSD_PERP.3 | OKX | future | 100 |  |
| btc_perp | BTC.H | Hyperliquid | future | 100 |  |
| btc_perp | BTCUSD_PERP.0 | BitMEX | future | 100 |  |
| btc_perp | BTC-PERPETUAL.2 | Deribit | future | 100 |  |
| stable_stable | FDUSDUSD.A | Binance | spot | 100 |  |
| stable_stable | USDCUSD.A | Binance | spot | 100 |  |
| stable_stable | sUSDCUSDT.6 | Bybit | spot | 100 |  |
| stable_stable | USDCUSDT.K | Kraken | spot | 100 |  |
| stable_stable | USDTUSDC.C | Coinbase | spot | 80 |  |
| stable_stable | TUSDUSD.A | Binance | spot | 80 |  |
| stable_stable | DAIUSDT.K | Kraken | spot | 80 |  |
| stable_stable | USDEUSD.A | Binance | spot | 60 |  |
| stable_stable | USDEUSDT.K | Kraken | spot | 60 |  |
| stable_stable | sUSDEUSDT.6 | Bybit | spot | 60 |  |
| stable_fiat | USDTUSD.K | Kraken | spot | 100 |  |
| stable_fiat | USDCUSD.K | Kraken | spot | 100 |  |
| stable_fiat | USDTUSD.C | Coinbase | spot | 100 |  |
| stable_fiat | USDTUSD.F | Bitfinex | spot | 100 |  |
| stable_fiat | USDCUSD.F | Bitfinex | spot | 100 |  |
| stable_fiat | USDTUD.A | Binance | spot | 80 |  |
| stable_fiat | USDCUD.A | Binance | spot | 80 |  |
| stable_fiat | USDTEUR.K | Kraken | spot | 80 |  |
| stable_fiat | USDCEUR.K | Kraken | spot | 80 |  |
| stable_fiat | USDTEUR.C | Coinbase | spot | 80 |  |
| stable_fiat | USDCEUR.C | Coinbase | spot | 80 |  |

## excluded noisy exchanges
- Aster
- Gate.io
- Huobi
- Lighter
- Vertex
- WOO X
- Phemex
- Poloniex
- Luno

## ambiguous symbols
- BTCUSD.J / XBTUSDC mapping not present in selected set

## missing desired core markets
- none

## naming caveat
Naming caveat: Coinalyze symbols like FDUSDUSD.A may represent FDUSD/USDT. Use symbol_on_exchange/display_pair for human display.
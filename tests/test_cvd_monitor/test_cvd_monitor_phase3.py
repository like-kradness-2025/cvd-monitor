from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cvd_monitor.cli import main
from cvd_monitor.db import get_db_connection, init_db, save_cvd_features, save_raw_ohlcv_rows
from cvd_monitor.models import CvdFeatureRow, RawOhlcvRow
from cvd_monitor.renderer import render_cvd_chart
from cvd_monitor.market_registry import load_markets_config

BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = BASE_DIR / 'config' / 'universe.generated.yml'
CORE20_CONFIG_PATH = BASE_DIR / 'config' / 'universe.core20.yml'


def _market_key(symbol: str) -> str:
    markets = load_markets_config(CONFIG_PATH)
    for market in markets:
        if market.coinalyze_symbol == symbol:
            return market.market_key
    raise AssertionError(f'market not found: {symbol}')


def _market(symbol: str):
    markets = load_markets_config(CONFIG_PATH)
    for market in markets:
        if market.coinalyze_symbol == symbol:
            return market
    raise AssertionError(symbol)


def _seed_rows(db_path: Path, market_key: str, symbol: str, interval: str = '5min') -> None:
    rows = []
    raw_rows = []
    for idx, ts in enumerate((0, 300, 600, 900)):
        raw_rows.append(RawOhlcvRow(market_key, symbol, 'binance', symbol, 'spot', 'other', interval, ts, None, None, None, 100 + idx, 10, 6, 20, 12, 1))
        rows.append(CvdFeatureRow(market_key, symbol, interval, ts, 1.0, 2.0, float(idx), float(idx) * 2.0, None, None, None, None, 1))
    save_raw_ohlcv_rows(db_path, raw_rows)
    save_cvd_features(db_path, rows)


@pytest.fixture()
def prepared_db(tmp_path: Path) -> Path:
    db_path = tmp_path / 'cvd.sqlite'
    init_db(db_path)
    _seed_rows(db_path, _market_key('BTCUSD.C'), 'BTCUSD.C')
    _seed_rows(db_path, _market_key('BTCUSDT_PERP.A'), 'BTCUSDT_PERP.A')
    _seed_rows(db_path, _market_key('FDUSDUSD.A'), 'FDUSDUSD.A')
    _seed_rows(db_path, _market_key('USDTUSD.K'), 'USDTUSD.K')
    return db_path


def test_render_cvd_chart_creates_png_and_uses_display_pair(tmp_path: Path, prepared_db: Path) -> None:
    output = tmp_path / 'out' / 'cvd_monitor.png'
    result = render_cvd_chart(
        db_path=prepared_db,
        universe_config_path=CONFIG_PATH,
        interval='5min',
        window_hours=6,
        output=output,
        symbols='BTCUSD.C,BTCUSD.A,BTCUSDT_PERP.A,FDUSDUSD.A,USDTUSD.K',
    )
    assert output.exists() and output.stat().st_size > 0
    assert 'coinbase:btcusd.c' in result.selected_markets
    assert 'binance:btcusd.a' in result.selected_markets
    assert result.btc_price_market == 'coinbase:btcusd.c'
    assert result.unresolved_symbols == []


def test_render_skips_missing_rows_and_reports_unresolved(tmp_path: Path, prepared_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / 'smoke.png'
    missing_symbol = 'DOESNOTEXIST.X'
    result = render_cvd_chart(
        db_path=prepared_db,
        universe_config_path=CONFIG_PATH,
        interval='5min',
        window_hours=6,
        output=output,
        symbols=f'BTCUSD.C,{missing_symbol},FDUSDUSD.A',
    )
    assert missing_symbol in result.unresolved_symbols
    assert output.exists()


def test_render_cli_command(tmp_path: Path, prepared_db: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / 'cli.png'
    monkeypatch.setenv('DB_PATH', str(prepared_db))
    monkeypatch.setenv('MARKETS_CONFIG_PATH', str(CONFIG_PATH))
    monkeypatch.chdir(BASE_DIR)
    monkeypatch.setattr(sys, 'argv', ['cvd_monitor', 'render', '--interval', '5min', '--window-hours', '6', '--universe', str(BASE_DIR / 'config' / 'universe.core20.yml'), '--symbols', 'BTCUSD.C,BTCUSD.A,BTCUSDT_PERP.A,FDUSDUSD.A,USDTUSD.K', '--output', str(output)])
    assert main() == 0
    captured = capsys.readouterr().out
    assert output.exists() and output.stat().st_size > 0
    assert 'rendered=' in captured
    assert 'selected=' in captured
    assert 'with_features=' in captured
    assert 'plotted=' in captured
    assert 'omitted_crowding=' in captured
    assert 'skipped_no_features=' in captured
    assert 'skipped_no_cvd=' in captured
    assert 'unresolved=' in captured
    assert 'btc_price_market=' in captured
    assert 'panel_plot_map=' in captured
    assert 'panel_omitted_map=' in captured



def _seed_core20_rows(db_path: Path) -> None:
    for market in load_markets_config(CORE20_CONFIG_PATH):
        if market.enabled:
            _seed_rows(db_path, market.market_key, market.coinalyze_symbol)


def test_core20_all_eligible_series_are_plotted(tmp_path: Path) -> None:
    db_path = tmp_path / 'core20.sqlite'
    init_db(db_path)
    _seed_core20_rows(db_path)

    output = tmp_path / 'core20_all.png'
    result = render_cvd_chart(
        db_path=db_path,
        universe_config_path=CORE20_CONFIG_PATH,
        interval='5min',
        window_hours=6,
        output=output,
    )

    assert output.exists() and output.stat().st_size > 0
    assert result.selected_markets_count == 21
    assert result.markets_with_feature_rows_count == 21
    assert result.btc_price_market == 'coinbase:btcusd.c'
    assert result.plotted_series_count == 22
    assert result.omitted_for_crowding_count == 0
    assert result.skipped_no_feature_rows_count == 0
    assert result.skipped_no_usable_cvd_values_count == 0
    assert result.panel_omitted_map == {}
    assert len(result.panel_plot_map['Spot CVD cumulative delta']) == 7
    assert len(result.panel_plot_map['Futures CVD cumulative delta']) == 8
    assert len(result.panel_plot_map['Stable CVD cumulative delta']) == 6
    assert set(result.panel_plot_map['Stable CVD cumulative delta']) == {'FDUSDUSD.A', 'USDCUSD.A', 'USDTUSD.K', 'USDCUSD.K', 'USDTUSD.F', 'USDCUSD.C'}
    assert 'BTCUSD.C' in result.panel_plot_map['Spot CVD cumulative delta']
    assert 'BTC-PERPETUAL.2' in result.panel_plot_map['Futures CVD cumulative delta']


def test_line_color_matches_only_same_exchange_same_pair() -> None:
    from cvd_monitor.models import MarketConfig
    from cvd_monitor.renderer import _color_for_market_pair

    def market(exchange: str, pair: str, market_type: str) -> MarketConfig:
        base, quote = pair.split('/')
        return MarketConfig(
            market_key=f'{exchange}:{pair.replace("/", "").lower()}:{market_type}',
            exchange=exchange,
            coinalyze_symbol=f'{base}{quote}.{exchange[:1].upper()}',
            symbol=pair,
            symbol_on_exchange=pair.replace('/', ''),
            display_pair=pair,
            market_type=market_type,
            base_symbol=base,
            quote_symbol=quote,
            category='btc_stable',
            priority=1,
            enabled=True,
        )

    binance_spot = market('binance', 'BTC/USDT', 'spot')
    binance_future = market('binance', 'BTC/USDT', 'future')
    okx_future = market('okx', 'BTC/USDT', 'future')
    binance_usdc = market('binance', 'BTC/USDC', 'future')

    assert _color_for_market_pair(binance_spot) == _color_for_market_pair(binance_future)
    assert _color_for_market_pair(binance_spot) != _color_for_market_pair(okx_future)
    assert _color_for_market_pair(binance_spot) != _color_for_market_pair(binance_usdc)



def test_render_supports_longer_cumulative_context_than_visible_window(tmp_path: Path) -> None:
    db_path = tmp_path / 'rolling.sqlite'
    init_db(db_path)
    market = _market('BTCUSD.C')
    # 30 hours of 5m rows. Visible window is 24h, cumulative context is 30h.
    raw_rows = []
    feature_rows = []
    for idx in range(361):
        ts = idx * 300
        raw_rows.append(RawOhlcvRow(market.market_key, market.coinalyze_symbol, market.exchange, market.symbol_on_exchange, market.market_type, market.category, '5min', ts, None, None, None, 100 + idx, 10, 6, 20, 12, 1))
        feature_rows.append(CvdFeatureRow(market.market_key, market.coinalyze_symbol, '5min', ts, 1.0, 2.0, float(idx), float(idx) * 2.0, None, None, None, None, 1))
    save_raw_ohlcv_rows(db_path, raw_rows)
    save_cvd_features(db_path, feature_rows)
    output = tmp_path / 'rolling.png'
    result = render_cvd_chart(
        db_path=db_path,
        universe_config_path=CONFIG_PATH,
        interval='5min',
        window_hours=24,
        cumulative_hours=30,
        output=output,
        symbols='BTCUSD.C',
    )
    assert output.exists() and output.stat().st_size > 0
    assert result.plotted_series_count == 2


def test_coinbase_usdcusd_is_in_universe() -> None:
    markets = load_markets_config(CORE20_CONFIG_PATH)
    symbols = {m.coinalyze_symbol: m for m in markets}
    assert 'USDCUSD.C' in symbols
    assert symbols['USDCUSD.C'].exchange == 'coinbase'
    assert symbols['USDCUSD.C'].display_pair == 'USDC/USD'

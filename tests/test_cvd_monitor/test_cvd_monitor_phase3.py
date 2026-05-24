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
    assert result.selected_markets_count == 20
    assert result.markets_with_feature_rows_count == 20
    assert result.btc_price_market == 'coinbase:btcusd.c'
    assert result.plotted_series_count == 21
    assert result.omitted_for_crowding_count == 0
    assert result.skipped_no_feature_rows_count == 0
    assert result.skipped_no_usable_cvd_values_count == 0
    assert result.panel_omitted_map == {}
    assert len(result.panel_plot_map['BTC Spot/Perp CVD']) == 15
    assert len(result.panel_plot_map['Stable/Stable CVD']) == 2
    assert len(result.panel_plot_map['Stable/Fiat CVD']) == 3
    assert set(result.panel_plot_map['Stable/Stable CVD']) == {'FDUSDUSD.A', 'USDCUSD.A'}
    assert set(result.panel_plot_map['Stable/Fiat CVD']) == {'USDTUSD.K', 'USDCUSD.K', 'USDTUSD.F'}
    assert 'BTCUSD.C' in result.panel_plot_map['BTC Spot/Perp CVD']
    assert 'BTC-PERPETUAL.2' in result.panel_plot_map['BTC Spot/Perp CVD']

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.axes import Axes

from .constants import CANDLE_CUTOFF_SECONDS
from .db import get_db_connection
from .exceptions import ConfigError
from .market_registry import load_markets_config
from .models import MarketConfig

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class RenderResult:
    output_path: Path
    selected_markets: list[str]
    skipped_markets: list[str]
    unresolved_symbols: list[str]
    omitted_for_crowding: list[str]
    skipped_no_feature_rows: list[str]
    skipped_no_usable_cvd_values: list[str]
    btc_price_market: str | None
    selected_markets_count: int
    markets_with_feature_rows_count: int
    plotted_series_count: int
    omitted_for_crowding_count: int
    skipped_no_feature_rows_count: int
    skipped_no_usable_cvd_values_count: int
    unresolved_symbols_count: int
    panel_plot_map: dict[str, list[str]]
    panel_omitted_map: dict[str, list[str]]


def _priority_key(market: MarketConfig) -> tuple[int, str]:
    return (market.priority, market.market_key)


def _load_markets(universe_config_path: Path) -> list[MarketConfig]:
    return [m for m in load_markets_config(universe_config_path) if m.enabled]


def _lookup_values(market: MarketConfig) -> list[str]:
    values = [market.coinalyze_symbol, market.market_key, market.symbol_on_exchange]
    return [v.strip().upper() for v in values if v and v.strip()]


def resolve_selected_markets(markets: list[MarketConfig], symbols: str | None, limit: int | None) -> tuple[list[MarketConfig], list[str]]:
    requested = [s.strip().upper() for s in symbols.split(',') if s.strip()] if symbols else []
    unresolved: list[str] = []
    if requested:
        chosen: list[MarketConfig] = []
        seen: set[str] = set()
        for token in requested:
            candidates = [m for m in markets if token in _lookup_values(m)]
            if not candidates:
                unresolved.append(token)
                continue
            market = sorted(candidates, key=_priority_key)[0]
            if market.market_key not in seen:
                chosen.append(market)
                seen.add(market.market_key)
        selected = chosen
    else:
        selected = sorted(markets, key=_priority_key)
    if limit is not None:
        selected = selected[:limit]
    return selected, unresolved


def _utc_dt(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _series_name(market: MarketConfig) -> str:
    return f'{market.exchange} {market.display_pair}'


def _style_axis(ax: Axes) -> None:
    ax.set_facecolor('#0f172a')
    ax.grid(True, color='#334155', alpha=0.35, linewidth=0.8)
    ax.tick_params(colors='#cbd5e1', labelsize=8)
    for spine in ax.spines.values():
        spine.set_color('#475569')


def _fetch_feature_rows(conn: sqlite3.Connection, market_key: str, interval: str, start_ts: int, end_ts: int) -> list[sqlite3.Row]:
    return list(conn.execute(
        'SELECT market_key, ts, cvd, cvd_quote FROM cvd_features WHERE market_key = ? AND interval = ? AND ts BETWEEN ? AND ? AND ts <= ? ORDER BY ts ASC',
        (market_key, interval, start_ts, end_ts, end_ts - CANDLE_CUTOFF_SECONDS),
    ))


def _fetch_price_rows(conn: sqlite3.Connection, market_key: str, interval: str, start_ts: int, end_ts: int) -> list[sqlite3.Row]:
    return list(conn.execute(
        'SELECT ts, close FROM ohlcv_raw WHERE market_key = ? AND interval = ? AND ts BETWEEN ? AND ? AND close IS NOT NULL ORDER BY ts ASC',
        (market_key, interval, start_ts, end_ts),
    ))


def _has_usable_price(conn: sqlite3.Connection, market_key: str, interval: str, start_ts: int, end_ts: int) -> bool:
    row = conn.execute(
        'SELECT 1 FROM ohlcv_raw WHERE market_key = ? AND interval = ? AND ts BETWEEN ? AND ? AND close IS NOT NULL LIMIT 1',
        (market_key, interval, start_ts, end_ts),
    ).fetchone()
    return row is not None


def _extract_values(rows: list[sqlite3.Row]) -> tuple[list[datetime], list[float]]:
    times: list[datetime] = []
    values: list[float] = []
    for row in rows:
        value = row['cvd_quote'] if row['cvd_quote'] is not None else row['cvd']
        if value is None:
            continue
        times.append(_utc_dt(int(row['ts'])))
        values.append(float(value))
    return times, values


def _select_cvd_series(conn: sqlite3.Connection, markets: list[MarketConfig], interval: str, start_ts: int, end_ts: int) -> tuple[list[MarketConfig], list[str], list[str], list[str]]:
    available: list[MarketConfig] = []
    skipped_no_feature_rows: list[str] = []
    skipped_no_usable_cvd_values: list[str] = []
    for market in sorted(markets, key=_priority_key):
        rows = _fetch_feature_rows(conn, market.market_key, interval, start_ts, end_ts)
        if not rows:
            skipped_no_feature_rows.append(f'{market.coinalyze_symbol} ({market.market_key}: no feature rows)')
            continue
        if not any((r['cvd_quote'] is not None or r['cvd'] is not None) for r in rows):
            skipped_no_usable_cvd_values.append(f'{market.coinalyze_symbol} ({market.market_key}: no usable cvd values)')
            continue
        available.append(market)
    # Stage 6C all-series mode: do not truncate for panel crowding.
    return available, skipped_no_feature_rows, skipped_no_usable_cvd_values, []


def _select_btc_price_market(conn: sqlite3.Connection, markets: list[MarketConfig], interval: str, start_ts: int, end_ts: int) -> MarketConfig | None:
    btc_markets = [m for m in markets if m.base_symbol == 'BTC']
    explicit_order = ['BTCUSD.C', 'BTCUSD.A', 'BTCUSDT_PERP.A']
    for symbol in explicit_order:
        for market in btc_markets:
            if market.coinalyze_symbol == symbol and _has_usable_price(conn, market.market_key, interval, start_ts, end_ts):
                return market
    for market in sorted([m for m in btc_markets if m.market_type == 'spot'], key=_priority_key):
        if _has_usable_price(conn, market.market_key, interval, start_ts, end_ts):
            return market
    for market in sorted([m for m in btc_markets if m.market_type == 'future'], key=_priority_key):
        if _has_usable_price(conn, market.market_key, interval, start_ts, end_ts):
            return market
    return None


def _legend_columns(series_count: int) -> int:
    if series_count <= 3:
        return 1
    if series_count <= 8:
        return 2
    return 3


def render_cvd_chart(db_path: Path, universe_config_path: Path, interval: str, window_hours: int, output: Path, symbols: str | None = None, limit: int | None = None) -> RenderResult:
    if not universe_config_path.exists():
        raise ConfigError(f'Missing universe config: {universe_config_path}')

    markets = _load_markets(universe_config_path)
    selected, unresolved = resolve_selected_markets(markets, symbols, limit)
    if not selected:
        raise ValueError('No selected markets to render')

    with get_db_connection(db_path, read_only=True) as conn:
        placeholders = ','.join('?' for _ in selected)
        params = [interval, *[m.market_key for m in selected]]
        feature_max_ts = conn.execute(
            f'SELECT MAX(ts) FROM cvd_features WHERE interval = ? AND market_key IN ({placeholders})',
            params,
        ).fetchone()[0]
        end_ts = int(feature_max_ts) if feature_max_ts is not None else int(datetime.now(timezone.utc).timestamp())
        start_ts = end_ts - int(window_hours * 3600)

        skipped_markets: list[str] = []
        selected_rows: dict[str, list[sqlite3.Row]] = {}
        for market in selected:
            rows = _fetch_feature_rows(conn, market.market_key, interval, start_ts, end_ts)
            selected_rows[market.market_key] = rows
            if not rows:
                skipped_markets.append(f'{market.market_key} (no feature rows)')

        fig = plt.figure(figsize=(18, 14), facecolor='#020617')
        axes = [fig.add_subplot(4, 1, i + 1) for i in range(4)]
        for ax in axes:
            _style_axis(ax)

        # Panel 1: BTC price
        price_market = _select_btc_price_market(conn, markets, interval, start_ts, end_ts)

        ax = axes[0]
        ax.set_title('BTC Price', color='white', fontsize=11, loc='left')
        if price_market is None:
            ax.text(0.5, 0.5, 'No usable BTC price series in window', transform=ax.transAxes, ha='center', va='center', color='#cbd5e1')
        else:
            price_rows = _fetch_price_rows(conn, price_market.market_key, interval, start_ts, end_ts)
            times = mdates.date2num([_utc_dt(int(r['ts'])) for r in price_rows])
            closes = [float(r['close']) for r in price_rows]
            ax.plot(times, closes, color='#fbbf24', linewidth=1.8, label=_series_name(price_market))
            ax.legend(loc='upper left', fontsize=8, frameon=False)
            ax.set_ylabel('Price', color='#cbd5e1')

        panel_defs = [
            ('BTC Spot/Perp CVD', [m for m in selected if m.base_symbol == 'BTC' and m.market_type in {'spot', 'future'}]),
            ('Stable/Stable CVD', [m for m in selected if m.category == 'stable_stable']),
            ('Stable/Fiat CVD', [m for m in selected if m.category == 'stable_fiat']),
        ]
        all_omitted_for_crowding: list[str] = []
        all_skipped_no_feature_rows: list[str] = []
        all_skipped_no_usable_cvd_values: list[str] = []
        panel_plot_map: dict[str, list[str]] = {}
        panel_omitted_map: dict[str, list[str]] = {}
        plotted_cvd_series_count = 0
        palette = plt.get_cmap('tab20')
        linestyles = ['-', '--', '-.', ':']
        for idx, (title, candidates) in enumerate(panel_defs, start=1):
            ax = axes[idx]
            ax.set_title(title, color='white', fontsize=11, loc='left')
            series, skipped_no_feature_rows, skipped_no_usable_cvd_values, omitted_for_crowding = _select_cvd_series(conn, candidates, interval, start_ts, end_ts)
            all_skipped_no_feature_rows.extend(skipped_no_feature_rows)
            all_skipped_no_usable_cvd_values.extend(skipped_no_usable_cvd_values)
            all_omitted_for_crowding.extend(omitted_for_crowding)
            omitted_for_panel = [*skipped_no_feature_rows, *skipped_no_usable_cvd_values, *omitted_for_crowding]
            if omitted_for_panel:
                panel_omitted_map[title] = omitted_for_panel
            panel_plot_map[title] = []
            for series_idx, market in enumerate(series):
                rows = selected_rows.get(market.market_key) or _fetch_feature_rows(conn, market.market_key, interval, start_ts, end_ts)
                times, values = _extract_values(rows)
                if times:
                    plotted_cvd_series_count += 1
                    panel_plot_map[title].append(market.coinalyze_symbol)
                    ax.plot(
                        mdates.date2num(times),
                        values,
                        color=palette(series_idx % palette.N),
                        linestyle=linestyles[(series_idx // palette.N) % len(linestyles)],
                        linewidth=1.0,
                        alpha=0.9,
                        label=_series_name(market),
                    )
            if panel_plot_map[title]:
                ax.legend(loc='upper left', fontsize=6, frameon=False, ncol=_legend_columns(len(panel_plot_map[title])))
            ax.set_ylabel('CVD', color='#cbd5e1')

        for ax in axes:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M', tz=timezone.utc))
            for label in ax.get_xticklabels():
                label.set_rotation(30)
                label.set_horizontalalignment('right')
        axes[-1].set_xlabel('UTC Time', color='#cbd5e1')

        fig.suptitle(f'CVD Monitor | interval={interval} | last {window_hours}h', color='white', fontsize=14)
        fig.text(0.01, 0.01, f'UTC range: {_utc_dt(start_ts).isoformat()} → {_utc_dt(end_ts).isoformat()}', color='#cbd5e1', fontsize=8)
        output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output, dpi=160, facecolor=fig.get_facecolor(), bbox_inches='tight')
        plt.close(fig)

    # Calculate actual metrics
    has_btc_price = price_market is not None
    plotted_series_count = (1 if has_btc_price else 0) + plotted_cvd_series_count
    markets_with_feature_rows_count = len(selected) - len(skipped_markets)
    
    LOGGER.info(
        'rendered %s selected=%s unresolved=%s skipped=%s btc_price=%s plotted=%d',
        output,
        [m.market_key for m in selected],
        unresolved,
        skipped_markets,
        price_market.market_key if price_market else None,
        plotted_series_count,
    )
    return RenderResult(
        output_path=output,
        selected_markets=[m.market_key for m in selected],
        skipped_markets=skipped_markets,
        unresolved_symbols=unresolved,
        omitted_for_crowding=all_omitted_for_crowding,
        skipped_no_feature_rows=all_skipped_no_feature_rows,
        skipped_no_usable_cvd_values=all_skipped_no_usable_cvd_values,
        btc_price_market=price_market.market_key if price_market else None,
        selected_markets_count=len(selected),
        markets_with_feature_rows_count=markets_with_feature_rows_count,
        plotted_series_count=plotted_series_count,
        omitted_for_crowding_count=len(all_omitted_for_crowding),
        skipped_no_feature_rows_count=len(all_skipped_no_feature_rows),
        skipped_no_usable_cvd_values_count=len(all_skipped_no_usable_cvd_values),
        unresolved_symbols_count=len(unresolved),
        panel_plot_map=panel_plot_map,
        panel_omitted_map=panel_omitted_map,
    )

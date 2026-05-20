from __future__ import annotations

import logging
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.transforms import blended_transform_factory

from .constants import CANDLE_CUTOFF_SECONDS
from .db import get_db_connection
from .exceptions import ConfigError
from .market_registry import load_markets_config
from .models import MarketConfig

LOGGER = logging.getLogger(__name__)

BG = '#020617'
PANEL_BG = '#0f172a'
GRID = '#334155'
TEXT = '#cbd5e1'
MUTED = '#94a3b8'
SPINE = '#475569'
BUY = '#ef4444'
SELL = '#38bdf8'
NEUTRAL = '#e2e8f0'
PRICE = '#fbbf24'

# Venue-pair colors. The key ignores only spot/future type.
# Example: Binance BTC/USDT spot and Binance BTC/USDT perp share one color,
# while OKX BTC/USDT remains a different line color.
VENUE_PAIR_COLORS = {
    'binance:BTC/USDT': '#f97316',
    'binance:BTC/USDC': '#22c55e',
    'binance:BTC/FDUSD': '#e879f9',
    'binance:BTC/USD': '#fb923c',
    'binance:FDUSD/USDT': '#facc15',
    'binance:USDC/USDT': '#2dd4bf',
    'coinbase:BTC/USD': '#60a5fa',
    'coinbase:USDC/USD': '#2563eb',
    'coinbase:USDT/USD': '#06b6d4',
    'coinbase:USDT/USDC': '#3b82f6',
    'kraken:BTC/USD': '#38bdf8',
    'kraken:BTC/USDT': '#14b8a6',
    'kraken:USDT/USD': '#a78bfa',
    'kraken:USDC/USD': '#fb7185',
    'bitfinex:BTC/USD': '#818cf8',
    'bitfinex:USDT/USD': '#c084fc',
    'okx:BTC/USDT': '#ef4444',
    'okx:BTC/USD': '#f43f5e',
    'bybit:BTC/USDT': '#84cc16',
    'hyperliquid:BTC/USD': '#93c5fd',
    'deribit:BTC/USD': '#f472b6',
}
FALLBACK_PAIR_PALETTE = [
    '#38bdf8', '#f472b6', '#84cc16', '#c084fc', '#fb923c',
    '#67e8f9', '#fda4af', '#bef264', '#93c5fd', '#fdba74',
    '#60a5fa', '#22c55e', '#e879f9', '#facc15', '#2dd4bf',
    '#a78bfa', '#fb7185', '#ef4444', '#14b8a6', '#818cf8',
]
ANOMALY_THRESHOLD = 3.0
TOP_EVENT_LIMIT = 10
EVENTS_PER_TIMESTAMP_LIMIT = 3
LATEST_BAR_LIMIT = 12
LAYOUT_VERSION = "phone_portrait_wide_label_margin_24h_rolling_cum_delta_v12_cleanroot"


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


@dataclass(slots=True)
class _DeltaSeries:
    panel_title: str
    market: MarketConfig
    times: list[datetime]
    deltas: list[float]
    zscores: list[float]


@dataclass(slots=True)
class _AnomalyEvent:
    time: datetime
    market_label: str
    panel_title: str
    zscore: float


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


def _compact_series_name(market: MarketConfig) -> str:
    # Human-readable fallback used in summaries and diagnostics.
    if market.market_type == 'future':
        return f'{market.exchange} perp'
    return f'{market.exchange} {market.display_pair}'


def _endpoint_label_name(market: MarketConfig) -> str:
    """Return a very short inline label for phone endpoint labels.

    Dense CVD bundles become unreadable if every endpoint uses the full
    exchange + pair string. The panel title already tells the user the group,
    so labels only need exchange and quote/contract hints.
    """

    exchange = {
        'binance': 'BN',
        'coinbase': 'CB',
        'kraken': 'KR',
        'bitfinex': 'BF',
        'okx': 'OKX',
        'bybit': 'BB',
        'hyperliquid': 'HL',
        'deribit': 'DB',
    }.get(market.exchange.lower(), market.exchange[:3].upper())

    base = market.base_symbol.upper()
    quote = market.quote_symbol.upper()
    if market.market_type == 'future':
        # BTC futures/perps: exchange + collateral/quote is enough inside the
        # futures panel, and avoids repeated long "BTC/USDT perp" strings.
        return f'{exchange} {quote}.P'
    if base == 'BTC':
        return f'{exchange} {quote}'
    return f'{exchange} {base}/{quote}'



def _venue_pair_color_key(market: MarketConfig) -> str:
    """Return the venue + pair identity used for line colors.

    This intentionally ignores only market_type. The same exchange and same
    BTC/stable pair should keep the same color across spot/futures panels, but
    the same pair on a different exchange should not be forced to share color.
    """

    return f'{market.exchange.lower()}:{market.base_symbol.upper()}/{market.quote_symbol.upper()}'


def _fallback_color_for_key(key: str) -> str:
    # Deterministic fallback without depending on Python's randomized hash().
    score = sum((i + 1) * ord(ch) for i, ch in enumerate(key))
    return FALLBACK_PAIR_PALETTE[score % len(FALLBACK_PAIR_PALETTE)]


def _color_for_market_pair(market: MarketConfig) -> str:
    key = _venue_pair_color_key(market)
    return VENUE_PAIR_COLORS.get(key, _fallback_color_for_key(key))


def _linestyle_for_market(market: MarketConfig) -> str:
    """Keep every CVD line solid; only color encodes pair identity."""

    return '-'


def _style_axis(ax: Axes) -> None:
    ax.set_facecolor(PANEL_BG)
    ax.grid(True, color=GRID, alpha=0.28, linewidth=0.8)
    # Mobile screenshots are usually visually scanned from the right edge.
    # Move y-axis ticks and the y-axis label to the right so the chart body is
    # not pinched by left-side labels.
    ax.yaxis.tick_right()
    ax.yaxis.set_label_position('right')
    ax.tick_params(
        axis='y',
        colors=TEXT,
        labelsize=8,
        right=True,
        labelright=True,
        left=False,
        labelleft=False,
        pad=4,
    )
    ax.tick_params(axis='x', colors=TEXT, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color(SPINE)
    ax.spines['left'].set_visible(False)


def _fetch_feature_rows(conn: sqlite3.Connection, market_key: str, interval: str, start_ts: int, end_ts: int) -> list[sqlite3.Row]:
    return list(conn.execute(
        'SELECT market_key, ts, delta, delta_quote, cvd, cvd_quote FROM cvd_features WHERE market_key = ? AND interval = ? AND ts BETWEEN ? AND ? AND ts <= ? ORDER BY ts ASC',
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


def _extract_delta_values(rows: list[sqlite3.Row]) -> tuple[list[datetime], list[float]]:
    """Extract per-candle CVD change values for anomaly rendering.

    Prefer stored delta_quote, then delta, then fallback to first-difference of CVD.
    The subsequent robust z-score is calculated per market, so large venues do
    not flatten smaller but abnormal markets.
    """

    times: list[datetime] = []
    values: list[float] = []
    prior_cvd_value: float | None = None
    for row in rows:
        value: float | None
        row_keys = row.keys()
        if 'delta_quote' in row_keys and row['delta_quote'] is not None:
            value = float(row['delta_quote'])
        elif 'delta' in row_keys and row['delta'] is not None:
            value = float(row['delta'])
        else:
            cvd_value = row['cvd_quote'] if row['cvd_quote'] is not None else row['cvd']
            if cvd_value is None:
                continue
            cvd_float = float(cvd_value)
            value = None if prior_cvd_value is None else cvd_float - prior_cvd_value
            prior_cvd_value = cvd_float
        if value is None or not math.isfinite(value):
            continue
        times.append(_utc_dt(int(row['ts'])))
        values.append(value)
    return times, values


def _robust_scale(values: list[float]) -> float:
    """Return a per-market robust scale for ΔCVD size normalization.

    We intentionally do not subtract the median here. Cumulative delta needs zero
    to remain meaningful: positive steps mean buyer-initiated dominance and
    negative steps mean seller-initiated dominance. The scale only prevents large
    venues from visually flattening small venues.
    """

    finite_values = [v for v in values if math.isfinite(v)]
    if not finite_values:
        return 0.0
    center = median(finite_values)
    deviations = [abs(v - center) for v in finite_values]
    mad = median(deviations)
    if mad > 1e-12:
        return 1.4826 * mad
    mean = sum(finite_values) / len(finite_values)
    variance = sum((v - mean) ** 2 for v in finite_values) / max(1, len(finite_values) - 1)
    std = math.sqrt(variance)
    if std > 1e-12:
        return std
    max_abs = max(abs(v) for v in finite_values)
    return max_abs if max_abs > 1e-12 else 0.0


def _cumulative_normalized_delta(values: list[float], step_clip_abs: float = 8.0) -> list[float]:
    """Convert per-candle ΔCVD into longer-context cumulative normalized delta.

    Formula: cumulative_sum(ΔCVD / robust_scale(ΔCVD)).
    The caller may calculate this over a longer rolling context window and then
    trim to the visible chart window. That keeps the latest 24h view readable
    without throwing away the preceding pressure state.
    """

    scale = _robust_scale(values)
    if scale <= 1e-12:
        return [0.0 for _ in values]
    out: list[float] = []
    running = 0.0
    for value in values:
        step = value / scale
        if math.isfinite(step):
            step = max(-step_clip_abs, min(step_clip_abs, step))
            running += step
        out.append(running)
    return out


def _select_cvd_series(conn: sqlite3.Connection, markets: list[MarketConfig], interval: str, start_ts: int, end_ts: int) -> tuple[list[MarketConfig], list[str], list[str], list[str]]:
    available: list[MarketConfig] = []
    skipped_no_feature_rows: list[str] = []
    skipped_no_usable_cvd_values: list[str] = []
    for market in sorted(markets, key=_priority_key):
        rows = _fetch_feature_rows(conn, market.market_key, interval, start_ts, end_ts)
        if not rows:
            skipped_no_feature_rows.append(f'{market.coinalyze_symbol} ({market.market_key}: no feature rows)')
            continue
        if not any((r['delta_quote'] is not None or r['delta'] is not None or r['cvd_quote'] is not None or r['cvd'] is not None) for r in rows):
            skipped_no_usable_cvd_values.append(f'{market.coinalyze_symbol} ({market.market_key}: no usable cvd values)')
            continue
        available.append(market)
    # All selected series are represented in the anomaly rail. We suppress normal candles, not markets.
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


def _build_delta_series(panel_title: str, market: MarketConfig, rows: list[sqlite3.Row], plot_start_ts: int) -> _DeltaSeries | None:
    """Build a longer-window cumulative ΔCVD series and trim to display window.

    The cumulative line is calculated from the cumulative/rolling window start,
    not from the visible chart's left edge.  This behaves more like a rolling
    VWAP context line: the chart shows the latest window, while the CVD state
    carries pressure accumulated before the left edge.
    """

    times, deltas = _extract_delta_values(rows)
    if not times:
        return None
    cumulative = _cumulative_normalized_delta(deltas)
    plot_start = _utc_dt(plot_start_ts)
    trimmed_times: list[datetime] = []
    trimmed_deltas: list[float] = []
    trimmed_cumulative: list[float] = []
    for t, delta, value in zip(times, deltas, cumulative, strict=False):
        if t >= plot_start:
            trimmed_times.append(t)
            trimmed_deltas.append(delta)
            trimmed_cumulative.append(value)
    if not trimmed_times:
        return None
    return _DeltaSeries(panel_title=panel_title, market=market, times=trimmed_times, deltas=trimmed_deltas, zscores=trimmed_cumulative)


def _merge_panel_pressure(series_list: list[_DeltaSeries]) -> dict[str, list[tuple[datetime, float]]]:
    by_panel: dict[str, dict[datetime, list[float]]] = {}
    for series in series_list:
        panel_bucket = by_panel.setdefault(series.panel_title, {})
        for t, z in zip(series.times, series.zscores, strict=False):
            if math.isfinite(z):
                panel_bucket.setdefault(t, []).append(z)
    merged: dict[str, list[tuple[datetime, float]]] = {}
    for panel, time_values in by_panel.items():
        points = []
        for t in sorted(time_values):
            values = time_values[t]
            if values:
                # Median avoids one wild exchange dominating the group pressure.
                points.append((t, median(values)))
        merged[panel] = points
    return merged


def _collect_anomaly_events(series_list: list[_DeltaSeries], threshold: float = ANOMALY_THRESHOLD) -> list[_AnomalyEvent]:
    events: list[_AnomalyEvent] = []
    for series in series_list:
        label = _compact_series_name(series.market)
        for t, z in zip(series.times, series.zscores, strict=False):
            if abs(z) >= threshold:
                events.append(_AnomalyEvent(time=t, market_label=label, panel_title=series.panel_title, zscore=z))
    return events


def _thin_events_by_timestamp(events: list[_AnomalyEvent], per_timestamp_limit: int = EVENTS_PER_TIMESTAMP_LIMIT) -> list[_AnomalyEvent]:
    """Keep only the strongest few events per candle for the main rail.

    This keeps the monitor readable. The raw event list is still used for counts
    and can be inspected by lowering the threshold or disabling this cap later.
    """

    by_time: dict[datetime, list[_AnomalyEvent]] = {}
    for event in events:
        by_time.setdefault(event.time, []).append(event)
    thinned: list[_AnomalyEvent] = []
    for t in sorted(by_time):
        thinned.extend(sorted(by_time[t], key=lambda e: abs(e.zscore), reverse=True)[:per_timestamp_limit])
    return thinned


def _event_sort_key(event: _AnomalyEvent) -> tuple[int, str, str, float]:
    panel_order = {
        'BTC Spot/Perp CVD': 0,
        'Stable/Stable CVD': 1,
        'Stable/Fiat CVD': 2,
    }.get(event.panel_title, 9)
    return (panel_order, event.market_label, event.time.isoformat(), -abs(event.zscore))


def _last_finite_y(values: list[float]) -> float | None:
    for value in reversed(values):
        if math.isfinite(value):
            return float(value)
    return None


def _spread_label_fractions(fractions: list[float], *, min_gap: float = 0.045, lower: float = 0.06, upper: float = 0.94) -> list[float]:
    """Spread endpoint label y-positions in axis-fraction space.

    Labels still track the latest line value, but dense clusters are nudged just
    enough to remain readable on smartphone screenshots.
    """

    if not fractions:
        return []
    if len(fractions) == 1:
        return [min(upper, max(lower, fractions[0]))]
    gap = min(min_gap, max(0.012, (upper - lower) / max(1, len(fractions) - 1)))
    out = [min(upper, max(lower, v)) for v in fractions]
    for i in range(1, len(out)):
        if out[i] < out[i - 1] + gap:
            out[i] = out[i - 1] + gap
    if out[-1] > upper:
        out[-1] = upper
        for i in range(len(out) - 2, -1, -1):
            if out[i] > out[i + 1] - gap:
                out[i] = out[i + 1] - gap
    if out[0] < lower:
        out[0] = lower
        for i in range(1, len(out)):
            if out[i] < out[i - 1] + gap:
                out[i] = out[i - 1] + gap
    return [min(upper, max(lower, v)) for v in out]


def _draw_endpoint_labels(
    ax: Axes,
    label_points: list[tuple[float, str, str]],
    *,
    fontsize: float = 6.0,
    x_fraction: float = 0.982,
    min_gap: float = 0.055,
) -> None:
    """Draw readable inline endpoint labels near the latest line value.

    The labels are intentionally short, collision-spread, and drawn with a
    compact dark background. This keeps the mapping visible without the old
    legend block covering the phone chart.
    """

    cleaned: list[tuple[float, str, str]] = [
        (float(y), label, color)
        for y, label, color in label_points
        if math.isfinite(float(y)) and label
    ]
    if not cleaned:
        return
    ymin, ymax = ax.get_ylim()
    if not math.isfinite(ymin) or not math.isfinite(ymax) or abs(ymax - ymin) <= 1e-12:
        return
    span = ymax - ymin
    ordered = sorted(cleaned, key=lambda item: item[0])
    raw_fractions = [(y - ymin) / span for y, _, _ in ordered]
    spread_fractions = _spread_label_fractions(raw_fractions, min_gap=min_gap, lower=0.08, upper=0.92)
    transform = blended_transform_factory(ax.transAxes, ax.transData)

    for frac, (raw_y, label, color) in zip(spread_fractions, ordered, strict=False):
        y = ymin + frac * span
        # Short leader tick: makes it clear the label belongs to the current
        # endpoint while avoiding a full legend box.
        ax.plot(
            [0.940, 0.955],
            [y, y],
            transform=transform,
            color=color,
            linewidth=1.15,
            alpha=0.95,
            solid_capstyle='round',
            zorder=8,
            clip_on=True,
        )
        ax.text(
            x_fraction,
            y,
            label,
            transform=transform,
            ha='right',
            va='center',
            fontsize=fontsize,
            color=color,
            zorder=9,
            clip_on=True,
            bbox={
                'facecolor': BG,
                'alpha': 0.86,
                'edgecolor': color,
                'linewidth': 0.28,
                'boxstyle': 'round,pad=0.13',
            },
        )

def _draw_price(ax: Axes, conn: sqlite3.Connection, price_market: MarketConfig | None, interval: str, start_ts: int, end_ts: int) -> None:
    ax.set_title('BTC price', color='white', fontsize=11, loc='left', pad=6)
    if price_market is None:
        ax.text(0.5, 0.5, 'No usable BTC price series in window', transform=ax.transAxes, ha='center', va='center', color=TEXT)
        return
    price_rows = _fetch_price_rows(conn, price_market.market_key, interval, start_ts, end_ts)
    times = mdates.date2num([_utc_dt(int(r['ts'])) for r in price_rows])
    closes = [float(r['close']) for r in price_rows]
    ax.plot(times, closes, color=PRICE, linewidth=2.2)
    label_points: list[tuple[float, str, str]] = []
    if closes:
        last = closes[-1]
        first = closes[0]
        change = ((last / first) - 1.0) * 100 if first else 0.0
        label_points.append((last, f'BTC {last:,.0f} {change:+.1f}%', PRICE))
    ax.set_ylabel('Price', color=TEXT)
    _draw_endpoint_labels(ax, label_points, fontsize=6.0, x_fraction=0.982, min_gap=0.06)


def _draw_delta_bundle(ax: Axes, title: str, series_list: list[_DeltaSeries]) -> None:
    """Draw cumulative ΔCVD lines with endpoint labels instead of a legend.

    The plotted value is cumulative ΔCVD over the configured rolling context
    window after per-market robust scale normalization. Labels sit beside the
    latest line value at the right edge so the color/name mapping is read
    directly on the line chart.
    """

    ax.set_title(title, color='white', fontsize=11, loc='left', pad=6)
    if not series_list:
        ax.text(0.5, 0.5, 'No usable cumulative ΔCVD series', transform=ax.transAxes, ha='center', va='center', color=TEXT)
        ax.set_ylabel('cum ΔCVD', color=TEXT)
        return

    ordered = sorted(series_list, key=lambda s: _priority_key(s.market))
    label_points: list[tuple[float, str, str]] = []
    for series in ordered:
        xs = mdates.date2num(series.times)
        ys = series.zscores
        color = _color_for_market_pair(series.market)
        line = ax.plot(
            xs,
            ys,
            color=color,
            linestyle=_linestyle_for_market(series.market),
            linewidth=1.45,
            alpha=0.94,
        )[0]
        last_y = _last_finite_y(ys)
        if last_y is not None:
            label_points.append((last_y, _endpoint_label_name(series.market), line.get_color()))

    ax.axhline(0, color=SPINE, linewidth=1.0)
    # Let matplotlib autoscale the cumulative drift. Fixed ±5 would hide the
    # exact accumulation the chart is now meant to show.
    ax.set_ylabel('cum ΔCVD', color=TEXT)
    _draw_endpoint_labels(ax, label_points, fontsize=6.0, x_fraction=0.982, min_gap=0.052)



def render_cvd_chart(db_path: Path, universe_config_path: Path, interval: str, window_hours: int, output: Path, symbols: str | None = None, limit: int | None = None, cumulative_hours: int | None = None) -> RenderResult:
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
        cumulative_window_hours = max(window_hours, int(cumulative_hours or 72))
        cumulative_start_ts = end_ts - int(cumulative_window_hours * 3600)

        skipped_markets: list[str] = []
        selected_rows: dict[str, list[sqlite3.Row]] = {}
        for market in selected:
            rows = _fetch_feature_rows(conn, market.market_key, interval, cumulative_start_ts, end_ts)
            selected_rows[market.market_key] = rows
            if not rows:
                skipped_markets.append(f'{market.market_key} (no feature rows)')

        panel_defs = [
            ('Spot CVD cumulative delta', [m for m in selected if m.base_symbol == 'BTC' and m.market_type == 'spot']),
            ('Futures CVD cumulative delta', [m for m in selected if m.base_symbol == 'BTC' and m.market_type == 'future']),
            ('Stable CVD cumulative delta', [m for m in selected if m.category in {'stable_stable', 'stable_fiat'}]),
        ]

        all_omitted_for_crowding: list[str] = []
        all_skipped_no_feature_rows: list[str] = []
        all_skipped_no_usable_cvd_values: list[str] = []
        panel_plot_map: dict[str, list[str]] = {}
        panel_omitted_map: dict[str, list[str]] = {}
        delta_series: list[_DeltaSeries] = []

        for title, candidates in panel_defs:
            series, skipped_no_feature_rows, skipped_no_usable_cvd_values, omitted_for_crowding = _select_cvd_series(conn, candidates, interval, cumulative_start_ts, end_ts)
            all_skipped_no_feature_rows.extend(skipped_no_feature_rows)
            all_skipped_no_usable_cvd_values.extend(skipped_no_usable_cvd_values)
            all_omitted_for_crowding.extend(omitted_for_crowding)
            omitted_for_panel = [*skipped_no_feature_rows, *skipped_no_usable_cvd_values, *omitted_for_crowding]
            if omitted_for_panel:
                panel_omitted_map[title] = omitted_for_panel
            panel_plot_map[title] = []
            for market in series:
                rows = selected_rows.get(market.market_key) or _fetch_feature_rows(conn, market.market_key, interval, cumulative_start_ts, end_ts)
                item = _build_delta_series(title, market, rows, start_ts)
                if item is not None:
                    panel_plot_map[title].append(market.coinalyze_symbol)
                    delta_series.append(item)

        price_market = _select_btc_price_market(conn, markets, interval, start_ts, end_ts)
        series_by_panel = {title: [s for s in delta_series if s.panel_title == title] for title, _ in panel_defs}

        # Smartphone-first wide compact portrait canvas. 7.111111 x 10.666667 at 180 dpi = 1280 x 1920 px.
        # This keeps the 4-panel mobile layout while giving time-series lines more horizontal room.
        fig, axes = plt.subplots(
            4,
            1,
            figsize=(7.11112, 10.666667),
            facecolor=BG,
            sharex=True,
            gridspec_kw={'height_ratios': [0.82, 1.0, 1.0, 1.0], 'hspace': 0.24},
        )
        ax_price, ax_spot, ax_futures, ax_stable = axes
        for ax in axes:
            _style_axis(ax)

        _draw_price(ax_price, conn, price_market, interval, start_ts, end_ts)
        _draw_delta_bundle(ax_spot, 'Spot CVD cumulative delta | line bundle', series_by_panel.get('Spot CVD cumulative delta', []))
        _draw_delta_bundle(ax_futures, 'Futures CVD cumulative delta | line bundle', series_by_panel.get('Futures CVD cumulative delta', []))
        _draw_delta_bundle(ax_stable, 'Stable CVD cumulative delta | line bundle', series_by_panel.get('Stable CVD cumulative delta', []))

        right_pad_seconds = max(900, int((end_ts - start_ts) * 0.08))
        padded_end_ts = end_ts + right_pad_seconds
        latest_x = mdates.date2num(_utc_dt(end_ts))
        for ax in axes:
            ax.set_xlim(mdates.date2num(_utc_dt(start_ts)), mdates.date2num(_utc_dt(padded_end_ts)))
            ax.axvline(latest_x, color=SPINE, linewidth=0.75, alpha=0.55, linestyle=':')
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=timezone.utc))
            for label in ax.get_xticklabels():
                label.set_rotation(0)
                label.set_horizontalalignment('center')
        ax_stable.set_xlabel('UTC time', color=TEXT)

        fig.suptitle(f'CVD Monitor | {interval} | last {window_hours}h | rolling {cumulative_window_hours}h cum ΔCVD | venue-pair color mapping', color='white', fontsize=11, y=0.985)
        fig.text(0.03, 0.02, f'UTC: {_utc_dt(start_ts).strftime("%m-%d %H:%M")} → {_utc_dt(end_ts).strftime("%m-%d %H:%M")} | right blank margin is label space | same exchange+pair color across spot/perp', color=MUTED, fontsize=6.5)
        fig.subplots_adjust(left=0.035, right=0.925, top=0.925, bottom=0.065)
        output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output, dpi=180, facecolor=fig.get_facecolor())
        plt.close(fig)

    has_btc_price = price_market is not None
    plotted_cvd_series_count = len(delta_series)
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

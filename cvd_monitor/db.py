from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import CvdFeatureRow, MarketConfig, OhlcvBar, RawOhlcvRow
from .market_registry import load_markets_config

UTC = timezone.utc


def get_db_connection(db_path: Path, read_only: bool = False) -> sqlite3.Connection:
    if read_only:
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    else:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if not read_only:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
    conn.execute('PRAGMA busy_timeout=5000')
    return conn


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with get_db_connection(db_path) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS ohlcv_raw (market_key TEXT NOT NULL, symbol TEXT NOT NULL, exchange TEXT NOT NULL, symbol_on_exchange TEXT NOT NULL, market_type TEXT NOT NULL, category TEXT NOT NULL, interval TEXT NOT NULL, ts INTEGER NOT NULL, open REAL, high REAL, low REAL, close REAL, volume REAL, buy_volume REAL, tx INTEGER, buy_tx INTEGER, fetched_at INTEGER NOT NULL, PRIMARY KEY(market_key, interval, ts))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS cvd_features (market_key TEXT NOT NULL, symbol TEXT NOT NULL, interval TEXT NOT NULL, ts INTEGER NOT NULL, delta REAL, delta_quote REAL, cvd REAL, cvd_quote REAL, buy_ratio REAL, buy_tx_ratio REAL, cvd_change_15m REAL, cvd_change_1h REAL, computed_at INTEGER NOT NULL, PRIMARY KEY(market_key, interval, ts))''')
        conn.commit()


def save_raw_ohlcv_rows(db_path: Path, rows: list[RawOhlcvRow]) -> None:
    if not rows:
        return
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        conn.executemany('''INSERT OR REPLACE INTO ohlcv_raw (market_key, symbol, exchange, symbol_on_exchange, market_type, category, interval, ts, open, high, low, close, volume, buy_volume, tx, buy_tx, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', [(r.market_key, r.symbol, r.exchange, r.symbol_on_exchange, r.market_type, r.category, r.interval, r.ts, r.open, r.high, r.low, r.close, r.volume, r.buy_volume, r.tx, r.buy_tx, r.fetched_at) for r in rows])
        conn.commit()


def save_cvd_features(db_path: Path, rows: list[CvdFeatureRow]) -> None:
    if not rows:
        return
    init_db(db_path)
    with get_db_connection(db_path) as conn:
        conn.executemany(
            '''INSERT OR REPLACE INTO cvd_features (market_key, symbol, interval, ts, delta, delta_quote, cvd, cvd_quote, buy_ratio, buy_tx_ratio, cvd_change_15m, cvd_change_1h, computed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            [(r.market_key, r.symbol, r.interval, r.ts, r.delta, r.delta_quote, r.cvd, r.cvd_quote, r.buy_ratio, r.buy_tx_ratio, r.cvd_change_15m, r.cvd_change_1h, r.computed_at) for r in rows],
        )
        conn.commit()


def load_cvd_feature_summary(db_path: Path) -> dict[str, object]:
    with get_db_connection(db_path, read_only=True) as conn:
        total = int(conn.execute('SELECT COUNT(*) FROM cvd_features').fetchone()[0])
        by_symbol = [(r[0], int(r[1])) for r in conn.execute('SELECT symbol, COUNT(*) FROM cvd_features GROUP BY symbol ORDER BY symbol')]
        by_market = [(r[0], int(r[1])) for r in conn.execute('SELECT market_key, COUNT(*) FROM cvd_features GROUP BY market_key ORDER BY market_key')]
        min_ts, max_ts, latest = conn.execute('SELECT MIN(ts), MAX(ts), MAX(computed_at) FROM cvd_features').fetchone()
    return {'total': total, 'by_symbol': by_symbol, 'by_market': by_market, 'min_ts': min_ts, 'max_ts': max_ts, 'latest_computed_at': latest}


def load_cvd_inspection_summary(db_path: Path, markets_config_path: Path, interval: str | None = None) -> dict[str, object]:
    markets = load_markets_config(markets_config_path)
    market_by_key = {market.market_key: market for market in markets}
    with get_db_connection(db_path, read_only=True) as conn:
        params: list[object] = []
        raw_where = '' if interval is None else 'WHERE interval = ?'
        if interval is not None:
            params.append(interval)

        raw_by_market = {r[0]: int(r[1]) for r in conn.execute(f'SELECT market_key, COUNT(*) FROM ohlcv_raw {raw_where} GROUP BY market_key ORDER BY market_key', params)}
        eligible_by_market = {r[0]: int(r[1]) for r in conn.execute(f'''SELECT market_key, COUNT(*) FROM ohlcv_raw {raw_where} {'AND' if raw_where else 'WHERE'} volume IS NOT NULL AND buy_volume IS NOT NULL AND close IS NOT NULL AND tx IS NOT NULL AND buy_tx IS NOT NULL GROUP BY market_key ORDER BY market_key''', params)}
        feature_params: list[object] = []
        feature_where = '' if interval is None else 'WHERE interval = ?'
        if interval is not None:
            feature_params.append(interval)
        feature_by_market = {r[0]: int(r[1]) for r in conn.execute(f'SELECT market_key, COUNT(*) FROM cvd_features {feature_where} GROUP BY market_key ORDER BY market_key', feature_params)}
        skipped_null_required_by_market = {r[0]: int(r[1]) for r in conn.execute(f'''SELECT market_key, COUNT(*) FROM ohlcv_raw {raw_where} {'AND' if raw_where else 'WHERE'} (volume IS NULL OR buy_volume IS NULL OR close IS NULL OR tx IS NULL OR buy_tx IS NULL) GROUP BY market_key ORDER BY market_key''', params)}

    markets_with_data = sorted(set(raw_by_market) | set(eligible_by_market) | set(feature_by_market) | set(skipped_null_required_by_market))
    per_market: list[dict[str, object]] = []
    for market_key in markets_with_data:
        market = market_by_key.get(market_key)
        per_market.append({
            'market_key': market_key,
            'coinalyze_symbol': market.coinalyze_symbol if market else None,
            'symbol_on_exchange': market.symbol_on_exchange if market else None,
            'display_pair': market.display_pair if market else None,
            'raw_rows': raw_by_market.get(market_key, 0),
            'eligible_rows': eligible_by_market.get(market_key, 0),
            'feature_rows': feature_by_market.get(market_key, 0),
            'skipped_rows': skipped_null_required_by_market.get(market_key, 0),
        })

    return {'per_market': per_market}

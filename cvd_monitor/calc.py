from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .constants import CANDLE_CUTOFF_SECONDS
from .db import save_cvd_features
from .models import CvdFeatureRow

UTC = timezone.utc


_INTERVAL_RE = re.compile(r'^(\d+)(min|m|h)$')


def interval_to_seconds(interval: str) -> int:
    m = _INTERVAL_RE.match(interval)
    if not m:
        raise ValueError(f'Unsupported interval: {interval}')
    n = int(m.group(1))
    unit = m.group(2)
    return n * 60 if unit in {'min', 'm'} else n * 3600


def compute_cvd_features(db_path: Path, interval: str, market_keys: list[str] | None = None, limit: int | None = None) -> dict[str, object]:
    from .db import get_db_connection, init_db

    init_db(db_path)
    selected: list[tuple[str, str]] = []
    with get_db_connection(db_path, read_only=True) as conn:
        base_sql = 'SELECT DISTINCT market_key, symbol FROM ohlcv_raw WHERE interval = ?'
        params: list[object] = [interval]
        if market_keys:
            wanted = [s.strip().lower() for s in market_keys if s and s.strip()]
            if wanted:
                placeholders = ','.join('?' for _ in wanted)
                base_sql += f' AND market_key IN ({placeholders})'
                params.extend(wanted)
        base_sql += ' ORDER BY market_key'
        for row in conn.execute(base_sql, params):
            selected.append((row['market_key'], row['symbol']))
    if limit is not None:
        selected = selected[:limit]
    if not selected:
        raise ValueError('No symbols remain after filtering')

    now = int(datetime.now(UTC).timestamp())
    rows_written = 0
    rows_skipped = 0
    rows_read = 0
    skipped_by_reason: dict[str, int] = {}
    feature_rows: list[CvdFeatureRow] = []
    with get_db_connection(db_path, read_only=True) as conn:
        for market_key, symbol in selected:
            rows = list(conn.execute(
                'SELECT market_key, symbol, interval, ts, close, volume, buy_volume, buy_tx, tx FROM ohlcv_raw WHERE market_key = ? AND interval = ? AND ts <= ? ORDER BY ts ASC',
                (market_key, interval, now - CANDLE_CUTOFF_SECONDS),
            ))
            cvd = 0.0
            cvd_quote = 0.0
            cvd_by_ts: dict[int, float] = {}
            for row in rows:
                rows_read += 1
                if any(row[k] is None for k in ('volume', 'buy_volume', 'close', 'tx', 'buy_tx')):
                    rows_skipped += 1
                    skipped_by_reason['null_required_fields'] = skipped_by_reason.get('null_required_fields', 0) + 1
                    continue
                volume = float(row['volume'])
                buy_volume = float(row['buy_volume'])
                close = float(row['close'])
                tx = float(row['tx'])
                buy_tx = float(row['buy_tx'])
                if volume == 0 or tx == 0:
                    buy_ratio = None if volume == 0 else buy_volume / volume
                    buy_tx_ratio = None if tx == 0 else buy_tx / tx
                else:
                    buy_ratio = buy_volume / volume
                    buy_tx_ratio = buy_tx / tx
                delta = 2 * buy_volume - volume
                delta_quote = delta * close
                cvd += delta
                cvd_quote += delta_quote
                prior_15 = cvd_by_ts.get(row['ts'] - 15 * 60)
                prior_1h = cvd_by_ts.get(row['ts'] - 60 * 60)
                feature_rows.append(CvdFeatureRow(market_key=row['market_key'], symbol=row['symbol'], interval=row['interval'], ts=row['ts'], delta=delta, delta_quote=delta_quote, cvd=cvd, cvd_quote=cvd_quote, buy_ratio=buy_ratio, buy_tx_ratio=buy_tx_ratio, cvd_change_15m=(cvd - prior_15) if prior_15 is not None else None, cvd_change_1h=(cvd - prior_1h) if prior_1h is not None else None, computed_at=now))
                cvd_by_ts[row['ts']] = cvd
    save_cvd_features(db_path, feature_rows)
    rows_written = len(feature_rows)
    return {
        'rows_read': rows_read,
        'rows_skipped': rows_skipped,
        'rows_written': rows_written,
        'symbols_processed': len(selected),
        'skipped_by_reason': skipped_by_reason,
    }

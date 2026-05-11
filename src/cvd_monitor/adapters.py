from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from . import parsers
from .storage import (
    CVDRecord,
    FundingRateRecord,
    LiquidationRecord,
    LongShortRatioRecord,
    OHLCVRecord,
    OpenInterestRecord,
)


@dataclass(frozen=True)
class ParsedOHLCVRecord:
    timestamp: int
    symbol: str
    exchange: str
    market_type: str | None
    interval: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None
    buy_volume: float | None
    sell_volume: float | None
    volume_delta: float | None
    fetched_at: int
    raw_json: dict[str, Any]


def ohlcv_parsed_from_point(point: dict[str, Any], *, symbol: str, exchange: str, market_type: str | None, interval: str, fetched_at: int) -> ParsedOHLCVRecord:
    parsed = parsers.parse_ohlcv_record(point, symbol=symbol, exchange=exchange, market_type=market_type, interval=interval, fetched_at=fetched_at)
    return ParsedOHLCVRecord(**parsed)


def ohlcv_db_record_from_parsed(record: ParsedOHLCVRecord) -> OHLCVRecord:
    return OHLCVRecord(timestamp=record.timestamp, symbol=record.symbol, exchange=record.exchange, market_type=record.market_type, interval=record.interval, open=record.open, high=record.high, low=record.low, close=record.close, volume=record.volume, buy_volume=record.buy_volume, sell_volume=record.sell_volume, volume_delta=record.volume_delta, fetched_at=record.fetched_at, raw_json=json.dumps(record.raw_json, ensure_ascii=False))


def cvd_db_record_from_parsed(record: ParsedOHLCVRecord, *, cumulative_cvd: float) -> CVDRecord:
    return CVDRecord(timestamp=record.timestamp, symbol=record.symbol, exchange=record.exchange, market_type=record.market_type, interval=record.interval, buy_volume=record.buy_volume, sell_volume=record.sell_volume, volume_delta=record.volume_delta, cumulative_cvd=cumulative_cvd, fetched_at=record.fetched_at, raw_json=json.dumps(record.raw_json, ensure_ascii=False))


def _metric_record(record_cls, point: dict[str, Any], *, field_name: str, field_value: Any, symbol: str, exchange: str, market_type: str | None, interval: str, fetched_at: int):
    timestamp = parsers.parse_timestamp(parsers.required_field(point, "t", field_name.replace("_", " ") + " point"))
    return record_cls(timestamp=timestamp, symbol=symbol, exchange=exchange, market_type=market_type, interval=parsers.normalize_interval(interval), **{field_name: field_value}, fetched_at=fetched_at, raw_json=json.dumps(point, ensure_ascii=False))


def open_interest_record_from_point(point: dict[str, Any], *, symbol: str, exchange: str, market_type: str | None, interval: str, fetched_at: int) -> OpenInterestRecord:
    return _metric_record(OpenInterestRecord, point, field_name="open_interest", field_value=parsers.transform_open_interest(point), symbol=symbol, exchange=exchange, market_type=market_type, interval=interval, fetched_at=fetched_at)


def funding_rate_record_from_point(point: dict[str, Any], *, symbol: str, exchange: str, market_type: str | None, interval: str, fetched_at: int) -> FundingRateRecord:
    return _metric_record(FundingRateRecord, point, field_name="funding_rate", field_value=parsers.transform_funding_rate(point), symbol=symbol, exchange=exchange, market_type=market_type, interval=interval, fetched_at=fetched_at)


def liquidation_record_from_point(point: dict[str, Any], *, symbol: str, exchange: str, market_type: str | None, interval: str, fetched_at: int) -> LiquidationRecord:
    timestamp = parsers.parse_timestamp(parsers.required_field(point, "t", "liquidation point"))
    long_liquidation, short_liquidation = parsers.transform_liquidation(point)
    return LiquidationRecord(timestamp=timestamp, symbol=symbol, exchange=exchange, market_type=market_type, interval=parsers.normalize_interval(interval), long_liquidation=long_liquidation, short_liquidation=short_liquidation, fetched_at=fetched_at, raw_json=json.dumps(point, ensure_ascii=False))


def long_short_ratio_record_from_point(point: dict[str, Any], *, symbol: str, exchange: str, market_type: str | None, interval: str, fetched_at: int) -> LongShortRatioRecord:
    return _metric_record(LongShortRatioRecord, point, field_name="long_short_ratio", field_value=parsers.transform_long_short_ratio(point), symbol=symbol, exchange=exchange, market_type=market_type, interval=interval, fetched_at=fetched_at)

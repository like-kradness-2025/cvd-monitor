from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .env import load_env

DEFAULT_SYMBOLS_FILE = "/home/weed420/.hermes/data/coinalyze/coinalyze-btc-selected-20-symbol-market-map.json"
DEFAULT_DB = "/home/weed420/.hermes/data/coinalyze/cvd-monitor-ohlcv-test.sqlite3"

_ENV_BOOL_TRUE = {"1", "true", "t", "yes", "y", "on"}
_ENV_BOOL_FALSE = {"0", "false", "f", "no", "n", "off"}


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in _ENV_BOOL_TRUE:
        return True
    if text in _ENV_BOOL_FALSE or text == "":
        return False
    raise ValueError(f"invalid boolean value: {value!r}")


def normalize_config_path(path: str, *, label: str) -> str:
    if path is None:
        raise ValueError(f"{label} path must not be empty")
    text = str(path).strip()
    if not text:
        raise ValueError(f"{label} path must not be empty")
    try:
        resolved = Path(text).expanduser()
        if not resolved.is_absolute():
            resolved = resolved.resolve()
        return str(resolved)
    except OSError as exc:
        raise ValueError(f"invalid {label} path {path!r}: {exc}") from exc


def _env_int(name: str, default: str) -> int:
    value = os.environ.get(name, default)
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"environment variable {name} must be an integer: {value!r}") from exc


def _env_float(name: str, default: str) -> float:
    value = os.environ.get(name, default)
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"environment variable {name} must be a number: {value!r}") from exc


@dataclass(frozen=True)
class DatabaseConfig:
    db_path: str = DEFAULT_DB

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        return cls(db_path=normalize_config_path(os.environ.get("CVD_MONITOR_DB", DEFAULT_DB), label="database"))


def parse_args() -> argparse.Namespace:
    load_env()
    db_cfg = DatabaseConfig.from_env()
    p = argparse.ArgumentParser()
    p.add_argument(
        "--symbols-file",
        default=normalize_config_path(os.environ.get("CVD_MONITOR_SYMBOLS_FILE", DEFAULT_SYMBOLS_FILE), label="symbols file"),
        type=lambda value: normalize_config_path(value, label="symbols file"),
    )
    p.add_argument(
        "--db",
        default=db_cfg.db_path,
        type=lambda value: normalize_config_path(value, label="database"),
    )
    p.add_argument("--interval", default=os.environ.get("CVD_MONITOR_INTERVAL", "1min"))
    p.add_argument("--hours", type=int, default=_env_int("CVD_MONITOR_HOURS", "1"))
    p.add_argument("--limit", type=int, default=_env_int("CVD_MONITOR_LIMIT", "20"))
    p.add_argument("--overlap-candles", type=int, default=_env_int("CVD_MONITOR_OVERLAP_CANDLES", "3"))
    p.add_argument("--sleep-seconds", type=float, default=_env_float("CVD_MONITOR_SLEEP_SECONDS", "8.0"))
    p.add_argument("--dry-run", action="store_true", default=_parse_bool(os.environ.get("CVD_MONITOR_DRY_RUN")))
    p.add_argument("--market-type", default=os.environ.get("CVD_MONITOR_MARKET_TYPE", "all"), choices=["spot", "future", "all"])
    p.add_argument("--max-retries", type=int, default=_env_int("CVD_MONITOR_MAX_RETRIES", "1"))
    p.add_argument("--max-retry-after-seconds", type=float, default=_env_float("CVD_MONITOR_MAX_RETRY_AFTER_SECONDS", "120.0"))
    p.add_argument("--min-retry-after-seconds", type=float, default=_env_float("CVD_MONITOR_MIN_RETRY_AFTER_SECONDS", "1.0"))
    p.add_argument("--max-consecutive-failures", type=int, default=_env_int("CVD_MONITOR_MAX_CONSECUTIVE_FAILURES", "3"))
    p.add_argument("--max-rate-limit-count", type=int, default=_env_int("CVD_MONITOR_MAX_RATE_LIMIT_COUNT", "2"))
    p.add_argument("--allow-partial-success", action="store_true", default=_parse_bool(os.environ.get("CVD_MONITOR_ALLOW_PARTIAL_SUCCESS")))
    return p.parse_args()


def _validate_symbol_entry(entry: Any, index: int) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise ValueError(f"symbols[{index}] must be an object")

    required_fields = {
        "symbol": str,
        "market_type": str,
        "interval": str,
    }
    for field, expected_type in required_fields.items():
        if field not in entry:
            raise ValueError(f"symbols[{index}]: missing required key '{field}'")
        value = entry[field]
        if not isinstance(value, expected_type):
            raise ValueError(
                f"symbols[{index}].{field} must be of type {expected_type.__name__}"
            )
        if not value.strip():
            raise ValueError(f"symbols[{index}].{field} must not be empty")

    exchange = entry.get("exchange") or entry.get("exchange_name") or entry.get("exchange_code")
    if not isinstance(exchange, str):
        raise ValueError(f"symbols[{index}]: missing required key 'exchange' (or exchange_name/exchange_code)")
    if not exchange.strip():
        raise ValueError(f"symbols[{index}].exchange must not be empty")

    normalized = dict(entry)
    normalized["exchange"] = exchange.strip()
    normalized["exchange_name"] = str(entry.get("exchange_name") or exchange).strip()
    normalized["exchange_code"] = str(entry.get("exchange_code") or exchange).strip()

    return normalized


def load_symbols(path: str, market_type: str) -> list[dict[str, Any]]:
    if market_type not in {"spot", "future", "all"}:
        raise ValueError(f"unsupported market_type: {market_type}")

    resolved_path = normalize_config_path(path, label="symbols file")
    try:
        with open(resolved_path, "r", encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON in symbols file {resolved_path}: {exc.msg}") from exc
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"symbols file not found: {resolved_path}") from exc
    except PermissionError as exc:
        raise PermissionError(f"cannot read symbols file {resolved_path}: permission denied") from exc
    except NotADirectoryError as exc:
        raise NotADirectoryError(f"symbols file path is not valid: {resolved_path}") from exc
    except OSError as exc:
        raise OSError(f"failed to read symbols file {resolved_path}: {exc}") from exc

    if not isinstance(data, list):
        raise ValueError(f"symbols file must contain a JSON array: {resolved_path}")

    validated = [_validate_symbol_entry(entry, index) for index, entry in enumerate(data)]
    if market_type != "all":
        validated = [x for x in validated if x.get("market_type") == market_type]
    return validated

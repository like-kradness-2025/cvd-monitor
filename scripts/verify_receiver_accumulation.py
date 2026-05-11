from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cvd_monitor.storage import connect_db, init_db


DEFAULT_DB = "/home/weed420/.hermes/data/coinalyze/cvd-monitor-ohlcv-test.sqlite3"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Verify that the receiver accumulates data over time.")
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--interval-seconds", type=float, default=60.0, help="Wait time between snapshots.")
    p.add_argument("--run-cmd", default="", help="Optional receiver command to run once between snapshots.")
    p.add_argument("--check-latest-only", action="store_true", help="Treat only latest timestamps advancing as sufficient when counts stay flat.")
    return p.parse_args()


def snapshot(db_path: str) -> dict[str, int | None]:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"db does not exist: {db_path}")
    conn = connect_db(db_path)
    try:
        init_db(conn)
        out: dict[str, int | None] = {}
        for table in ("ohlcv_history", "cvd_history", "ohlcv_fetch_state", "fetch_runs"):
            out[f"{table}_count"] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        out["ohlcv_history_max_ts"] = conn.execute("SELECT MAX(timestamp) FROM ohlcv_history").fetchone()[0]
        out["cvd_history_max_ts"] = conn.execute("SELECT MAX(timestamp) FROM cvd_history").fetchone()[0]
        out["fetch_state_max_updated_at"] = conn.execute("SELECT MAX(updated_at) FROM ohlcv_fetch_state").fetchone()[0]
        out["fetch_runs_max_finished_at"] = conn.execute("SELECT MAX(finished_at) FROM fetch_runs").fetchone()[0]
        return out
    finally:
        conn.close()


def fmt_delta(before: int | None, after: int | None) -> str:
    if before is None or after is None:
        return "n/a"
    return str(int(after) - int(before))


def main() -> int:
    args = parse_args()
    before = snapshot(args.db)
    print("before=" + json.dumps(before, sort_keys=True))

    if args.run_cmd:
        rc = subprocess.run(args.run_cmd, shell=True).returncode
        if rc != 0:
            print(f"run_cmd_failed rc={rc}", file=sys.stderr)
            return 2
    else:
        time.sleep(args.interval_seconds)

    after = snapshot(args.db)
    print("after=" + json.dumps(after, sort_keys=True))

    count_deltas = {
        k: int(after[k]) - int(before[k])
        for k in ("ohlcv_history_count", "cvd_history_count", "ohlcv_fetch_state_count", "fetch_runs_count")
    }
    latest_deltas = {
        k: fmt_delta(before[k], after[k])
        for k in ("ohlcv_history_max_ts", "cvd_history_max_ts", "fetch_state_max_updated_at", "fetch_runs_max_finished_at")
    }
    print("count_deltas=" + json.dumps(count_deltas, sort_keys=True))
    print("latest_deltas=" + json.dumps(latest_deltas, sort_keys=True))

    counts_grew = any(v > 0 for k, v in count_deltas.items() if k in ("ohlcv_history_count", "cvd_history_count"))
    latest_moved = any(after[k] is not None and before[k] is not None and int(after[k]) > int(before[k]) for k in ("ohlcv_history_max_ts", "cvd_history_max_ts"))
    if counts_grew or (args.check_latest_only and latest_moved):
        print("PASS: receiver is accumulating data over time")
        return 0

    print("FAIL: no table count growth or timestamp advancement observed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

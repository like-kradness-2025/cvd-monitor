#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"

interval_seconds="300"
if [[ ${1:-} == --interval-seconds ]]; then
  interval_seconds="${2:?missing interval seconds}"
  shift 2
elif [[ ${1:-} == --interval-seconds=* ]]; then
  interval_seconds="${1#--interval-seconds=}"
  shift 1
fi

if [[ -z ${interval_seconds} ]]; then
  echo "interval seconds is required" >&2
  exit 2
fi

if ! [[ ${interval_seconds} =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "invalid interval seconds: ${interval_seconds}" >&2
  exit 2
fi

cycle=0
while true; do
  cycle=$((cycle + 1))
  echo "[receiver-loop] cycle=${cycle} start $(date -Is)"
  if python -c 'from cvd_monitor.fetcher import main; raise SystemExit(main())' "$@"; then
    rc=0
  else
    rc=$?
  fi
  echo "[receiver-loop] cycle=${cycle} end rc=${rc} $(date -Is)"
  if (( rc != 0 )); then
    exit "${rc}"
  fi
  sleep "${interval_seconds}"
done

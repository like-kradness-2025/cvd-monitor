from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

_ENV_LOADED = False


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def load_env(*, candidates: Iterable[Path] | None = None) -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    if candidates is None:
        here = Path(__file__).resolve()
        candidates = (here.parent.parent / ".env", Path.cwd() / ".env")
    for candidate in candidates:
        _load_env_file(candidate)
    _ENV_LOADED = True

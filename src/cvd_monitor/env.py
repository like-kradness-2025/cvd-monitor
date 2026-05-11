from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


def _normalize_path(path: Path) -> Path:
    path = path.expanduser()
    return path if path.is_absolute() else path.resolve()


def _load_env_file(path: Path) -> None:
    path = _normalize_path(path)
    if path.is_dir():
        raise NotADirectoryError(f"environment file path points to a directory: {path}")

    try:
        if not path.exists():
            return
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    except PermissionError as exc:
        raise PermissionError(f"cannot read environment file {path}: permission denied") from exc
    except OSError as exc:
        raise OSError(f"failed to read environment file {path}: {exc}") from exc

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def load_env(*, candidates: Iterable[Path] | None = None) -> None:
    if candidates is None:
        here = Path(__file__).resolve()
        candidates = (here.parent.parent / ".env", Path.cwd() / ".env")
    for candidate in candidates:
        _load_env_file(candidate)

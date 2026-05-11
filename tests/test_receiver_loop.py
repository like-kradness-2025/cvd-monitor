from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TestReceiverLoopScript(unittest.TestCase):
    def _run_script(self, script_name: str, *, extra_args: list[str] | None = None) -> tuple[int, str, str, str, Path]:
        extra_args = extra_args or []
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            bin_dir = tmp / "bin"
            bin_dir.mkdir()
            log_file = tmp / "calls.log"

            python_stub = bin_dir / "python"
            python_stub.write_text(
                textwrap.dedent(
                    f"""\
                    #!/usr/bin/env bash
                    set -euo pipefail
                    printf 'python:%s\n' "$*" >> {log_file}
                    printf 'cwd:%s\n' "$PWD" >> {log_file}
                    printf 'py:%s\n' "${{PYTHONPATH:-}}" >> {log_file}
                    count_file={tmp / 'python_count'}
                    count=0
                    if [[ -f "$count_file" ]]; then
                      count=$(<"$count_file")
                    fi
                    count=$((count + 1))
                    printf '%s' "$count" > "$count_file"
                    if [[ "$count" -eq 1 ]]; then
                      exit 0
                    fi
                    exit 7
                    """
                ),
                encoding="utf-8",
            )
            python_stub.chmod(0o755)

            sleep_stub = bin_dir / "sleep"
            sleep_stub.write_text(
                textwrap.dedent(
                    f"""\
                    #!/usr/bin/env bash
                    set -euo pipefail
                    printf 'sleep:%s\n' "$*" >> {log_file}
                    exit 0
                    """
                ),
                encoding="utf-8",
            )
            sleep_stub.chmod(0o755)

            date_stub = bin_dir / "date"
            date_stub.write_text(
                textwrap.dedent(
                    f"""\
                    #!/usr/bin/env bash
                    set -euo pipefail
                    printf 'date:%s\n' "$*" >> {log_file}
                    echo '2026-01-01T00:00:00+00:00'
                    """
                ),
                encoding="utf-8",
            )
            date_stub.chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env['PATH']}"
            proc = subprocess.run(
                ["bash", str(ROOT / script_name), *extra_args],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
            )
            log = log_file.read_text(encoding="utf-8") if log_file.exists() else ""
            return proc.returncode, proc.stdout, proc.stderr, log, tmp

    def test_run_receiver_loop_forwards_args_and_sleeps_between_iterations(self) -> None:
        rc, _, _, log, _ = self._run_script(
            "run_receiver_loop.sh",
            extra_args=["--interval-seconds", "12", "--foo", "bar"],
        )
        self.assertEqual(rc, 7)
        self.assertIn("python:-c from cvd_monitor.fetcher import main; raise SystemExit(main()) --foo bar", log)
        self.assertIn(f"cwd:{ROOT}", log)
        self.assertIn(f"py:{ROOT / 'src'}", log)
        self.assertIn("sleep:12", log)
        self.assertEqual(log.count("python:"), 2)
        self.assertEqual(log.count("sleep:"), 1)

    def test_run_receiver_live_executes_fetcher_entrypoint(self) -> None:
        rc, _, _, log, _ = self._run_script("scripts/run_receiver_live.sh", extra_args=["--alpha", "1"])
        self.assertEqual(rc, 0)
        self.assertEqual(log.count("python:"), 1)
        self.assertIn("python:-c from cvd_monitor.fetcher import main; raise SystemExit(main()) --alpha 1", log)
        self.assertNotIn("sleep:", log)

    def test_run_receiver_loop_rejects_invalid_interval(self) -> None:
        rc, _, stderr, _, _ = self._run_script("run_receiver_loop.sh", extra_args=["--interval-seconds", "bad"])
        self.assertEqual(rc, 2)
        self.assertIn("invalid interval seconds: bad", stderr)


if __name__ == "__main__":
    unittest.main()

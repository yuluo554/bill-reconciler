"""编码守卫：非 UTF-8、非中文控制台的流被切到 UTF-8（plan/03 §八）。

判据刻意用**字节级**断言：子进程在 cp1252 环境下必须仍写出**合法 UTF-8**
（守卫生效），而不是任何"能跑就算过"的宽松检查。
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_raw(*args, env=None):
    full_env = dict(os.environ)
    full_env["PYTHONDONTWRITEBYTECODE"] = "1"
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "bill_reconciler"] + list(args),
        capture_output=True,
        cwd=str(REPO_ROOT),
        env=full_env,
    )


def test_cp1252_console_help_emits_valid_utf8():
    result = _run_raw("--help", env={"PYTHONIOENCODING": "cp1252"})
    assert result.returncode == 0
    text = result.stdout.decode("utf-8", errors="strict")  # 必须为合法 UTF-8
    assert "bill-reconciler" in text


def test_cp1252_console_selftest_emits_valid_utf8():
    result = _run_raw("selftest", env={"PYTHONIOENCODING": "cp1252"})
    assert result.returncode == 0
    text = result.stdout.decode("utf-8", errors="strict")
    assert "结论：" in text

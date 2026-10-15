"""测试公共夹具。

约定：

- 子进程测试统一走 ``run_cli`` 夹具：用 ``sys.executable -m bill_reconciler``、
  cwd=仓库根、显式 UTF-8 编码（不依赖本机 locale，"判据不随环境变"）。
- ``PYTHONIOENCODING`` 缺省固定为 utf-8 保证断言跨平台一致；
  编码守卫自身的测试会显式覆盖为 cp1252（见 test_encoding_guard.py）。
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def run_cli():
    def _run(*args, env=None, cwd=None):
        override = dict(env or {})
        full_env = dict(os.environ)
        full_env["PYTHONDONTWRITEBYTECODE"] = "1"
        if "PYTHONIOENCODING" not in override:
            full_env["PYTHONIOENCODING"] = "utf-8"
        full_env.update(override)
        return subprocess.run(
            [sys.executable, "-m", "bill_reconciler"] + list(args),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(cwd or REPO_ROOT),
            env=full_env,
        )

    return _run


@pytest.fixture()
def run_tools():
    """tools/ 生成器与守门脚本的子进程夹具（显式 UTF-8，cwd=仓库根）。"""

    def _run(*args, env=None):
        override = dict(env or {})
        full_env = dict(os.environ)
        full_env["PYTHONDONTWRITEBYTECODE"] = "1"
        if "PYTHONIOENCODING" not in override:
            full_env["PYTHONIOENCODING"] = "utf-8"
        full_env.update(override)
        return subprocess.run(
            [sys.executable, "-X", "utf8"] + list(args),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(REPO_ROOT),
            env=full_env,
        )

    return _run

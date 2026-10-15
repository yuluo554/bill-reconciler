"""占位命令契约（M0 骨架期）。

各功能的占位命令应：打印"尚未实现（计划于 Mx）"到 stderr、返回退出码 2。
**注意**：对应命令在里程碑实现后，这些期望按 plan/02 §4.5 的最终语义翻转
（把期望改掉是刻意的"期望变更"，不做静默放宽）。
"""

import pytest

from bill_reconciler.cli import main

STUB_COMMANDS = ["import", "normalize", "dedup", "classify", "report", "run", "bench"]


@pytest.mark.parametrize("command", STUB_COMMANDS)
def test_stub_prints_not_implemented_and_exits_2(command, capsys):
    code = main([command])
    captured = capsys.readouterr()  # 只能消费一次：先接住再分别断言
    assert code == 2
    assert "尚未实现" in captured.err
    assert command in captured.err


def test_stub_via_subprocess(run_cli):
    result = run_cli("dedup")
    assert result.returncode == 2
    assert "尚未实现" in result.stderr

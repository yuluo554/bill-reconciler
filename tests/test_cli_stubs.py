"""占位命令契约（M0 骨架期建立；M2/M3 两次翻转）。

各占位命令应：打印"尚未实现（计划于 Mx）"到 stderr、返回退出码 2。
**注意**：对应命令在里程碑实现后，这些期望按 plan/02 §4.5 的最终语义翻转
（把期望改掉是刻意的"期望变更"，不做静默放宽）。
**期望变更（M2，2026-10-15）**：``import`` 已实装（模块①）。
**期望变更（M3，2026-10-15）**：``normalize/dedup/classify/run`` 已实装
（模块②③④ + 编排），从占位清单移除；契约见 test_pipeline_cli.py；
占位余 report/bench（M4）。
"""

import pytest

from bill_reconciler.cli import main

STUB_COMMANDS = ["report", "bench"]


@pytest.mark.parametrize("command", STUB_COMMANDS)
def test_stub_prints_not_implemented_and_exits_2(command, capsys):
    code = main([command])
    captured = capsys.readouterr()  # 只能消费一次：先接住再分别断言
    assert code == 2
    assert "尚未实现" in captured.err
    assert command in captured.err


def test_stub_via_subprocess(run_cli):
    result = run_cli("bench")
    assert result.returncode == 2
    assert "尚未实现" in result.stderr

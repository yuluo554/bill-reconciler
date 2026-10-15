"""占位命令契约（M0 骨架期建立；M2/M3/M4 三次翻转）。

各占位命令应：打印"尚未实现（计划于 Mx）"到 stderr、返回退出码 2。
**注意**：对应命令在里程碑实现后，这些期望按 plan/02 §4.5 的最终语义翻转
（把期望改掉是刻意的"期望变更"，不做静默放宽）。
**期望变更（M2，2026-10-15）**：``import`` 已实装（模块①）。
**期望变更（M3，2026-10-15）**：``normalize/dedup/classify/run`` 已实装
（模块②③④ + 编排），从占位清单移除；契约见 test_pipeline_cli.py；
占位余 report/bench（M4）。
**期望变更（M4，2026-10-15）**：``report``/``bench`` 已实装（模块⑤ +
基准全套），占位清单清空；新契约见 test_report_cli.py / test_bench.py
（bench 退出码 0/1/2、report 与 run 同语义）。
"""

from bill_reconciler.cli import main

STUB_COMMANDS = []


def test_no_stubs_remain():
    """占位清单已清空：所有子命令均实装（M4 收口）。"""
    assert STUB_COMMANDS == []

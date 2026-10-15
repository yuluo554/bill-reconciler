"""安装面：metadata 版本与包版本一致；console script 声明齐备。

未安装通道（源码直跑）声明式跳过——由安装通道（editable）与 CI 实跑覆盖；
这是刻意的分工：源码态不装包也能测逻辑，安装面断言交给装好的环境。
"""

import pytest

import bill_reconciler


def _metadata_or_skip():
    try:
        from importlib import metadata
    except ImportError:  # pragma: no cover - 3.8+ 均可用
        pytest.skip("importlib.metadata 不可用")
    try:
        dist = metadata.distribution("bill-reconciler")
    except metadata.PackageNotFoundError:
        pytest.skip("当前通道未安装包（源码直跑）；安装通道（editable/CI）会执行本测试")
    return dist


def test_metadata_version_matches_package():
    dist = _metadata_or_skip()
    assert dist.version == bill_reconciler.__version__


def test_console_scripts_declared():
    dist = _metadata_or_skip()
    scripts = {ep.name for ep in dist.entry_points if ep.group == "console_scripts"}
    assert {"bill-reconciler", "brc"} <= scripts

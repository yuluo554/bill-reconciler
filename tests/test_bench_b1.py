"""内置基准骨架（M2 接入）：B1 候选实现 + 探活可证伪（正式全套在 M4）。

- B1 对账：真引擎 F1 = 1.0（77 行全命中）、门槛读规则包（门槛是数据）；
- 探活：注入坏引擎 → 基准必须报未达标（"全绿"必须能被证伪）；
- 门槛缺失 → 配置错误（exit 2 语义的 InputError）。
"""

import json

import pytest

from bill_reconciler.bench_runner import _load_frozen, _threshold, run_b1, run_suite_live_probe
from bill_reconciler.datadir import require_data_dir
from bill_reconciler.errors import InputError


def test_b1_full_hit_with_real_engine():
    result = run_b1()
    assert result["pass"] is True
    assert result["f1"] == 1.0
    assert result["mismatches"] == []
    assert result["total"] == 77  # 真值期望行数（分子=分母口径）


def test_b1_threshold_is_data_from_rules_package():
    _, manifest, _, _ = _load_frozen()
    result = run_b1()
    assert result["threshold"] == _threshold(manifest, "bench_b1_row_f1_min")


def test_b1_missing_threshold_is_config_error():
    _, manifest, truth, aliases = _load_frozen()
    stripped = json.loads(json.dumps(manifest))
    stripped["bench_thresholds"] = []
    with pytest.raises(InputError):
        run_b1(rules_env=(require_data_dir(), stripped, truth, aliases))


def test_b1_probe_is_falsifiable():
    """探活：坏引擎注入 → 未达标 + mismatches 非空（基准能红）。"""
    ok, detail = run_suite_live_probe("B1")
    assert ok is True
    assert "F1=" in detail


def test_b1_probe_rejects_unknown_suite():
    with pytest.raises(InputError):
        run_suite_live_probe("B99")

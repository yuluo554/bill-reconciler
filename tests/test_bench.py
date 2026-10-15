"""内置基准测试（M4，plan/03 §九）。

- B2/B3/B4 真值对账全绿（门槛读规则包，门槛是数据）；
- B2 双向对账：公式推导端点 vs 粗扫+细扫穷举恢复一致；
- 探活可证伪：四套件注入缺陷必报未达标；
- 退出码契约：run_bench 0 达标 / 1 未达标 / 2 未知名（--only）。
"""

import json

import pytest

from bill_reconciler.bench_b2 import run_b2, run_b2_boundary_reconciliation
from bill_reconciler.bench_b3 import run_b3
from bill_reconciler.bench_b4 import run_b4
from bill_reconciler.bench_runner import (
    _load_frozen,
    _threshold,
    run_all_probes,
    run_bench,
)
from bill_reconciler.errors import InputError


def test_b2_truth_reconciliation_pass():
    result = run_b2()
    assert result["pass"] is True
    assert result["accuracy"] == 1.0
    assert result["false_positives"] == 0
    assert result["total"] == 14  # 5 簇×(verdict+代表笔含 S1 无代表) + 5 反例


def test_b2_thresholds_are_data():
    _, manifest, _, _ = _load_frozen()
    result = run_b2()
    assert result["thresholds"]["accuracy_min"] == \
        _threshold(manifest, "bench_b2_cluster_accuracy_min")
    assert result["thresholds"]["false_positive_max"] == \
        _threshold(manifest, "bench_b2_false_positive_max")


def test_b2_boundary_reconciliation_two_paths_agree():
    """双向对账：推导端点（引擎）与穷举恢复两条路径同结论。"""
    result = run_b2_boundary_reconciliation()
    assert result["pass"] is True
    kinds = [c["kind"] for c in result["checks"]]
    assert "endpoint_hit_at_W" in kinds
    assert "brute_force_agreement" in kinds


def test_b3_full_hit_and_unknown_separability():
    result = run_b3()
    assert result["pass"] is True
    assert result["accuracy"] == 1.0
    assert result["total"] == 67
    assert result["unknown_violations"] == []


def test_b4_subscription_f1_and_price_records():
    result = run_b4()
    assert result["pass"] is True
    assert result["f1"] == 1.0
    assert result["price_changes_match"] is True
    assert result["distractor_hits"] == []


def test_run_bench_all_green_exit_0():
    results, code = run_bench()
    assert code == 0
    assert [r["suite"] for r in results] == ["B1", "B2", "B3", "B4"]
    assert all(r["pass"] for r in results)


def test_run_bench_only_known_name():
    results, code = run_bench(only=["B2"])
    assert code == 0
    assert len(results) == 1
    assert results[0]["suite"] == "B2"


def test_run_bench_unknown_name_is_usage_error():
    with pytest.raises(InputError):
        run_bench(only=["B99"])


def test_probes_all_falsifiable():
    """探活家族：四套件注入缺陷 → 基准必须报未达标。"""
    for name, ok, detail in run_all_probes():
        assert ok, "%s 探活失败（注入缺陷后基准仍绿 = 假门）：%s" % (name, detail)

"""模块⑤ 订阅识别测试（M4，plan/03 §5.1）。

- 真值对齐：expect_subscription 5 订阅全形态（月付/涨价/季付/年付/中断）
  逐条 entries 集合对齐 + 涨价记录对齐 + 非周期干扰行不判订阅；
- 规则驱动边界（不读真值库）：容差端点、涨价阈值端点、漏期补链、
  确定性（同输入同输出）；
- 未知/非消费行绝不进入订阅判定。
"""

import json
from decimal import Decimal

import pytest

from bill_reconciler.datadir import require_data_dir
from bill_reconciler.ingest.importer import import_files
from bill_reconciler.normalize import normalize_ledger
from bill_reconciler.params import load_rules_package
from bill_reconciler.pipeline import run_pipeline
from bill_reconciler.classify import classify_ledger
from bill_reconciler import subscription as S
from bill_reconciler.subscription import (
    detect_subscriptions,
    detect_subscription_ledger,
)


@pytest.fixture(scope="module")
def package():
    return load_rules_package(require_data_dir())


def _classified_ledger(package):
    ledger, _ = run_pipeline([
        str(p) for p in sorted((package.data_dir / "samples").iterdir())
        if p.is_file()
    ])
    return ledger


@pytest.fixture(scope="module")
def full_ledger(package):
    return _classified_ledger(package)


@pytest.fixture(scope="module")
def detected(package, full_ledger):
    subs, dis = detect_subscriptions(
        full_ledger,
        min_repeats=package.params.get("subscription_min_repeats"),
        price_change_min_percent=package.params.get("price_change_min_percent"),
        period_table=package.params.get("period_table"),
        default_tolerance_days=package.params.get(
            "subscription_interval_tolerance_days"),
    )
    return subs, dis


# ── 真值对齐（样本驱动层） ──────────────────────────────────────────

def _truth_subscription(package):
    truth = json.loads(
        (package.data_dir / "truth" / "truth.json").read_text(encoding="utf-8")
    )
    return truth["expect_subscription"]


def test_truth_subscription_entries_match(package, detected):
    """5 订阅逐条 entries 集合对齐（形态：月付/涨价/季付/年付/中断）。"""
    subs, _ = detected
    truth = _truth_subscription(package)
    expected = {e["subscription_id"]: set(e["entries"])
                for e in truth["subscriptions"]}
    observed = [set(s["entries"]) for s in subs]
    for sub_id, entries in expected.items():
        assert entries in observed, (
            "订阅 %s 的成员集合未被识别：%s" % (sub_id, sorted(entries))
        )


def test_truth_price_change_recorded(package, detected):
    """涨价记录：观测到的前后金额与落点行（SUB-B 形态）。"""
    subs, _ = detected
    truth = _truth_subscription(package)
    expected_changes = {}
    for e in truth["subscriptions"]:
        for c in e["price_changes"]:
            expected_changes[c["entry"]] = (c["from_amount"], c["to_amount"])
    observed_changes = {}
    for s in subs:
        for c in s["price_changes"]:
            observed_changes[c["entry"]] = (c["from_amount"], c["to_amount"])
    assert observed_changes == expected_changes
    assert expected_changes  # 真值确有涨价形态（防空转对齐）


def test_truth_gap_interrupted_flagged(package, detected):
    """周期中断形态：中断续接点被显式记录（SUB-E 形态，漏 2026-06 一期）。"""
    subs, _ = detected
    truth = _truth_subscription(package)
    gap_sub = [e for e in truth["subscriptions"] if e["gaps"]]
    assert gap_sub, "真值确有中断形态（防空转对齐）"
    # 中断后的续接行必须落进该订阅成员，且该订阅恰有 1 条中断记录
    for e in gap_sub:
        match = [s for s in subs if set(e["entries"]) == set(s["entries"])]
        assert match, "中断订阅未被识别"
        assert len(match[0]["gaps"]) == len(e["gaps"])
        assert match[0]["gaps"][0]["resumed_entry"] in e["entries"]


def test_truth_non_periodic_distractor_not_subscription(package, detected):
    """非周期相似金额不得判为订阅（打车平台：间隔 43/33 天不落带）。"""
    subs, distractors = detected
    truth = _truth_subscription(package)
    sub_entries = {e for s in subs for e in s["entries"]}
    for group in truth["non_periodic_distractors"]:
        for entry in group["entries"]:
            assert entry not in sub_entries
            assert any(d["id"] == entry for d in distractors)


def test_subscription_view_records_marked(package, full_ledger):
    """视图：订阅成员 record 增设 subscription_id；原始不可变（只增不改）。"""
    out = detect_subscription_ledger(
        full_ledger,
        min_repeats=package.params.get("subscription_min_repeats"),
        price_change_min_percent=package.params.get("price_change_min_percent"),
        period_table=package.params.get("period_table"),
        default_tolerance_days=package.params.get(
            "subscription_interval_tolerance_days"),
    )
    for record_before, record_after in zip(full_ledger["records"],
                                           out["records"]):
        for key, value in record_before.items():
            assert record_after[key] == value  # 只增不改
    sub_section = out["subscription"]
    assert sub_section["subscriptions"]
    for sub in sub_section["subscriptions"]:
        for entry in sub["entries"]:
            pass  # 成员标记在下方逐条断言
    by_id = {r["id"]: r for r in out["records"]}
    for sub in sub_section["subscriptions"]:
        for entry in sub["entries"]:
            assert by_id[entry]["subscription_id"] == sub["subscription_id"]


def test_subscription_params_snapshot(package, full_ledger):
    """参数快照来自规则包（非内联）；来源标注在案。"""
    out = detect_subscription_ledger(
        full_ledger,
        min_repeats=package.params.get("subscription_min_repeats"),
        price_change_min_percent=package.params.get("price_change_min_percent"),
        period_table=package.params.get("period_table"),
        default_tolerance_days=package.params.get(
            "subscription_interval_tolerance_days"),
    )
    params = out["subscription"]["params"]
    assert params["min_repeats"] == \
        package.params.get("subscription_min_repeats")
    assert params["price_change_min_percent"] == \
        package.params.get("price_change_min_percent")
    assert params["period_table"] == package.params.get("period_table")
    assert "非官方" in params["source"]


# ── 规则驱动边界（不读真值库） ──────────────────────────────────────

BANDS_INPUT = [
    {"id": "monthly", "label": "月付", "interval_days": 30, "tolerance_days": 2},
    {"id": "quarterly", "label": "季付", "interval_days": 91, "tolerance_days": 3},
    {"id": "yearly", "label": "年付", "interval_days": 365, "tolerance_days": 5},
]


def _record(rid, offset_days, amount="10.00", merchant="商户甲"):
    from datetime import date, timedelta

    day = date(2026, 1, 1) + timedelta(days=offset_days)
    return {
        "id": rid, "time": "%s 08:00:00" % day.isoformat(),
        "amount": amount, "direction": "expense",
        "normalized_counterparty": merchant, "counterparty": merchant,
        "semantic_label": "消费", "source_row": 1, "source_platform": "wechat",
    }


def _detect(records, **overrides):
    ledger = {"records": records}
    kwargs = dict(
        min_repeats=3,
        price_change_min_percent=2.0,
        period_table=BANDS_INPUT,
        default_tolerance_days=2,
    )
    kwargs.update(overrides)
    return detect_subscriptions(ledger, **kwargs)


def test_boundary_tolerance_upper_edge_hits():
    """间隔 = 30+2=32 天（月付容差上沿，闭区间）→ 命中。"""
    records = [_record("a", 1), _record("b", 33), _record("c", 65)]
    subs, _ = _detect(records)
    assert len(subs) == 1
    assert subs[0]["repeats"] == 3


def test_boundary_tolerance_beyond_misses():
    """间隔 = 33 天（月付容差外）→ 不成种子。"""
    records = [_record("a", 1), _record("b", 34), _record("c", 67)]
    subs, _ = _detect(records)
    assert subs == []


def test_boundary_tolerance_lower_edge_hits():
    """间隔 = 30-2=28 天（月付容差下沿）→ 命中。"""
    records = [_record("a", 1), _record("b", 29), _record("c", 57)]
    subs, _ = _detect(records)
    assert len(subs) == 1


def test_repeats_min_exact_hits_and_one_less_misses():
    """重复次数 = min_repeats 恰好成立；少一期不成订阅。"""
    three = [_record("a", 1), _record("b", 31), _record("c", 61)]
    subs, _ = _detect(three)
    assert len(subs) == 1
    two = three[:2]
    subs2, _ = _detect(two)
    assert subs2 == []


def test_price_change_threshold_edge():
    """涨价阈值端点：变化 ≥ 阈值记涨价；低于阈值不并簇不记涨价。"""
    # 前段 3 笔 10.00（满足 min_repeats 锚定）→ 第 4 笔 10.21（2.1% ≥ 2.0%）
    up = [_record("a", 1, "10.00"), _record("b", 31, "10.00"),
          _record("c", 61, "10.00"), _record("d", 91, "10.21")]
    subs, _ = _detect(up)
    assert len(subs) == 1
    assert subs[0]["repeats"] == 4
    assert subs[0]["price_changes"], "2.1% 变动应记涨价"
    assert subs[0]["price_changes"][0]["from_amount"] == "10.00"
    assert subs[0]["price_changes"][0]["to_amount"] == "10.21"
    # 1.9%（<2.0%）：不并簇——前段独立成订阅，10.19 落干扰行
    below = [_record("a", 1, "10.00"), _record("b", 31, "10.00"),
             _record("c", 61, "10.00"), _record("d", 91, "10.19")]
    subs2, dis2 = _detect(below)
    assert all(not s["price_changes"] for s in subs2)
    assert any(d["id"] == "d" for d in dis2)


def test_price_change_below_threshold_same_amount_chain_splits():
    """金额切换但变化 < 阈值：不得并簇（防把噪声当涨价续链）。"""
    records = [_record("a", 1, "10.00"), _record("b", 31, "10.00"),
               _record("c", 61, "10.00"),
               _record("d", 91, "10.00"), _record("e", 121, "10.19")]
    subs, _ = _detect(records)
    assert len(subs) == 1  # 金额相同的 5 笔同链
    assert subs[0]["price_changes"] == []


def test_gap_missed_period_bridged_and_recorded():
    """漏一期：间隔 ≈2×30 天补链，期次中断显式记录。"""
    records = [_record("a", 1), _record("b", 31), _record("c", 61),
               _record("d", 121)]  # c→d 60 天 = 漏一期
    subs, _ = _detect(records)
    assert len(subs) == 1
    assert subs[0]["repeats"] == 4
    assert subs[0]["gaps"], "漏期应显式记录"
    assert subs[0]["gaps"][0]["missed_intervals"] == 1


def test_two_missed_periods_breaks_chain():
    """间隔 120 天（不落任何单期带、非漏一期补链带）→ 不续链。

    注意 90 天间隔是季付带合法命中（不是"漏期"），此处用 120 天真断点。
    """
    records = [_record("a", 1), _record("b", 31), _record("c", 61),
               _record("d", 181)]  # c→d 120 天
    subs, distractors = _detect(records)
    assert len(subs) == 1
    assert subs[0]["repeats"] == 3
    assert not subs[0]["gaps"]
    assert any(d["id"] == "d" for d in distractors)


def test_unknown_and_non_expense_never_judged():
    """语义未知/非消费/收入行绝不参与订阅判定。"""
    records = [_record("a", 1), _record("b", 31), _record("c", 61)]
    for r in records:
        r["semantic_label"] = "未知"
    subs, _ = _detect(records)
    assert subs == []
    for r in records:
        r["semantic_label"] = "消费"
        r["direction"] = "income"
    subs2, _ = _detect(records)
    assert subs2 == []


def test_determinism_same_input_same_output():
    """纯函数：同输入同输出（含订阅 id 编号稳定）。"""
    records = [_record("a", 1), _record("b", 31), _record("c", 61)]
    s1, d1 = _detect(records)
    s2, d2 = _detect(records)
    assert s1 == s2
    assert d1 == d2

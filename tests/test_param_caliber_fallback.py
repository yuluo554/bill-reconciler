"""零参数字面量门禁的**残余面**兜底测试（plan/03 §七，2026-10-16 审计修复）。

背景：静态门禁（``tests/test_no_param_literals.py``）的 token 集只覆盖
**两位及以上**数值（``param_tokens`` 按 ``len(text) > 1`` 过滤一位数豁免），
故三个真口径参数不在保护集内：

- ``subscription_min_repeats``（值 3）
- ``subscription_interval_tolerance_days``（值 2）
- ``header_locate_k``（值 2）

本文件做两件事（与静态门禁同向防御）：

1. **残余面登记锁定**：程序化算出"数值形态与 token 集不相交"的参数 id 集合，
   断言恰为上述三个——防豁免规则改动后残余面漂移而无人发现；
2. **行为穿透兜底**：逐参数覆盖规则包值，断言**可观测行为随之变化**——
   若引擎把口径硬编码进代码（而不是经 ``params.py`` 读规则包），
   覆盖参数值不会改变行为，本测试必红。

注意：本文件在 ``tests/`` 下，**不在** ``lint_params`` 的扫描面（``_SCAN_ROOTS``
只含 ``bill_reconciler``），因此这里的构造数值不算违规；被测行为锚在引擎。
"""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from bill_reconciler.datadir import require_data_dir
from bill_reconciler.ingest.locate import locate_header
from bill_reconciler.params import load_rules_package, param_tokens
from bill_reconciler.pipeline import run_pipeline
from bill_reconciler.subscription import detect_subscriptions

# 三个不受静态门禁保护的真口径参数（值均为一位数）
RESIDUAL_FACE = frozenset({
    "subscription_min_repeats",
    "subscription_interval_tolerance_days",
    "header_locate_k",
})


@pytest.fixture(scope="module")
def package():
    return load_rules_package(require_data_dir())


def _numeric_forms(value):
    """参数值 → 数值形态集合（与 params.param_tokens 同口径：整数十进制串、
    浮点双形式；列表/嵌套字典展开；非数值项不产生形态）。"""
    forms = set()
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            forms.add(str(item))
        elif isinstance(item, float):
            forms.add(str(item))
            forms.add(str(int(item)))
        elif isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, dict):
            stack.extend(item.values())
    return forms


def test_residual_face_is_registered(package):
    """残余面恰为登记的三个 id（防豁免规则改动后登记漂移）。"""
    tokens = param_tokens(package)
    uncovered = {
        entry["id"]
        for entry in package.manifest["params"]
        if _numeric_forms(entry["value"]) and not (_numeric_forms(entry["value"]) & tokens)
    }
    assert uncovered == set(RESIDUAL_FACE), (
        "门禁残余面漂移：实际 %s，登记 %s（plan/03 §七 / params.py docstring）"
        % (sorted(uncovered), sorted(RESIDUAL_FACE))
    )


def test_non_numeric_params_are_out_of_scope_by_type(package):
    """platform_priority 等非数值参数按类型出局，不是"豁免"（防混淆口径）。"""
    for entry in package.manifest["params"]:
        if entry["id"] == "platform_priority":
            assert _numeric_forms(entry["value"]) == set(), (
                "platform_priority 应为字符串序列（无数值形态，按类型出局）"
            )


# ── 行为穿透：subscription_min_repeats ──────────────────────────────


def _full_ledger(package):
    ledger, _ = run_pipeline([
        str(p) for p in sorted((package.data_dir / "samples").iterdir())
        if p.is_file()
    ])
    return ledger


def _detect(ledger, package, **overrides):
    kwargs = dict(
        min_repeats=package.params.get("subscription_min_repeats"),
        price_change_min_percent=package.params.get("price_change_min_percent"),
        period_table=package.params.get("period_table"),
        default_tolerance_days=package.params.get(
            "subscription_interval_tolerance_days"),
    )
    kwargs.update(overrides)
    return detect_subscriptions(ledger, **kwargs)


def test_min_repeats_penetrates_behavior(package):
    """min_repeats 覆盖值必改变结果：把它抬到"最长订阅重复数 + 1"→ 订阅清零。"""
    ledger = _full_ledger(package)
    baseline, _ = _detect(ledger, package)
    assert baseline, "真值确有订阅（防空转）"
    longest = max(s["repeats"] for s in baseline)
    raised, _ = _detect(ledger, package, min_repeats=longest + 1)
    assert raised == [], (
        "min_repeats 抬到 %d 后订阅未清零——口径疑似被硬编码"
        % (longest + 1)
    )
    # 不变量：检出订阅的重复数都不低于生效门槛
    assert all(s["repeats"] >= package.params.get("subscription_min_repeats")
               for s in baseline)


# ── 行为穿透：subscription_interval_tolerance_days ──────────────────


def _rec(rid, offset_days, amount="10.00", merchant="商户甲"):
    day = date(2026, 1, 1) + timedelta(days=offset_days)
    return {
        "id": rid, "time": "%s 08:00:00" % day.isoformat(),
        "amount": amount, "direction": "expense",
        "normalized_counterparty": merchant, "counterparty": merchant,
        "semantic_label": "消费", "source_row": 1, "source_platform": "wechat",
    }


def test_interval_tolerance_penetrates_behavior(package):
    """默认容差只在周期条目未自带 tolerance_days 时生效——用它做穿透面：

    周期表只给 interval_days=30（无 tolerance_days），三笔间隔 28 天
    （= 30 − 2，落在规则包默认容差 2 的闭区间内）。覆盖默认容差为 0 →
    28 天偏离 30 天 2 天 > 0，不成订阅。
    """
    ledger = {"records": [_rec("a", 1), _rec("b", 29), _rec("c", 57)]}
    bare_band = [{"id": "monthly", "label": "月付", "interval_days": 30}]
    effective = package.params.get("subscription_interval_tolerance_days")
    hit, _ = _detect(ledger, package, period_table=bare_band,
                     default_tolerance_days=effective)
    miss, _ = _detect(ledger, package, period_table=bare_band,
                      default_tolerance_days=0)
    assert len(hit) == 1, "默认容差内应成订阅（构造前提）"
    assert miss == [], (
        "默认容差覆盖为 0 后仍成订阅——口径疑似被硬编码（期望值 %s）" % effective
    )


# ── 行为穿透：header_locate_k ──────────────────────────────────────


def test_header_locate_k_penetrates_behavior(package):
    """K 值决定表头行定位：构造"第 1 行命中 1 列、第 2 行命中 4 列"，

    K=1 → 选中第 1 行；K=2（规则包值）→ 跳过第 1 行选中第 2 行。
    两者不同即证明 K 真被读取；硬编码 K 则两次结果相同。
    """
    lines = [
        "交易时间",  # 仅 1 列命中锚定列
        "交易时间\t交易对方\t金额(元)\t收/支",  # 4 列命中
    ]
    k_low, _ = locate_header(lines, "wechat", 1, 20)
    k_pkg, _ = locate_header(lines, "wechat",
                             package.params.get("header_locate_k"), 20)
    assert k_low == 0, "K=1 应选中首个命中行"
    assert k_pkg == 1, (
        "K=%s 应跳过仅 1 列命中的第 1 行——口径疑似被硬编码"
        % package.params.get("header_locate_k")
    )
    assert k_low != k_pkg, "K 值未改变定位行为（口径未被读取）"

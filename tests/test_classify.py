"""模块④ 语义识别回归（M3）。

真值对齐（expect_semantic 67 行）+ 规则驱动测试（优先级/方向条件/未知一等，
不读真值库构造干扰例）。
"""

import json

import pytest

from bill_reconciler.classify import LABEL_UNKNOWN, classify_ledger, load_keyword_rules
from bill_reconciler.datadir import require_data_dir
from bill_reconciler.errors import InputError
from bill_reconciler.ingest.importer import import_files
from bill_reconciler.normalize import normalize_ledger
from bill_reconciler.params import load_rules_package


@pytest.fixture(scope="module")
def package():
    return load_rules_package(require_data_dir())


@pytest.fixture(scope="module")
def classified(package):
    samples = sorted(
        str(p) for p in (package.data_dir / "samples").iterdir() if p.is_file()
    )
    ledger = import_files(
        samples,
        column_aliases=package.aliases["column_aliases"],
        header_k=package.params.get("header_locate_k"),
        max_scan_lines=package.params.get("header_locate_max_scan_lines"),
    )
    ledger = normalize_ledger(ledger, package.aliases)
    return classify_ledger(ledger, package.keywords)


def test_truth_semantic_labels_match(classified):
    """真值 expect_semantic 逐行对齐（67 行全量）。"""
    truth = json.loads(
        (require_data_dir() / "truth" / "truth.json").read_text(encoding="utf-8")
    )
    by_id = {r["id"]: r["semantic_label"] for r in classified["records"]}
    for rid, expect in truth["expect_semantic"].items():
        assert by_id[rid] == expect["label"], (
            "%s：%s ≠ 期望 %s" % (rid, by_id[rid], expect["label"])
        )


def test_unknown_is_first_class(classified):
    """未知是一等结论：未知行入显式清单、绝不标成消费。"""
    unknown_ids = {u["id"] for u in classified["classify"]["unknown_rows"]}
    by_id = {r["id"]: r for r in classified["records"]}
    assert unknown_ids
    for rid in unknown_ids:
        assert by_id[rid]["semantic_label"] == LABEL_UNKNOWN
        assert by_id[rid]["semantic_basis"]["basis"]["rule"] == "no_match"


def test_refund_keyword_in_expense_direction_not_hit(package):
    """干扰例：支出方向出现"退款"词 → 不命中退款规则（未知；真值 DIST-退款词 同型）。"""
    record = {
        "id": "t#1", "direction": "expense",
        "normalized_counterparty": "示例房东李四", "description": "已申请退款",
    }
    out = classify_ledger({"records": [record]}, package.keywords)
    verdict = out["records"][0]
    assert verdict["semantic_label"] == LABEL_UNKNOWN
    assert verdict["semantic_basis"]["basis"]["rule"] == "no_match"
    assert verdict["semantic_basis"]["all_hits"] == []


def test_transfer_word_income_not_hit(package):
    """干扰例：入账 + 张三转账（词面无规则）→ 未知，不得猜成消费/报销。"""
    record = {
        "id": "t#2", "direction": "income",
        "normalized_counterparty": "示例同事张三", "description": "转账",
    }
    out = classify_ledger({"records": [record]}, package.keywords)
    assert out["records"][0]["semantic_label"] == LABEL_UNKNOWN


def test_reimbursement_keyword_hits_income(package):
    record = {
        "id": "t#3", "direction": "income",
        "normalized_counterparty": "示例同事张三", "description": "报销款-8月差旅",
    }
    out = classify_ledger({"records": [record]}, package.keywords)
    row = out["records"][0]
    assert row["semantic_label"] == "报销"
    assert row["semantic_basis"]["all_hits"][0]["rule_id"] == "R30_reimbursement"


def test_self_transfer_neutral_direction_hits(package):
    """本人转账含 neutral 方向（R40 any）。"""
    record = {
        "id": "t#4", "direction": "neutral",
        "normalized_counterparty": "示例本人卡A", "description": "账户划转",
    }
    out = classify_ledger({"records": [record]}, package.keywords)
    assert out["records"][0]["semantic_label"] == "本人转账"


def test_priority_order_and_full_hits_recorded(package):
    """同一行命中多条：取 priority 首个，全部命中条目都记录。"""
    rules = load_keyword_rules(package.keywords)
    assert rules[0]["id"] == "R10_refund"  # priority 升序首位
    record = {
        "id": "t#5", "direction": "income",
        "normalized_counterparty": "示例超市丙", "description": "退款",
    }
    out = classify_ledger({"records": [record]}, package.keywords)
    basis = out["records"][0]["semantic_basis"]
    assert basis["label"] == "退款"
    assert basis["all_hits"], "命中条目必须全记录"
    priorities = [h["priority"] for h in basis["all_hits"]]
    assert priorities == sorted(priorities)


def test_empty_keywords_rejected(package):
    bad = {"rules": [{"id": "X", "label": "消费", "direction_condition": "expense",
                      "keywords": [], "priority": 1}]}
    with pytest.raises(InputError):
        load_keyword_rules(bad)


def test_distribution_and_unknown_amounts(classified):
    dist = classified["classify"]["distribution"]
    assert dist.get(LABEL_UNKNOWN, 0) == len(classified["classify"]["unknown_rows"])
    assert sum(dist.values()) == len(classified["records"])

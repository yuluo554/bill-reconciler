"""模块② 归一化回归（M3）。

规则驱动（不读真值库）：动作序列写死、纯函数、逐条依据、"归并了"与
"没归并"可区分；规则包（aliases.json）为唯一规则来源。
"""

import copy

import pytest

from bill_reconciler.datadir import require_data_dir
from bill_reconciler.normalize import AliasIndex, normalize_ledger
from bill_reconciler.params import load_rules_package


@pytest.fixture(scope="module")
def package():
    return load_rules_package(require_data_dir())


@pytest.fixture(scope="module")
def index(package):
    return AliasIndex(package.aliases)


def test_suffix_strip(index):
    norm, actions = index.normalize("示例便利店甲有限公司")
    assert norm == "示例便利店甲"
    assert [a["rule"] for a in actions] == ["suffix_strip"]


def test_whitespace_then_fullwidth_then_alias(index):
    # 全角括号 + 尾部空白：去空白 → 全半角 → 别名表 三段齐发
    norm, actions = index.normalize("示例便利店甲（有限）公司 ")
    assert norm == "示例便利店甲"
    assert [a["rule"] for a in actions] == [
        "whitespace_collapse", "fullwidth_norm", "alias_table"]


def test_inner_whitespace_removed(index):
    # 内部空白也去除（plan/03 §2.1 "首尾及内部"）
    norm, actions = index.normalize("示例 便利店甲")
    assert norm == "示例便利店甲"
    assert [a["rule"] for a in actions] == ["whitespace_collapse"]


def test_no_match_keeps_original_with_empty_actions(index):
    # 未命中 → 原样保留 + 依据为空（"归并了"与"没归并"可区分）
    norm, actions = index.normalize("示例房东李四")
    assert norm == "示例房东李四"
    assert actions == []


def test_fullwidth_only(index):
    norm, actions = index.normalize("ＡＢＣ公司")
    assert norm == "ABC公司"
    assert [a["rule"] for a in actions] == ["fullwidth_norm"]


def test_pure_function_same_input_same_output(index):
    a = index.normalize("示例便利店甲（有限）公司")
    b = index.normalize("示例便利店甲（有限）公司")
    assert a == b


def test_variant_indexed_after_pipeline(index):
    # 变体先过归一管线再入索引：带全角括号的变体能直接命中
    norm, actions = index.normalize("示例咖啡丁（五道口店）")
    assert norm == "示例咖啡丁"
    assert actions[-1]["rule"] == "alias_table"


def test_strip_leaving_empty_does_not_apply(index):
    # 剥离后为空则不生效（后缀剥离守门："有限公司"单独出现不剥成空串）
    norm, actions = index.normalize("有限公司")
    assert norm == "有限公司"
    assert actions == []


def test_normalize_ledger_adds_fields_and_journal(package):
    ledger = {
        "records": [
            {"id": "a#1", "counterparty": "示例便利店甲有限公司"},
            {"id": "a#2", "counterparty": "示例便利店甲"},
            {"id": "a#3", "counterparty": ""},
        ],
    }
    out = normalize_ledger(ledger, package.aliases)
    by_id = {r["id"]: r for r in out["records"]}
    assert by_id["a#1"]["normalized_counterparty"] == "示例便利店甲"
    assert by_id["a#1"]["normalize_actions"]
    assert by_id["a#2"]["normalized_counterparty"] == "示例便利店甲"
    assert by_id["a#2"]["normalize_actions"] == []
    assert by_id["a#3"]["normalized_counterparty"] == ""
    # 台账：原名去重；空名不入台账（a#1 与 a#2 是不同原名 → 2 条）
    assert len(out["normalize"]["entries"]) == 2
    # 原始不可变：入参不被改写
    assert "normalized_counterparty" not in ledger["records"][0]


def test_normalize_ledger_twice_same_result(package):
    ledger = {"records": [{"id": "a#1", "counterparty": "示例快餐乙外卖店"}]}
    once = normalize_ledger(ledger, package.aliases)
    twice = normalize_ledger(copy.deepcopy(once), package.aliases)
    assert once["records"] == twice["records"]

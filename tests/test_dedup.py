"""模块③ 去重回归（M3）。

真值对齐（expect_dedup 5 簇 + must_not_merge 5 对）+ 规则驱动边界测试
（窗口 ±ε 端点，不读真值库——plan/03 §3.4）。
"""

import copy
import json

import pytest

from bill_reconciler.datadir import require_data_dir
from bill_reconciler.dedup import dedup_ledger
from bill_reconciler.errors import InputError
from bill_reconciler.ingest.importer import import_files
from bill_reconciler.normalize import normalize_ledger
from bill_reconciler.params import load_rules_package


@pytest.fixture(scope="module")
def package():
    return load_rules_package(require_data_dir())


@pytest.fixture(scope="module")
def normalized(package):
    samples = sorted(
        str(p) for p in (package.data_dir / "samples").iterdir() if p.is_file()
    )
    ledger = import_files(
        samples,
        column_aliases=package.aliases["column_aliases"],
        header_k=package.params.get("header_locate_k"),
        max_scan_lines=package.params.get("header_locate_max_scan_lines"),
    )
    return normalize_ledger(ledger, package.aliases)


@pytest.fixture(scope="module")
def deduped(normalized, package):
    return dedup_ledger(
        normalized,
        window_seconds=package.params.get("dedup_window_seconds"),
        platform_priority=package.params.get("platform_priority"),
    )


def _clusters(deduped):
    return {
        tuple(c["members"]): (c["verdict"], c["representative"])
        for c in deduped["dedup"]["clusters"]
    }


def test_truth_clusters_match(deduped):
    """真值 5 簇逐条对齐（verdict/members/representative）。"""
    truth = json.loads(
        (deduped["meta"].get("_data_dir") or require_data_dir() / "truth" / "truth.json")
        .read_text(encoding="utf-8")
    )
    got = _clusters(deduped)
    for cluster in truth["expect_dedup"]["clusters"]:
        key = tuple(cluster["members"])
        assert key in got, "真值簇 %s 未命中：%s" % (cluster["cluster_id"], sorted(got))
        verdict, representative = got[key]
        assert verdict == cluster["verdict"]
        if "representative" in cluster:
            assert representative == cluster["representative"]


def test_truth_must_not_merge(deduped):
    """真值 5 对 must_not_merge：任何一对不得出现在同一簇。"""
    truth = json.loads(
        (require_data_dir() / "truth" / "truth.json").read_text(encoding="utf-8")
    )
    got = _clusters(deduped)
    for item in truth["expect_dedup"]["must_not_merge"]:
        pair = tuple(item["pair"])
        merged = [members for members in got if pair[0] in members and pair[1] in members]
        assert not merged, "must_not_merge 对被合并：%s（%s）" % (pair, item["form"])


def _record(rid, platform, time_s, amount, direction, counterparty):
    return {
        "id": rid,
        "source_platform": platform,
        "source_file": rid.rsplit("#", 1)[0],
        "source_row": int(rid.rsplit("#", 1)[1]),
        "time": time_s,
        "amount": amount,
        "direction": direction,
        "normalized_counterparty": counterparty,
    }


W = None  # 占位：窗口从规则包读（测试内显式用 60/61 构造端点，属"测试自身参数"）


def _small_ledger(records):
    return {
        "meta": {"sources": []},
        "records": records,
        "issues": [],
        "file_issues": [],
    }


def test_boundary_exactly_window_hits(package):
    """Δt = W 恰好命中（闭区间）——规则驱动，不读真值库。"""
    records = [
        _record("a.csv#1", "wechat", "2026-08-01 12:00:00", "10.00", "expense", "甲"),
        _record("b.csv#1", "alipay", "2026-08-01 12:01:00", "10.00", "expense", "甲"),
    ]
    out = dedup_ledger(_small_ledger(records), window_seconds=60,
                       platform_priority=["wechat", "alipay"])
    assert len(out["dedup"]["clusters"]) == 1
    assert out["dedup"]["clusters"][0]["verdict"] == "duplicate_cross_platform"


def test_boundary_window_plus_one_misses(package):
    """Δt = W+1s 不命中。"""
    records = [
        _record("a.csv#1", "wechat", "2026-08-01 12:00:00", "10.00", "expense", "甲"),
        _record("b.csv#1", "alipay", "2026-08-01 12:01:01", "10.00", "expense", "甲"),
    ]
    out = dedup_ledger(_small_ledger(records), window_seconds=60,
                       platform_priority=["wechat", "alipay"])
    assert out["dedup"]["clusters"] == []


def test_one_cent_difference_not_merged(package):
    """金额差 1 分不合并（Decimal 精确相等）。"""
    records = [
        _record("a.csv#1", "wechat", "2026-08-01 12:00:00", "88.00", "expense", "甲"),
        _record("b.csv#1", "alipay", "2026-08-01 12:00:30", "88.01", "expense", "甲"),
    ]
    out = dedup_ledger(_small_ledger(records), window_seconds=60,
                       platform_priority=["wechat", "alipay"])
    assert out["dedup"]["clusters"] == []


def test_diff_counterparty_not_merged(package):
    records = [
        _record("a.csv#1", "wechat", "2026-08-01 12:00:00", "10.00", "expense", "甲"),
        _record("b.csv#1", "alipay", "2026-08-01 12:00:30", "10.00", "expense", "乙"),
    ]
    out = dedup_ledger(_small_ledger(records), window_seconds=60,
                       platform_priority=["wechat", "alipay"])
    assert out["dedup"]["clusters"] == []


def test_diff_direction_not_merged(package):
    records = [
        _record("a.csv#1", "wechat", "2026-08-01 12:00:00", "10.00", "expense", "甲"),
        _record("b.csv#1", "alipay", "2026-08-01 12:00:30", "10.00", "income", "甲"),
    ]
    out = dedup_ledger(_small_ledger(records), window_seconds=60,
                       platform_priority=["wechat", "alipay"])
    assert out["dedup"]["clusters"] == []


def test_same_platform_is_candidate_not_merged(package):
    """同平台三元组命中 → candidate_same_platform，绝不静默合并。"""
    records = [
        _record("a.csv#1", "wechat", "2026-08-01 12:00:00", "66.00", "expense", "甲"),
        _record("a.csv#2", "wechat", "2026-08-01 12:00:10", "66.00", "expense", "甲"),
    ]
    out = dedup_ledger(_small_ledger(records), window_seconds=60,
                       platform_priority=["wechat", "alipay"])
    cluster = out["dedup"]["clusters"][0]
    assert cluster["verdict"] == "candidate_same_platform"
    by_id = {r["id"]: r for r in out["records"]}
    # 同平台候选不排除出净额
    assert all(not by_id[i].get("is_duplicate") for i in cluster["members"])


def test_representative_earliest_then_platform_then_row(package):
    """代表笔：时间最早 → 平台优先级 → 行号。"""
    records = [
        _record("c.csv#7", "bank", "2026-08-01 12:00:30", "10.00", "expense", "甲"),
        _record("b.csv#2", "alipay", "2026-08-01 12:00:00", "10.00", "expense", "甲"),
        _record("a.csv#9", "wechat", "2026-08-01 12:00:30", "10.00", "expense", "甲"),
    ]
    out = dedup_ledger(_small_ledger(records), window_seconds=60,
                       platform_priority=["wechat", "alipay", "bank"])
    cluster = out["dedup"]["clusters"][0]
    # 时间最早 = alipay#2
    assert cluster["representative"] == "b.csv#2"
    # 同时刻时：wechat 优先级高于 bank → a.csv#9 排前
    records2 = [
        _record("c.csv#7", "bank", "2026-08-01 12:00:00", "10.00", "expense", "甲"),
        _record("a.csv#9", "wechat", "2026-08-01 12:00:00", "10.00", "expense", "甲"),
    ]
    out2 = dedup_ledger(_small_ledger(records2), window_seconds=60,
                        platform_priority=["wechat", "alipay", "bank"])
    assert out2["dedup"]["clusters"][0]["representative"] == "a.csv#9"
    # 同时刻同优先级：行号小者
    records3 = [
        _record("a.csv#9", "wechat", "2026-08-01 12:00:00", "10.00", "expense", "甲"),
        _record("a.csv#4", "wechat", "2026-08-01 12:00:00", "10.00", "expense", "甲"),
    ]
    out3 = dedup_ledger(_small_ledger(records3), window_seconds=60,
                        platform_priority=["wechat"])
    assert out3["dedup"]["clusters"][0]["representative"] == "a.csv#4"


def test_chain_adjacent_clustering(package):
    """链式相邻：A-B 近、B-C 近、A-C 远 → 三者同簇（划分由规则唯一确定）。"""
    records = [
        _record("a.csv#1", "wechat", "2026-08-01 12:00:00", "10.00", "expense", "甲"),
        _record("b.csv#1", "alipay", "2026-08-01 12:00:50", "10.00", "expense", "甲"),
        _record("c.csv#1", "bank", "2026-08-01 12:01:40", "10.00", "expense", "甲"),
    ]
    out = dedup_ledger(_small_ledger(records), window_seconds=60,
                       platform_priority=["wechat", "alipay", "bank"])
    assert len(out["dedup"]["clusters"]) == 1
    assert out["dedup"]["clusters"][0]["members"] == [
        "a.csv#1", "b.csv#1", "c.csv#1"]
    # A-C 相距 100s > W=60，但链式仍成簇——依据里记录实测时间跨度
    assert out["dedup"]["clusters"][0]["time_span_seconds"] == 100.0


def test_cluster_order_and_ids_deterministic(normalized, package):
    args = (normalized, package.params.get("dedup_window_seconds"),
            package.params.get("platform_priority"))
    first = dedup_ledger(copy.deepcopy(normalized), window_seconds=args[1],
                         platform_priority=args[2])
    second = dedup_ledger(copy.deepcopy(normalized), window_seconds=args[1],
                          platform_priority=args[2])
    assert first["dedup"] == second["dedup"]
    assert first["records"] == second["records"]


def test_negative_window_rejected(package):
    with pytest.raises(InputError):
        dedup_ledger(_small_ledger([]), window_seconds=-1,
                     platform_priority=["wechat"])


def test_unknown_direction_rows_not_clustered(package):
    """方向缺失（unknown 行）不参与聚类。"""
    records = [
        _record("a.csv#1", "wechat", "2026-08-01 12:00:00", "10.00", None, "甲"),
        _record("b.csv#1", "alipay", "2026-08-01 12:00:30", "10.00", None, "甲"),
    ]
    out = dedup_ledger(_small_ledger(records), window_seconds=60,
                       platform_priority=["wechat", "alipay"])
    assert out["dedup"]["clusters"] == []

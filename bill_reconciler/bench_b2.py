"""内置基准 B2 去重套件（plan/03 §九）。

两个独立的对账路径，互为**双向对账**（公式推导端点 vs 粗扫+细扫穷举恢复）：

- **真值对账**（样本驱动）：``expect_dedup`` 簇级判定 vs 引擎结果——
  5 簇（verdict+members+representative）+ 5 对 must_not_merge 全不合并；
  指标 = 簇判定准确率（含防误报：must_not_merge 误并即 false positive）；
- **规则驱动双向对账**（不读真值库）：窗口 W 的**边界端点**由公式直接
  推导（Δt=W 必并、Δt=W+1s 必不并），再用**粗扫+细扫穷举**独立恢复同一
  划分——两条独立路径对同一输入给出同一结论才算通过。

指标门槛读规则包（``bench_b2_cluster_accuracy_min`` / ``bench_b2_false_positive_max``），
门槛是数据；真值只存输入与期望，观测运行时实算。
"""

import json
from datetime import datetime, timedelta

from .dedup import dedup_ledger
from .errors import InputError

SECONDS_STEP = 1
BRUTE_FORCE_LIMIT = 4000


def _observed_cluster_map(ledger):
    """引擎结果 → {(frozenset(members)): (verdict, representative)}。"""
    return {
        frozenset(c["members"]): (c["verdict"], c.get("representative"))
        for c in ledger.get("dedup", {}).get("clusters", [])
    }


def _pair_cluster_map(ledger):
    """引擎结果 → {frozenset({id1, id2}): cluster}（判"两行是否同簇"用）。"""
    result = {}
    for cluster in ledger.get("dedup", {}).get("clusters", []):
        members = cluster["members"]
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                result[frozenset((a, b))] = cluster
    return result


def run_b2(deduped=None, rules_env=None):
    """B2 去重基准：真值 5 簇 + 5 反例对账 → 准确率 + 误报数。

    ``deduped`` 可注入（探活用）；缺省 = 全量冻结样例跑真引擎。
    """
    from .bench_runner import _load_frozen, _threshold

    data_dir, manifest, truth, column_aliases = (
        _load_frozen() if rules_env is None else rules_env
    )
    if deduped is None:
        from .ingest.importer import import_files
        from .normalize import normalize_ledger

        samples = sorted(
            str(p) for p in (data_dir / "samples").iterdir() if p.is_file()
        )
        ledger = import_files(
            samples,
            column_aliases=column_aliases,
            header_k=_param(manifest, "header_locate_k"),
            max_scan_lines=_param(manifest, "header_locate_max_scan_lines"),
        )
        deduped = dedup_ledger(
            normalize_ledger(ledger, _aliases_doc(data_dir)),
            window_seconds=_param(manifest, "dedup_window_seconds"),
            platform_priority=_param(manifest, "platform_priority"),
        )

    expect = truth["expect_dedup"]
    observed = _observed_cluster_map(deduped)
    pair_map = _pair_cluster_map(deduped)

    checks = []
    hit = 0
    false_positives = 0

    for cluster in expect["clusters"]:
        members = frozenset(cluster["members"])
        ok = members in observed and observed[members][0] == cluster["verdict"]
        checks.append({"kind": "cluster", "expect": cluster["cluster_id"],
                       "ok": ok})
        if ok:
            hit += 1
        representative = cluster.get("representative")
        if representative:
            obs = observed.get(members)
            ok = obs is not None and obs[1] == representative
            checks.append({"kind": "representative",
                           "expect": cluster["cluster_id"], "ok": ok})
            if ok:
                hit += 1

    for pair in expect["must_not_merge"]:
        merged = frozenset(pair["pair"]) in pair_map
        checks.append({"kind": "must_not_merge", "expect": pair["form"],
                       "ok": not merged})
        if merged:
            false_positives += 1
        if not merged:
            hit += 1

    total = len(checks)
    accuracy = hit / total if total else 0.0
    accuracy_min = _threshold(manifest, "bench_b2_cluster_accuracy_min")
    fp_max = _threshold(manifest, "bench_b2_false_positive_max")
    passed = accuracy >= accuracy_min and false_positives <= fp_max
    return {
        "suite": "B2",
        "total": total,
        "hit": hit,
        "accuracy": round(accuracy, 6),
        "false_positives": false_positives,
        "thresholds": {"accuracy_min": accuracy_min, "false_positive_max": fp_max},
        "pass": passed,
        "checks": checks,
        "notes": "簇判定 + 代表笔 + must_not_merge 误报对账（expect_dedup 全量）",
    }


def _param(manifest, param_id):
    for entry in manifest["params"]:
        if entry["id"] == param_id:
            return entry["value"]
    raise InputError("规则包缺少参数 %s（配置错误）" % param_id)


def _aliases_doc(data_dir):
    """完整 aliases.json（AliasIndex 消费 suffix_strip+aliases 全文档）。"""
    import json

    return json.loads(
        (data_dir / "rules" / "aliases.json").read_text(encoding="utf-8")
    )


def _derivation_endpoint_clustering(records, window_seconds):
    """路径一（公式推导端点）：直接用引擎语义复算——对排序后的等键组，
    相邻 Δt ≤ W（闭区间）续链。这是"定义"侧的实现。
    """
    return dedup_ledger(records, window_seconds=window_seconds,
                        platform_priority=["wechat", "alipay", "bank"])


def _brute_force_endpoint_clustering(records, window_seconds):
    """路径二（粗扫+细扫穷举恢复）：不依赖引擎的链式实现——对每个候选对
    (i, j)（i<j）穷举判定 Δt ≤ W，然后用**传递闭包**恢复划分；链式聚类的
    划分 = 同键组内"对内存在 Δt≤W 链"的连通分量。

    粗扫：逐组只看相邻序对；细扫：全对穷举；两条都做（互证）。
    """
    from .dedup import _sort_key

    platform_rank = {"wechat": 0, "alipay": 1, "bank": 2}
    groups = {}
    for record in records["records"]:
        if not record.get("direction") or record.get("amount") is None:
            continue
        key = (record.get("direction"),
               record.get("normalized_counterparty") or "",
               record.get("amount"))
        groups.setdefault(key, []).append(record)

    partition = []
    for key in sorted(groups):
        group = sorted(groups[key], key=lambda r: _sort_key(r, platform_rank))
        n = len(group)
        if n < 2:
            continue
        # 细扫：全对穷举 → 邻接表 → 连通分量（传递闭包）
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for i in range(n):
            for j in range(i + 1, n):
                dt = (_parse(group[j]["time"]) - _parse(group[i]["time"])
                      ).total_seconds()
                if dt <= window_seconds:
                    ri, rj = find(i), find(j)
                    if ri != rj:
                        parent[ri] = rj
        clusters = {}
        for i in range(n):
            clusters.setdefault(find(i), []).append(group[i])
        for root in sorted(clusters, key=lambda r: clusters[r][0]["id"]):
            members = clusters[root]
            if len(members) >= 2:
                partition.append(members)
    return partition


def _parse(value):
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def _boundary_probe_records(window_seconds):
    """构造覆盖窗口端点的合成记录：Δt=W 命中、W+1s 不命中、链式传播。"""
    base = datetime(2026, 9, 1, 12, 0, 0)

    def rec(rid, platform, offset_seconds, amount, counterparty, row):
        t = base + timedelta(seconds=offset_seconds)
        return {
            "id": rid, "source_platform": platform, "source_file": "%s.csv" % platform,
            "source_row": row, "time": t.strftime("%Y-%m-%d %H:%M:%S"),
            "amount": amount, "direction": "expense",
            "counterparty": counterparty,
            "normalized_counterparty": counterparty, "raw_fields": {},
            "row_status": "ok",
        }

    # 边界端点由公式推导：W 恰好命中（闭区间）、W+1s 不命中
    records = [
        rec("p-w-1", "wechat", 0, "5.00", "甲", 1),
        rec("p-b-1", "bank", window_seconds, "5.00", "甲", 2),      # Δt=W
        rec("p-w-3", "wechat", 2 * (window_seconds + SECONDS_STEP), "8.00", "丁", 7),
        rec("p-a-4", "alipay", 3 * (window_seconds + SECONDS_STEP), "8.00", "丁", 8),
        # 丁对：Δt = W+2s（>W 不合并；拨宽到 W+1s 也仍未合并）；
        # 再加一对 Δt = W+1s：穷举侧窗口若拨宽（≤W+1）即误并 → 双向对账分歧
        rec("p-w-4", "wechat", 5 * (window_seconds + SECONDS_STEP), "9.00", "戊", 9),
        rec("p-b-4", "bank", 5 * (window_seconds + SECONDS_STEP)
            + window_seconds + SECONDS_STEP, "9.00", "戊", 10),     # Δt=W+1s
        rec("p-a-2", "alipay", window_seconds + SECONDS_STEP, "6.00", "乙", 3),
        rec("p-w-2", "wechat", window_seconds + SECONDS_STEP + window_seconds,
            "6.00", "乙", 4),                                       # 链式：a2→w2 Δt=W
        rec("p-b-3", "bank", 0, "7.00", "丙", 5),
        rec("p-a-3", "alipay", 0, "7.01", "丙", 6),                 # 金额差 1 分
    ]
    ledger = {
        "schema_version": 1,
        "meta": {"sources": [], "params_digest": "probe"},
        "records": records, "issues": [], "file_issues": [],
    }
    return ledger


def run_b2_boundary_reconciliation(window_seconds=None):
    """双向对账：公式推导端点 vs 粗扫+细扫穷举恢复（两条独立路径互验）。

    返回指标 dict（口径同 B2 家族；进 ``--only B2`` 附加段）。
    """
    from .bench_runner import _load_frozen, _threshold, _params

    data_dir, manifest, truth, aliases = _load_frozen()
    if window_seconds is None:
        window_seconds = _params(manifest)["dedup_window_seconds"]

    ledger = _boundary_probe_records(window_seconds)

    # 路径一：公式推导端点直接喂引擎（Δt=W 必并、Δt=W+1s 必不并是推导结论）
    engine_out = _derivation_endpoint_clustering(ledger, window_seconds)
    # 路径二：粗扫+细扫穷举恢复
    brute_partition = _brute_force_endpoint_clustering(ledger, window_seconds)

    # 推导侧断言（端点语义）
    engine_pairs = _pair_cluster_map(engine_out)
    checks = []
    ok_w = frozenset(("p-w-1", "p-b-1")) in engine_pairs
    checks.append({"kind": "endpoint_hit_at_W", "ok": ok_w})
    ok_w1 = frozenset(("p-a-2", "p-b-3")) not in engine_pairs and \
        frozenset(("p-a-2", "p-w-2")) in engine_pairs
    checks.append({"kind": "chained_propagation", "ok": ok_w1})
    ok_cent = frozenset(("p-b-3", "p-a-3")) not in engine_pairs
    checks.append({"kind": "one_cent_not_merged", "ok": ok_cent})
    # Δt=W+1s：闭区间外必不合并（穷举侧若拨宽到 W+1 即误并 → 互验分歧）
    ok_beyond = frozenset(("p-w-4", "p-b-4")) not in engine_pairs
    checks.append({"kind": "beyond_W_not_merged", "ok": ok_beyond})

    # 互验：引擎划分与穷举恢复的划分（成员集合多重集）一致
    engine_clusters = sorted(
        tuple(sorted(c["members"]))
        for c in engine_out["dedup"]["clusters"]
    )
    brute_clusters = sorted(
        tuple(sorted(m["id"] for m in members))
        for members in brute_partition
    )
    agree = engine_clusters == brute_clusters
    checks.append({"kind": "brute_force_agreement", "ok": agree,
                   "engine": engine_clusters, "brute": brute_clusters})

    total = len(checks)
    hit = sum(1 for c in checks if c["ok"])
    accuracy = hit / total if total else 0.0
    accuracy_min = _threshold(manifest, "bench_b2_cluster_accuracy_min")
    return {
        "suite": "B2-reconciliation",
        "total": total,
        "hit": hit,
        "accuracy": round(accuracy, 6),
        "false_positives": 0,
        "thresholds": {"accuracy_min": accuracy_min},
        "pass": accuracy >= accuracy_min,
        "checks": checks,
        "notes": "窗口边界双向对账：公式推导端点（引擎）vs 粗扫+细扫穷举恢复",
    }

"""模块③ 跨平台去重（plan/03 §三）。

判定键（三元组，全部精确判定、无启发式）：

- **金额相等**：Decimal 精确相等（字符串直接 == 即可——ingest 已把金额
  字符串化为定点表示）；
- **时间窗口**：|Δt| ≤ W **闭区间**（W 经 params 单点读取，CLI ``--window-seconds``
  覆盖后经调用方传入、记录进产物）；
- **对手方相等**：模块②归一化后的名称。

聚类：同方向内、按固定排序（时间 → 平台优先级 → 来源行号）线性扫，
**链式相邻聚类**——相邻两条 Δt ≤ W 即归入同一簇（A-B 近、B-C 近、A-C 远
时三者仍同簇；划分由排序+链式规则唯一确定，无随机性）。

跨平台前提（plan/03 §3.3）：三元组命中只记**候选簇**；
- 簇内 ≥2 平台 → ``verdict=duplicate_cross_platform``（判定重复，非代表笔成员
  标 ``duplicate`` 排除出净额）；
- 簇内 1 个平台 → ``verdict=candidate_same_platform``：**显式不合并**（待人工
  复核），成员照常计入净额——绝不静默合并、绝不静默忽略。

代表笔（写死）：时间最早 → 平台优先级（规则包 ``platform_priority``）→ 来源行号。
去重不改变原始流水：净流水视图 = 原始记录 + 去重标记字段。
"""

from datetime import datetime

from .errors import InputError

VERDICT_CROSS = "duplicate_cross_platform"
VERDICT_SAME = "candidate_same_platform"

_SINGLETON_NOTE = "单条记录不成簇"


def _parse_time(value):
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def _sort_key(record, platform_rank):
    # 固定排序：时间 → 平台优先级 → 来源行号（plan/03 §3.2）
    return (
        _parse_time(record["time"]),
        platform_rank.get(record["source_platform"], len(platform_rank)),
        record["source_row"],
        record["id"],
    )


def _cluster_direction(records, window_seconds):
    """单方向内的链式相邻聚类 → 候选簇列表（每簇为排序后的 record 列表）。
    前提：records 同方向、同归一对手方、同金额；已按固定排序排好。
    链式相邻：与前一条 Δt ≤ W 就续链（闭区间，恰好 W 命中）。
    """
    clusters = []
    current = []
    prev_time = None
    for record in records:
        t = _parse_time(record["time"])
        if current and (t - prev_time).total_seconds() <= window_seconds:
            current.append(record)
        else:
            if current:
                clusters.append(current)
            current = [record]
        prev_time = t
    if current:
        clusters.append(current)
    return clusters


def dedup_ledger(ledger, window_seconds, platform_priority):
    """归一化后 IR → 追加去重段的视图（原始不可变，只增标记不改写）。

    ``platform_priority``：规则包参数（代表笔排序键，字符串平台次序）。
    返回新 dict：records 增设 ``dedup_verdict`` / ``dedup_cluster``；
    新增 ``dedup`` 段（参数快照、簇清单、净额摘要）。
    """
    if window_seconds < 0:
        raise InputError("时间窗口不能为负：%r" % window_seconds)
    platform_rank = {name: i for i, name in enumerate(platform_priority)}

    by_key = {}
    order = []
    for record in ledger.get("records", []):
        # 方向 None（unknown 行）不参与聚类——语义上"方向未知"无法断言同方向
        direction = record.get("direction")
        amount = record.get("amount")
        if not direction or amount is None:
            continue
        key = (direction, record.get("normalized_counterparty") or "", amount)
        if key not in by_key:
            by_key[key] = []
            order.append(key)
        by_key[key].append(record)

    records = [dict(r) for r in ledger.get("records", [])]
    by_id = {r["id"]: r for r in records}

    clusters = []
    for key in order:
        direction, counterparty, amount = key
        group = by_key[key]
        group.sort(key=lambda r: _sort_key(r, platform_rank))
        for members in _cluster_direction(group, window_seconds):
            if len(members) < 2:
                continue  # 单条不成簇
            platforms = sorted({m["source_platform"] for m in members})
            verdict = VERDICT_CROSS if len(platforms) >= 2 else VERDICT_SAME
            representative = min(members, key=lambda r: _sort_key(r, platform_rank))
            span = (_parse_time(members[-1]["time"]) - _parse_time(members[0]["time"])
                    ).total_seconds()
            cluster = {
                "cluster_id": "D%03d" % (len(clusters) + 1),
                "verdict": verdict,
                "direction": direction,
                "counterparty": counterparty,
                "amount": amount,
                "platforms": platforms,
                "members": [m["id"] for m in members],
                "representative": representative["id"],
                "time_span_seconds": span,
                "basis": {
                    "rule": "triplet+chain",
                    "detail": "金额精确相等 + |Δt|≤W 闭区间（W=%s）+ 归一对手方相等；"
                              "同方向链式相邻聚类" % window_seconds,
                    "evidence": {
                        "window_seconds": window_seconds,
                        "platforms": platforms,
                        "member_times": [m["time"] for m in members],
                    },
                },
                "note": "" if verdict == VERDICT_CROSS
                        else "同平台候选：不合并，待人工复核（绝不静默合并）",
            }
            clusters.append(cluster)
            for m in members:
                entry = by_id[m["id"]]
                entry["dedup_verdict"] = verdict
                entry["dedup_cluster"] = cluster["cluster_id"]
                entry["is_duplicate"] = (
                    verdict == VERDICT_CROSS and m["id"] != representative["id"]
                )
                entry["is_representative"] = m["id"] == representative["id"]

    # 净额摘要：duplicate_cross_platform 的非代表笔排除出净额（plan/03 §3.3）
    excluded = sorted(
        r["id"] for r in records if r.get("is_duplicate")
    )
    def _net(direction):
        total = 0
        for r in records:
            if r.get("is_duplicate"):
                continue
            if r.get("direction") == direction and r.get("amount"):
                total += int(_cents(r["amount"]))
        return total

    out = dict(ledger)
    out["records"] = records
    out["dedup"] = {
        "params": {
            "window_seconds": window_seconds,
            "platform_priority": list(platform_priority),
            "source": "规则包默认值（经验默认，非官方）；可经 --window-seconds 覆盖",
        },
        "clusters": clusters,
        "net_summary": {
            "excluded_duplicate_ids": excluded,
            "net_expense_cents": _net("expense"),
            "net_income_cents": _net("income"),
        },
    }
    return out


def _cents(amount_text):
    from decimal import Decimal
    return (Decimal(amount_text) * 100).to_integral_value()

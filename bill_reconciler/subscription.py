"""模块⑤ 周期性订阅识别（plan/03 §5.1）。

判定 = 商户 + 金额 + 日期间隔的**规则判定**（确定性、可证伪、无启发式）：

1. 只对 ``semantic_label == 消费`` 的支出行判定（plan/03 §4.3 口径；
   语义未知/非消费行绝不进入订阅判定——干扰例由 B4 对账锁定）；
2. 同商户（归一化后）+ 同金额分组，组内按时间排序做**链式相邻聚类**；
3. 周期锚定：链内首个满足「连续 min_repeats 期、相邻间隔都落在周期表
   任一 period 的 interval ± tolerance 天内」的窗格作**种子**（min_repeats
   与周期表来自规则包，代码零内联）；
4. 从种子锚点逐期**续链**：下一笔落在 interval ± tolerance 内即续；
   允许**漏一期**（间隔 ≈ 2×interval ± tolerance 内补链，期次记录中断）；
5. **涨价续链**（M4 定稿）：A 链尾笔与 B 链首笔（同商户、金额不同且变化
   ≥ price_change_min_percent、间隔落周期容差带内）→ 合并为同一订阅——
   前段锚定周期、涨价点后按新金额继续；
6. **涨价追踪只输出观测到的变动**（前后金额 + 日期），不做预测；
   间隔超带的金额变动视为"序列结束 + 新序列"（非涨价续链，不得并簇）。

全部参数经 ``params.py`` 唯一访问点传入；逐条依据随产物落盘。
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation

DAY_SECONDS = 86400


def _parse_time(value):
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def _days_floor(seconds):
    """间隔秒数 → 天数（向下取整；不足一天按 0 天计，避免边界误判）。"""
    return int(seconds // DAY_SECONDS)


def _percent_change(old_amount, new_amount):
    """金额变化百分比（Decimal 精确计算，字符串进出）。"""
    old = Decimal(old_amount)
    new = Decimal(new_amount)
    if old == 0:
        return None
    delta = abs(new - old)
    return delta / old * Decimal(100)


def _price_change_hit(old_amount, new_amount, min_percent):
    pct = _percent_change(old_amount, new_amount)
    if pct is None:
        return False
    return pct >= Decimal(str(min_percent))


def _period_bands(period_table, default_tolerance_days):
    """周期表 → [(period_id, interval_days, tolerance_days)]。

    周期条目未单独给 tolerance_days 时回落到规则包默认容差（参数单点传入）。
    """
    bands = []
    for period in period_table:
        tolerance = period.get("tolerance_days", default_tolerance_days)
        bands.append((period["id"], int(period["interval_days"]), int(tolerance)))
    return bands


def _match_period(days, bands):
    """间隔天数命中任一周期容差带 → 该 period 条目；否则 None。"""
    for period_id, interval, tolerance in bands:
        if abs(days - interval) <= tolerance:
            return {"period_id": period_id, "interval_days": interval,
                    "gap_days": days}
    return None


def _group_key(record):
    merchant = (record.get("normalized_counterparty")
                or record.get("counterparty") or "")
    return merchant, record.get("amount")


def _chain_gap_limit_days(bands):
    """链式相邻聚类的续链上限：允许漏一期（2×最长周期 + 容差）。"""
    longest = max(interval + tolerance for _, interval, tolerance in bands)
    return 2 * longest


def _chain_groups(records, bands):
    """同商户同金额组内链式相邻聚类（日距 ≤ 漏一期上限即续链）。"""
    limit = _chain_gap_limit_days(bands)
    chains = []
    current = []
    prev_time = None
    for record in records:
        t = _parse_time(record["time"])
        if current and (_days_floor((t - prev_time).total_seconds()) <= limit):
            current.append(record)
        else:
            if current:
                chains.append(current)
            current = [record]
        prev_time = t
    if current:
        chains.append(current)
    return chains


def _pair_in_band(days, bands):
    """相邻对间隔落单期容差带 → (hit, None)；否则 (None, bridge_hit)。"""
    hit = _match_period(days, bands)
    if hit is not None:
        return hit, None
    for period_id, interval, tolerance in bands:
        if abs(days - 2 * interval) <= tolerance:
            return None, {"period_id": period_id, "interval_days": interval,
                          "gap_days": days}
    return None, None


def _anchor_seed(chain, min_repeats, bands):
    """链内首个「连续 min_repeats 期相邻间隔都落带内（允许漏一期）」的窗格。

    返回 (seed_start_index, seed_end_index, first_hit, seed_gaps) 或 None。
    种子窗允许漏一期：漏期对的间隔落在 ≈2×interval ± tolerance 带内
    （SUB-E 形态：3/4/5 月连续、6 月漏、7/8 月续——种子窗跨漏期仍成立）。
    """
    count = len(chain)
    for start in range(0, count - min_repeats + 1):
        window = chain[start:start + min_repeats]
        first_hit = None
        seed_gaps = []
        ok = True
        for k, (prev, cur) in enumerate(zip(window, window[1:])):
            days = _days_floor(
                (_parse_time(cur["time"]) - _parse_time(prev["time"])).total_seconds()
            )
            hit, bridged = _pair_in_band(days, bands)
            if hit is None and bridged is None:
                ok = False
                break
            if first_hit is None:
                first_hit = hit or bridged
            if bridged is not None:
                seed_gaps.append({
                    "after_entry": prev["id"],
                    "resumed_entry": cur["id"],
                    "missed_intervals": 1,
                    "gap_days": bridged["gap_days"],
                    "period_id": bridged["period_id"],
                })
        if ok:
            return start, start + min_repeats - 1, first_hit, seed_gaps
    return None


def _follow_chain(chain, seed_start, seed_end, bands, seed_gaps):
    """种子锚点起逐期续链 → 成员下标序列 + gaps（0 基下标）。"""
    members = list(range(seed_start, seed_end + 1))
    gaps = list(seed_gaps)
    index = seed_end
    while True:
        advanced = False
        base = _parse_time(chain[index]["time"])
        for j in range(index + 1, len(chain)):
            days = _days_floor((_parse_time(chain[j]["time"]) - base).total_seconds())
            hit, bridged = _pair_in_band(days, bands)
            if hit is None and bridged is None:
                continue
            members.append(j)
            if bridged is not None:
                gaps.append({
                    "after_entry": chain[index]["id"],
                    "resumed_entry": chain[j]["id"],
                    "missed_intervals": 1,
                    "gap_days": bridged["gap_days"],
                    "period_id": bridged["period_id"],
                })
            index = j
            advanced = True
            break
        if not advanced:
            break
    return members, gaps


def _price_changes(chain, members, min_percent, bands):
    """相邻期对中观测到的金额变动（间隔落单期带内才算期对；≥阈值记变动）。"""
    changes = []
    for prev_idx, cur_idx in zip(members, members[1:]):
        prev = chain[prev_idx]
        cur = chain[cur_idx]
        if prev["amount"] == cur["amount"]:
            continue
        days = _days_floor(
            (_parse_time(cur["time"]) - _parse_time(prev["time"])).total_seconds()
        )
        # 只有单期间隔才算"相邻期对"——漏期补链对（≈2×interval）不是期对，
        # 涨价口径只认相邻期（防漏期被误记为涨价，M4 定稿）
        if _match_period(days, bands) is None:
            continue
        if _price_change_hit(prev["amount"], cur["amount"], min_percent):
            changes.append({
                "entry": cur["id"],
                "from_amount": prev["amount"],
                "to_amount": cur["amount"],
                "from_time": prev["time"],
                "to_time": cur["time"],
                "change_percent": str(_percent_change(prev["amount"], cur["amount"])),
            })
    return changes


def _merge_price_chains(chains_data, min_repeats, min_percent, bands):
    """涨价续链：A 链尾笔与 B 链首笔同商户、金额变化 ≥ 阈值、间隔落单期带内。

    B 允许是**未锚定链**（笔数不足 min_repeats——涨价后的新金额链天然只有
    1-2 笔）：只能被锚定链收编（B 不发起合并），合并后并集重新锚定+续链；
    间隔超带的金额变动不并簇（序列结束 + 新序列，两段各自独立判定）。
    """
    changed = True
    while changed:
        changed = False
        for i in range(len(chains_data)):
            if changed:
                break
            a = chains_data[i]
            if not a["members"]:
                continue
            tail = a["chain"][a["members"][-1]]
            for j in range(len(chains_data)):
                if j == i:
                    continue
                b = chains_data[j]
                if not b["chain"]:
                    continue
                head = b["chain"][0]
                if head["amount"] == tail["amount"]:
                    continue
                days = _days_floor(
                    (_parse_time(head["time"]) - _parse_time(tail["time"])).total_seconds()
                )
                if _match_period(days, bands) is None:
                    continue
                if not _price_change_hit(tail["amount"], head["amount"], min_percent):
                    continue
                # 成员并集 → 新子链（时间去重排序）
                seen_ids = set()
                union = []
                for record in sorted(a["chain"] + b["chain"],
                                     key=lambda r: (_parse_time(r["time"]), r["id"])):
                    if record["id"] in seen_ids:
                        continue
                    seen_ids.add(record["id"])
                    union.append(record)
                seed = _anchor_seed(union, min_repeats, bands)
                prior_gaps = a["gaps"] + b["gaps"]
                if seed is not None:
                    s, e, seed_hit, sg = seed
                    members, gaps = _follow_chain(union, s, e, bands, sg)
                    have = {g["resumed_entry"] for g in prior_gaps}
                    gaps = prior_gaps + [g for g in gaps
                                         if g["resumed_entry"] not in have]
                    period_hit = seed_hit
                else:
                    # 锚定退化（并集跨漏期窗过宽）：保留全部并集成员，
                    # 周期沿用前段锚点——成员不丢，依据如实
                    members = list(range(len(union)))
                    gaps = prior_gaps
                    period_hit = a["period_hit"]
                chains_data[i] = {
                    "chain": union,
                    "members": members,
                    "gaps": gaps,
                    "period_hit": period_hit,
                    "gapped_head": False,
                }
                del chains_data[j]
                changed = True
                break
    return chains_data


def detect_subscriptions(ledger, min_repeats, price_change_min_percent,
                         period_table, default_tolerance_days):
    """classified ledger → 订阅清单 + 干扰行清单（纯函数，不改输入）。"""
    bands = _period_bands(period_table, default_tolerance_days)

    candidates = []
    for record in ledger.get("records", []):
        if record.get("semantic_label") != "消费":
            continue
        if record.get("direction") != "expense":
            continue
        amount = record.get("amount")
        if not amount:
            continue
        try:
            Decimal(amount)
        except (InvalidOperation, ValueError):
            continue
        candidates.append(record)

    # 商户分组（金额只做链内子分组——涨价续链需要跨金额可见，M4 定稿）
    by_merchant = {}
    for record in candidates:
        merchant = (record.get("normalized_counterparty")
                    or record.get("counterparty") or "")
        by_merchant.setdefault(merchant, []).append(record)

    subscriptions = []
    distractor_entries = []
    for merchant in sorted(by_merchant):
        group = sorted(by_merchant[merchant],
                       key=lambda r: (_parse_time(r["time"]), r["id"]))
        # 商户内先按时间做链式相邻聚类（链=时间相近的一段），链内再按
        # 金额子分组锚定——跨金额的涨价续链在合并步完成
        merchant_chains = _chain_groups(group, bands)

        chains_data = []
        for chain in merchant_chains:
            for amount in sorted({r["amount"] for r in chain}):
                sub_chain = [r for r in chain if r["amount"] == amount]
                seed = _anchor_seed(sub_chain, min_repeats, bands)
                if seed is None:
                    # 未锚定子链（笔数不足或间隔不合带）保留进池：可能被
                    # 锚定链尾的涨价合并收编；终态仍未锚定 → 干扰行
                    chains_data.append({
                        "chain": sub_chain, "members": [], "gaps": [],
                        "period_hit": None, "gapped_head": False,
                    })
                    continue
                seed_start, seed_end, first_hit, seed_gaps = seed
                members, gaps = _follow_chain(sub_chain, seed_start, seed_end,
                                              bands, seed_gaps)
                chains_data.append({
                    "chain": sub_chain,
                    "members": members,
                    "gaps": gaps,
                    "period_hit": first_hit,
                    "gapped_head": False,
                })

        # 未锚定链不过滤（可能被涨价合并收编）；合并后终态仍未锚定 → 干扰行
        chains_data = _merge_price_chains(chains_data, min_repeats,
                                          price_change_min_percent, bands)

        for item in chains_data:
            if not item["members"]:
                distractor_entries.extend(r["id"] for r in item["chain"])
                continue
            chain = item["chain"]
            members = item["members"]
            changes = _price_changes(chain, members,
                                     price_change_min_percent, bands)
            entries = [chain[i]["id"] for i in members]
            subscriptions.append({
                "merchant": merchant,
                "amounts": sorted({chain[i]["amount"] for i in members}),
                "period_id": item["period_hit"]["period_id"],
                "repeats": len(members),
                "entries": entries,
                "gaps": item["gaps"],
                "price_changes": changes,
                "first_time": chain[members[0]]["time"],
                "last_time": chain[members[-1]]["time"],
                "basis": {
                    "rule": "merchant+amount+interval",
                    "detail": (
                        "同商户链式聚类（金额切换=涨价续链）；种子=连续 %d 期"
                        "落在周期 %s 容差带（允许漏一期，已显式记录）"
                        % (min_repeats, item["period_hit"]["period_id"])
                    ),
                    "evidence": {
                        "period_table_hit": item["period_hit"],
                        "min_repeats": min_repeats,
                        "gap_days_chain": [
                            _days_floor(
                                (_parse_time(chain[b]["time"])
                                 - _parse_time(chain[a]["time"])).total_seconds()
                            )
                            for a, b in zip(members, members[1:])
                        ],
                    },
                },
            })

    subscriptions.sort(key=lambda s: (s["merchant"], s["first_time"]))
    for i, sub in enumerate(subscriptions, start=1):
        sub["subscription_id"] = "SUB%03d" % i

    # 干扰行：消费支出里未进入任何订阅的（非周期相似金额等）
    subscribed = {entry for sub in subscriptions for entry in sub["entries"]}
    distractors = []
    for record in candidates:
        if record["id"] not in subscribed:
            distractors.append({
                "id": record["id"],
                "merchant": (record.get("normalized_counterparty")
                             or record.get("counterparty") or ""),
                "amount": record["amount"],
                "time": record["time"],
            })
    distractors.sort(key=lambda d: d["id"])

    return subscriptions, distractors


def detect_subscription_ledger(ledger, min_repeats, price_change_min_percent,
                               period_table, default_tolerance_days):
    """IR（classify 后）→ 追加订阅段的视图（原始不可变，只增不改）。

    每条订阅成员 record 增设 ``subscription_id``；新增 ``subscription`` 段
    （参数快照、订阅清单、非周期干扰行清单）。
    """
    subscriptions, distractors = detect_subscriptions(
        ledger,
        min_repeats=min_repeats,
        price_change_min_percent=price_change_min_percent,
        period_table=period_table,
        default_tolerance_days=default_tolerance_days,
    )
    records = [dict(r) for r in ledger.get("records", [])]
    by_id = {r["id"]: r for r in records}
    for sub in subscriptions:
        for entry in sub["entries"]:
            by_id[entry]["subscription_id"] = sub["subscription_id"]

    out = dict(ledger)
    out["records"] = records
    out["subscription"] = {
        "params": {
            "min_repeats": min_repeats,
            "price_change_min_percent": price_change_min_percent,
            "period_table": period_table,
            "default_tolerance_days": default_tolerance_days,
            "source": "规则包默认值（经验默认，非官方）",
        },
        "subscriptions": subscriptions,
        "distractors": distractors,
        "note": "只对语义=消费的支出行判定；涨价只记录观测到的变动，不做预测",
    }
    return out

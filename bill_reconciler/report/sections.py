"""报告结构化章节（单一渲染源，plan/03 §5.2）。

``build_sections(ledger)`` 从流水线产物提取**结构化章节**——HTML 渲染器与
JSON 渲染器各自消费同一份章节（"两格式内容一致"是结构性质，非人工比对）。

报告只呈现引擎结论，不做二次计算：金额/净额/分布全部取自 ledger 各段
（dedup.net_summary / classify.distribution / subscription.*），本章函数
只做组织与文本化。

章节（plan/03 §5.2 定稿）：
1. 概览 2. 真实支出汇总（未知单列区间）3. 去重簇明细
4. 语义标签分布 5. 订阅清单 + 涨价记录 6. 异常/未知清单
7. 参数来源块（值 + 来源 + 覆盖状态） 8. 隐私声明 + 免责声明
"""

SCHEMA_VERSION = 1

_PRIVACY_LINES = [
    "纯本地处理：账单文件与结论不离开本机，零上传、零遥测、零外链。",
    "本报告由离线流水线生成（单文件 HTML，断网可开）；无网络库参与运行。",
]

_DISCLAIMER_LINES = [
    "去重与语义判定是确定性规则输出，『跨平台重复』以窗口+金额+对手方三元组"
    "与跨平台前提为准；同平台候选为显式待人工复核项，不自动合并。",
    "全部参数默认值为经验默认（非官方口径），用户可经 CLI 覆盖；"
    "实际生效值以参数来源块为准。",
    "『未知』语义行未计入真实支出主口径，报告给出计入上限供人工评估。",
]


def _cents_to_yuan(cents):
    return "%d.%02d" % (cents // 100, cents % 100)


def _amount(amount_text):
    return str(amount_text) if amount_text is not None else "-"


def build_sections(ledger):
    """ledger（run 产物）→ 结构化章节 dict（渲染器唯一输入）。"""
    meta = ledger.get("meta", {})
    records = ledger.get("records", [])
    dedup = ledger.get("dedup", {})
    classify = ledger.get("classify", {})
    subscription = ledger.get("subscription", {})

    platforms = {}
    for source in meta.get("sources", []):
        platforms[source["platform"]] = platforms.get(source["platform"], 0) + \
            source["rows_ok"]
    times = [r["time"] for r in records if r.get("time")]
    net = dedup.get("net_summary", {})

    overview = {
        "title": "一、概览",
        "files": [
            {
                "file": s["file"], "platform": s["platform"],
                "encoding": s["encoding"], "rows_ok": s["rows_ok"],
                "rows_invalid": s["rows_invalid"],
                "rows_unknown": s["rows_unknown"],
            }
            for s in meta.get("sources", [])
        ],
        "records_total": len(records),
        "rows_by_platform": dict(sorted(platforms.items())),
        "time_range": {
            "from": min(times) if times else None,
            "to": max(times) if times else None,
        },
        "params_digest": meta.get("params_digest"),
        "ruleset_version": meta.get("ruleset_version"),
        "pipeline_stages": meta.get("pipeline", {}).get("stages", []),
    }

    clusters = dedup.get("clusters", [])
    cross = [c for c in clusters if c["verdict"] == "duplicate_cross_platform"]
    same = [c for c in clusters if c["verdict"] == "candidate_same_platform"]
    real_spend = {
        "title": "二、真实支出汇总",
        "basis": (
            "主口径 = 已判定『消费』的支出净额 − 已判定『退款』的入账；"
            "本人转账 / AA回款 / 报销不计入支出侧；『未知』单列不混入。"
        ),
        "net_expense": _cents_to_yuan(net.get("net_expense_cents", 0)),
        "net_income": _cents_to_yuan(net.get("net_income_cents", 0)),
        "excluded_duplicates": net.get("excluded_duplicate_ids", []),
    }

    dedup_section = {
        "title": "三、去重簇明细",
        "params": dedup.get("params", {}),
        "clusters": [
            {
                "cluster_id": c["cluster_id"],
                "verdict": c["verdict"],
                "direction": c["direction"],
                "counterparty": c["counterparty"],
                "amount": c["amount"],
                "platforms": c["platforms"],
                "members": c["members"],
                "representative": c.get("representative"),
                "time_span_seconds": c.get("time_span_seconds"),
                "note": c.get("note", ""),
            }
            for c in clusters
        ],
        "candidate_same_platform": [c["cluster_id"] for c in same],
        "duplicate_cross_platform": [c["cluster_id"] for c in cross],
    }

    distribution = classify.get("distribution", {})
    unknown_rows = classify.get("unknown_rows", [])
    unknown_total = sum(
        int(Decimal_amount(r.get("amount"))) for r in unknown_rows
        if r.get("amount")
    )
    semantic = {
        "title": "四、语义标签分布",
        "distribution": distribution,
        "unknown_count": len(unknown_rows),
        "unknown_amount_total": _cents_to_yuan(unknown_total),
        "unknown_upper_bound": _cents_to_yuan(unknown_total),
        "note": classify.get("note", ""),
    }

    subs = subscription.get("subscriptions", [])
    subscription_section = {
        "title": "五、周期性订阅识别",
        "params": subscription.get("params", {}),
        "subscriptions": [
            {
                "subscription_id": s["subscription_id"],
                "merchant": s["merchant"],
                "amounts": s["amounts"],
                "period_id": s["period_id"],
                "repeats": s["repeats"],
                "entries": s["entries"],
                "gaps": s["gaps"],
                "price_changes": s["price_changes"],
                "first_time": s["first_time"],
                "last_time": s["last_time"],
            }
            for s in subs
        ],
        "distractors": subscription.get("distractors", []),
        "note": subscription.get("note", ""),
    }

    issues = ledger.get("issues", [])
    file_issues = ledger.get("file_issues", [])
    issues_section = {
        "title": "六、异常与未知清单",
        "row_issues": [
            {
                "row_id": i.get("row_id"), "kind": i["kind"],
                "code": i.get("code"), "detail": i["detail"],
            }
            for i in issues
        ],
        "file_issues": [
            {"file": f["file"], "code": f["code"], "detail": f["detail"]}
            for f in file_issues
        ],
        "unknown_rows": unknown_rows,
    }

    params_section = {
        "title": "七、参数来源块",
        "params_digest": meta.get("params_digest"),
        "ruleset_version": meta.get("ruleset_version"),
        "entries": _param_entries(ledger),
    }

    closing = {
        "title": "八、隐私声明与免责声明",
        "privacy": list(_PRIVACY_LINES),
        "disclaimer": list(_DISCLAIMER_LINES),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "bill-reconciler-report",
        "sections": {
            "overview": overview,
            "real_spend": real_spend,
            "dedup": dedup_section,
            "semantic": semantic,
            "subscription": subscription_section,
            "issues": issues_section,
            "params": params_section,
            "closing": closing,
        },
    }


def _param_entries(ledger):
    """参数来源块条目：每参数 值/来源/覆盖状态（只从产物段读，不重算）。"""
    entries = []
    dedup_params = ledger.get("dedup", {}).get("params", {})
    if dedup_params.get("window_seconds") is not None:
        entries.append({
            "param": "dedup_window_seconds",
            "value": dedup_params["window_seconds"],
            "source": dedup_params.get("source", "规则包默认值"),
            "overridden": False,
        })
    sub_params = ledger.get("subscription", {}).get("params", {})
    for key in ("min_repeats", "price_change_min_percent", "period_table",
                "default_tolerance_days"):
        if key in sub_params:
            entries.append({
                "param": key,
                "value": sub_params[key],
                "source": sub_params.get("source", "规则包默认值"),
                "overridden": False,
            })
    return entries


def Decimal_amount(amount_text):
    """金额字符串 → 分（整数）；不可解析 → 0（呈现层不做判定）。"""
    from decimal import Decimal, InvalidOperation

    try:
        return int((Decimal(str(amount_text)) * 100).to_integral_value())
    except (InvalidOperation, ValueError):
        return 0

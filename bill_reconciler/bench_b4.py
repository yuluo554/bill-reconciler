"""内置基准 B4 订阅识别套件（plan/03 §九）。

真值对账（样本驱动）：``expect_subscription`` 6 形态（月付/涨价/季付/
年付/中断/非周期干扰）——5 订阅成员集合 + 涨价记录 + 中断续接 + 干扰行
不判订阅。指标 = 套件级 P/R/F1（订阅实例为单元）。门槛
``bench_b4_f1_min`` 读规则包（数据非代码）。
"""

from .errors import InputError


def run_b4(detected=None, rules_env=None):
    """B4 订阅基准：订阅实例级 P/R/F1 + 干扰行检查。

    ``detected`` 可注入 (subscriptions, distractors)（探活用）；
    缺省 = 全量冻结样例跑真引擎。
    """
    from .bench_runner import _load_frozen, _threshold

    data_dir, manifest, truth, column_aliases = (
        _load_frozen() if rules_env is None else rules_env
    )
    if detected is None:
        detected = _real_engine(data_dir, manifest, column_aliases)
    subscriptions, distractors = detected

    expect = truth["expect_subscription"]
    expected = [set(e["entries"]) for e in expect["subscriptions"]]
    observed = [set(s["entries"]) for s in subscriptions]

    matched = 0
    for exp in expected:
        if exp in observed:
            matched += 1
    precision = matched / len(observed) if observed else 0.0
    recall = matched / len(expected) if expected else 0.0
    f1 = (2 * precision * recall / (precision + recall)) \
        if (precision + recall) else 0.0

    # 涨价记录与中断记录对账（实例匹配上的订阅内）
    price_expect = {}
    for e in expect["subscriptions"]:
        for c in e["price_changes"]:
            price_expect[c["entry"]] = (c["from_amount"], c["to_amount"])
    price_observed = {}
    for s in subscriptions:
        for c in s["price_changes"]:
            price_observed[c["entry"]] = (c["from_amount"], c["to_amount"])

    # 干扰行不判订阅（非周期相似金额）
    sub_entries = {entry for s in subscriptions for entry in s["entries"]}
    distractor_hits = []
    for group in expect["non_periodic_distractors"]:
        for entry in group["entries"]:
            if entry in sub_entries:
                distractor_hits.append(entry)

    f1_min = _threshold(manifest, "bench_b4_f1_min")
    passed = f1 >= f1_min and price_observed == price_expect \
        and not distractor_hits
    return {
        "suite": "B4",
        "total": len(expected),
        "hit": matched,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "price_changes_match": price_observed == price_expect,
        "distractor_hits": distractor_hits,
        "thresholds": {"f1_min": f1_min},
        "pass": passed,
        "notes": "订阅实例级 P/R/F1（6 形态）+ 涨价记录对账 + 干扰行不判订阅",
    }


def _param(manifest, param_id):
    for entry in manifest["params"]:
        if entry["id"] == param_id:
            return entry["value"]
    raise InputError("规则包缺少参数 %s（配置错误）" % param_id)


def _real_engine(data_dir, manifest, column_aliases):
    """真引擎：全量冻结样例 → import→normalize→classify→detect。"""
    import json

    from .classify import classify_ledger
    from .ingest.importer import import_files
    from .normalize import normalize_ledger
    from .subscription import detect_subscriptions

    samples = sorted(
        str(p) for p in (data_dir / "samples").iterdir() if p.is_file()
    )
    ledger = import_files(
        samples,
        column_aliases=column_aliases,
        header_k=_param(manifest, "header_locate_k"),
        max_scan_lines=_param(manifest, "header_locate_max_scan_lines"),
    )
    aliases_doc = json.loads(
        (data_dir / "rules" / "aliases.json").read_text(encoding="utf-8")
    )
    ledger = classify_ledger(normalize_ledger(ledger, aliases_doc),
                             _keywords_doc(data_dir))
    return detect_subscriptions(
        ledger,
        min_repeats=_param(manifest, "subscription_min_repeats"),
        price_change_min_percent=_param(manifest, "price_change_min_percent"),
        period_table=_param(manifest, "period_table"),
        default_tolerance_days=_param(
            manifest, "subscription_interval_tolerance_days"),
    )


def _keywords_doc(data_dir):
    import json

    return json.loads(
        (data_dir / "rules" / "keywords.json").read_text(encoding="utf-8")
    )

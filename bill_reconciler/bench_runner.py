"""内置基准（M4 全套接入；plan/03 §九）。

套件注册表：``SUITES``（id → 运行函数）；``--only`` 未知名 exit 2；
退出码：0 达标 / 1 未达标 / 2 用例名或用法错误。

- B1 导入：真值 ``expect_import`` vs 解析结果，行级三态字段级对账；
- B2 去重：真值 ``expect_dedup`` 簇判定 + must_not_merge 误报
  （``bench_b2``；含窗口边界**双向对账** B2-reconciliation）；
- B3 语义：真值 ``expect_semantic`` 逐行标签 + 未知可区分性一票否决；
- B4 订阅：真值 ``expect_subscription`` 实例级 P/R/F1 + 涨价/干扰对账；
- 探活（可证伪）：每套件注入缺陷 → 基准必须报未达标（``PROBES``）；
- 门槛读规则包（门槛是数据不是代码）；真值只存输入与期望。

样本驱动与规则驱动分层：B2 的规则驱动层（窗口边界端点推导 + 穷举恢复）
不读真值库，专治"样本没覆盖的端点"。
"""

import json

from .datadir import require_data_dir
from .errors import InputError
from .ingest.importer import import_files


def _load_frozen():
    data_dir = require_data_dir()
    manifest = json.loads(
        (data_dir / "rules" / "manifest.json").read_text(encoding="utf-8")
    )
    truth = json.loads(
        (data_dir / "truth" / "truth.json").read_text(encoding="utf-8")
    )
    aliases_doc = json.loads(
        (data_dir / "rules" / "aliases.json").read_text(encoding="utf-8")
    )
    return data_dir, manifest, truth, aliases_doc["column_aliases"]


def _params(manifest):
    return {p["id"]: p["value"] for p in manifest["params"]}


def _threshold(manifest, threshold_id):
    """门槛是数据：缺失即配置错误（exit 2 语义）。"""
    for entry in manifest["bench_thresholds"]:
        if entry["id"] == threshold_id:
            return entry["value"]
    raise InputError("规则包缺少基准门槛 %s（配置错误）" % threshold_id)


def _truth_row_map(truth):
    """把 expect_import 展平成 {row_id: (status, code)}。"""
    rows = {}
    for rel, expect in truth["expect_import"].items():
        for row_id, row_expect in expect["rows"].items():
            rows[row_id] = (row_expect["status"], row_expect.get("code"))
    return rows


def _observed_row_map(ledger):
    rows = {}
    for r in ledger["records"]:
        rows[r["id"]] = (r["row_status"], None)
    for issue in ledger["issues"]:
        if issue.get("row_id"):
            # invalid 行在 issues 中给出期望比对的问题码；unknown 行同理
            rows[issue["row_id"]] = (issue["kind"], issue.get("code"))
    return rows


def run_b1(rules_env=None, engine=None):
    """B1 导入基准：全部冻结样例过引擎 → 行级三态逐条对账 → P/R/F1。

    ``engine`` 可注入（探活用：坏引擎必须被对账抓出来）；
    缺省 = 真引擎（ingest.import_files）。
    返回指标 dict（含 ``pass`` 结论与门槛值）。
    """
    data_dir, manifest, truth, aliases = _load_frozen() if rules_env is None else rules_env
    engine = engine or _default_engine(data_dir, aliases, _params(manifest))

    expect_rows = _truth_row_map(truth)
    ledger = engine()
    observed = _observed_row_map(ledger)

    total = len(expect_rows)
    hit = sum(1 for rid, exp in expect_rows.items() if observed.get(rid) == exp)
    precision = hit / total if total else 0.0
    recall = hit / total if total else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    threshold = _threshold(manifest, "bench_b1_row_f1_min")
    mismatches = sorted(
        rid for rid, exp in expect_rows.items() if observed.get(rid) != exp
    )
    return {
        "suite": "B1",
        "total": total,
        "hit": hit,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "threshold": threshold,
        "pass": f1 >= threshold,
        "mismatches": mismatches,
        "notes": "候选实现（M2）：行级三态一致率口径；字段级 P/R 拆分在 M4 细化",
    }


def _default_engine(data_dir, aliases, params):
    """真引擎闭包：全量冻结样例导入。"""

    def engine():
        samples = sorted(
            str(p) for p in (data_dir / "samples").iterdir() if p.is_file()
        )
        return import_files(
            samples,
            column_aliases=aliases,
            header_k=params["header_locate_k"],
            max_scan_lines=params["header_locate_max_scan_lines"],
        )

    return engine


def run_suite_live_probe(suite_id):
    """探活（可证伪）：注入坏引擎 → 基准必须报未达标，否则探活失败。

    返回 (ok, detail)：ok=True 表示探活通过（坏引擎被正确识别为未达标）。
    """
    if suite_id != "B1":
        raise InputError("未知探活套件 %s" % suite_id)
    data_dir, manifest, truth, aliases = _load_frozen()
    params = _params(manifest)
    truth_rows = _truth_row_map(truth)

    def broken_engine():
        """缺陷注入：把全部行标成 invalid（引擎坏 → 对账必须大面积不命中）。"""
        ledger = _default_engine(data_dir, aliases, params)()
        for r in ledger["records"]:
            r["row_status"] = "unknown"
        return ledger

    result = run_b1(rules_env=(data_dir, manifest, truth, aliases), engine=broken_engine)
    # 探活成立 = 注入缺陷后 F1 低于门槛且 mismatches 非空（"基准能红"）
    live = bool((not result["pass"]) and result["mismatches"])
    return live, "注入缺陷后 F1=%.4f（门槛 %.2f），mismatches=%d" % (
        result["f1"], result["threshold"], len(result["mismatches"])
    )


SUITES = {"B1": run_b1}


def _run_b2_wrapped(rules_env=None):
    from .bench_b2 import run_b2, run_b2_boundary_reconciliation

    results = [run_b2(rules_env=rules_env),
               run_b2_boundary_reconciliation()]
    return _combine(results, suite="B2")


def _run_b3_wrapped(rules_env=None):
    from .bench_b3 import run_b3

    return run_b3(rules_env=rules_env)


def _run_b4_wrapped(rules_env=None):
    from .bench_b4 import run_b4

    return run_b4(rules_env=rules_env)


def _combine(results, suite):
    """多段结果（B2 真值 + 双向对账）合成单套件结论（全段达标才达标）。"""
    combined = {
        "suite": suite,
        "pass": all(r["pass"] for r in results),
        "segments": results,
        "notes": "；".join(r.get("notes", "") for r in results),
    }
    for key in ("accuracy", "f1", "false_positives", "total", "hit"):
        values = [r[key] for r in results if key in r]
        if values:
            combined[key] = values if len(values) > 1 else values[0]
    return combined


def run_bench(only=None):
    """运行基准套件 → (结果清单, 退出码)。``only`` 未知名 = 用法错误 exit 2。

    ``only``：套件 id 列表（None = 全部）。返回 (results, exit_code)。
    """
    unknown = [name for name in (only or []) if name not in SUITES]
    if unknown:
        raise InputError(
            "未知基准套件：%s（可用：%s）" % (", ".join(unknown),
                                          ", ".join(sorted(SUITES)))
        )
    names = only or sorted(SUITES)
    results = []
    for name in names:
        try:
            results.append(SUITES[name]())
        except InputError:
            raise
    exit_code = 0 if all(r["pass"] for r in results) else 1
    return results, exit_code


SUITES["B2"] = _run_b2_wrapped
SUITES["B3"] = _run_b3_wrapped
SUITES["B4"] = _run_b4_wrapped


def run_all_probes():
    """全家族探活：每套件注入缺陷 → 必须报未达标（"全绿"可被证伪）。"""
    outcomes = []
    for name in sorted(PROBES):
        ok, detail = PROBES[name]()
        outcomes.append((name, ok, detail))
    return outcomes


def _probe_b1():
    return run_suite_live_probe("B1")


def _probe_b2():
    """缺陷注入：窗口拨错（0 秒）→ 簇判定必须未达标。"""
    from .bench_b2 import run_b2
    from .dedup import dedup_ledger

    data_dir, manifest, truth, column_aliases = _load_frozen()
    from .ingest.importer import import_files
    from .normalize import normalize_ledger

    samples = sorted(
        str(p) for p in (data_dir / "samples").iterdir() if p.is_file()
    )
    ledger = import_files(
        samples,
        column_aliases=column_aliases,
        header_k=_params(manifest)["header_locate_k"],
        max_scan_lines=_params(manifest)["header_locate_max_scan_lines"],
    )
    broken = dedup_ledger(
        normalize_ledger(ledger, _aliases_doc(data_dir)),
        window_seconds=0,
        platform_priority=_params(manifest)["platform_priority"],
    )
    result = run_b2(deduped=broken, rules_env=(data_dir, manifest, truth,
                                               column_aliases))
    live = bool((not result["pass"]) and result["false_positives"] > 0
                or (not result["pass"]))
    return live, "窗口拨 0 后 accuracy=%.4f（应未达标）" % result["accuracy"]


def _probe_b3():
    """缺陷注入：把全部未知行改判消费（fallthrough）→ 必须一票否决。"""
    from .bench_b3 import run_b3
    import json as _json

    data_dir, manifest, truth, column_aliases = _load_frozen()
    aliases_doc = _json.loads(
        (data_dir / "rules" / "aliases.json").read_text(encoding="utf-8")
    )
    from .ingest.importer import import_files
    from .normalize import normalize_ledger
    from .classify import classify_ledger

    samples = sorted(
        str(p) for p in (data_dir / "samples").iterdir() if p.is_file()
    )
    ledger = import_files(
        samples,
        column_aliases=column_aliases,
        header_k=_params(manifest)["header_locate_k"],
        max_scan_lines=_params(manifest)["header_locate_max_scan_lines"],
    )
    classified = classify_ledger(normalize_ledger(ledger, aliases_doc),
                                 _keywords_doc(data_dir))
    for r in classified["records"]:
        if r.get("semantic_label") == "未知":
            r["semantic_label"] = "消费"  # 缺陷注入：未知 fallthrough
    result = run_b3(classified=classified,
                    rules_env=(data_dir, manifest, truth, column_aliases))
    live = bool(not result["pass"] and result["unknown_violations"])
    return live, "未知 fallthrough 注入后 accuracy=%.4f、violations=%d" % (
        result["accuracy"], len(result["unknown_violations"]))


def _probe_b4():
    """缺陷注入：抽掉一个订阅实例（漏报）→ recall 必跌、未达标。"""
    from .bench_b4 import run_b4

    data_dir, manifest, truth, column_aliases = _load_frozen()
    subscriptions, distractors = _b4_engine(data_dir, manifest, column_aliases)
    broken = (subscriptions[:-1], distractors)
    result = run_b4(detected=broken,
                    rules_env=(data_dir, manifest, truth, column_aliases))
    live = bool(not result["pass"])
    return live, "抽掉订阅实例后 F1=%.4f（应未达标）" % result["f1"]


PROBES = {"B1": _probe_b1, "B2": _probe_b2, "B3": _probe_b3, "B4": _probe_b4}


def _aliases_doc(data_dir):
    return json.loads(
        (data_dir / "rules" / "aliases.json").read_text(encoding="utf-8")
    )


def _keywords_doc(data_dir):
    return json.loads(
        (data_dir / "rules" / "keywords.json").read_text(encoding="utf-8")
    )


def _b4_engine(data_dir, manifest, column_aliases):
    from .classify import classify_ledger
    from .normalize import normalize_ledger
    from .subscription import detect_subscriptions

    samples = sorted(
        str(p) for p in (data_dir / "samples").iterdir() if p.is_file()
    )
    ledger = import_files(
        samples,
        column_aliases=column_aliases,
        header_k=_params(manifest)["header_locate_k"],
        max_scan_lines=_params(manifest)["header_locate_max_scan_lines"],
    )
    ledger = classify_ledger(
        normalize_ledger(ledger, _aliases_doc(data_dir)),
        _keywords_doc(data_dir),
    )
    return detect_subscriptions(
        ledger,
        min_repeats=_params(manifest)["subscription_min_repeats"],
        price_change_min_percent=_params(manifest)["price_change_min_percent"],
        period_table=_params(manifest)["period_table"],
        default_tolerance_days=_params(manifest)[
            "subscription_interval_tolerance_days"],
    )

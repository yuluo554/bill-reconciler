"""内置基准骨架（M2 接入 B1 候选实现；正式达标与探活全套在 M4）。

设计口径（plan/03 §九）：

- 套件注册表：``SUITES``（id → 运行函数）；``--only`` 未知名 exit 2；
- B1 导入基准（候选实现）：真值 ``expect_import`` vs 解析结果，行级三态
  字段级对账，门槛读规则包 ``bench_thresholds``（门槛是数据不是代码）；
- 探活（可证伪）：注入缺陷 → 基准必须报未达标（``run_suite_live_probe``）；
- 退出码：0 达标 / 1 未达标 / 2 用例名或用法错误。
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

"""内置基准 B3 语义识别套件（plan/03 §九）。

真值对账（样本驱动）：``expect_semantic`` 67 行逐行标签 vs 引擎结果；
"未知"的可区分性是硬门——应未知的绝不能被猜成消费（fallthrough 一票
即未达标）。门槛 ``bench_b3_label_accuracy_min`` 读规则包（数据非代码）。
"""

from .errors import InputError


def run_b3(classified=None, rules_env=None):
    """B3 语义基准：逐行标签比对 → 准确率（含未知可区分性）。

    ``classified`` 可注入（探活用）；缺省 = 全量冻结样例跑真引擎。
    """
    from .bench_runner import _load_frozen, _threshold

    data_dir, manifest, truth, column_aliases = (
        _load_frozen() if rules_env is None else rules_env
    )
    if classified is None:
        from .ingest.importer import import_files
        from .normalize import normalize_ledger
        from .classify import classify_ledger
        import json

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
        classified = classify_ledger(normalize_ledger(ledger, aliases_doc),
                                     _keywords_doc(data_dir))

    expect = truth["expect_semantic"]
    observed = {r["id"]: r.get("semantic_label")
                for r in classified.get("records", [])}

    hit = 0
    mismatches = []
    unknown_violations = []
    for row_id, row_expect in expect.items():
        actual = observed.get(row_id)
        if actual == row_expect["label"]:
            hit += 1
        else:
            mismatches.append({"row": row_id, "expect": row_expect["label"],
                               "observed": actual})
            # 未知可区分性：应未知被判成其他标签 = 语义虚高（fallthrough）
            if row_expect["label"] == "未知" and actual is not None:
                unknown_violations.append(row_id)

    total = len(expect)
    accuracy = hit / total if total else 0.0
    accuracy_min = _threshold(manifest, "bench_b3_label_accuracy_min")
    passed = accuracy >= accuracy_min and not unknown_violations
    return {
        "suite": "B3",
        "total": total,
        "hit": hit,
        "accuracy": round(accuracy, 6),
        "unknown_violations": unknown_violations,
        "thresholds": {"accuracy_min": accuracy_min},
        "pass": passed,
        "mismatches": mismatches,
        "notes": "逐行标签对账（expect_semantic 全量）；未知 fallthrough 一票否决",
    }


def _param(manifest, param_id):
    for entry in manifest["params"]:
        if entry["id"] == param_id:
            return entry["value"]
    raise InputError("规则包缺少参数 %s（配置错误）" % param_id)


def _keywords_doc(data_dir):
    import json

    return json.loads(
        (data_dir / "rules" / "keywords.json").read_text(encoding="utf-8")
    )

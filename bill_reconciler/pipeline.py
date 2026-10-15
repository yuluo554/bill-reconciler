"""流水线编排（plan/03 §六：run 一条命令出结果；M3 接入前三段）。

import → normalize → dedup → classify 的内存内编排；report（M4）与
subscription（M4）接入后扩为 ①→⑤。每段"只增不改"（plan/03 §〇 原始不可变）；
分段产物（``normalize`` / ``dedup`` / ``classify`` 段与逐记录标记）共存于
同一份 IR dict，最终写单个 JSON。

CLI 单段子命令（``normalize`` / ``dedup`` / ``classify``）与 ``run`` 共用本模块，
保证"单段跑"与"流水线跑"是同一实现（不做两份口径）。
"""

import json
from pathlib import Path

from .classify import classify_ledger
from .dedup import dedup_ledger
from .errors import InputError
from .ingest.importer import import_files
from .normalize import normalize_ledger
from .params import load_rules_package

SCHEMA_VERSION = 1


def _write_json(path, payload):
    out_path = Path(path)
    if out_path.parent and not out_path.parent.exists():
        out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _load_package():
    from .datadir import require_data_dir

    return load_rules_package(require_data_dir())


def run_pipeline(files, platform=None, window_seconds=None, out_path=None):
    """文件清单 → 全流程 dict（ingest→normalize→dedup→classify）。

    ``window_seconds``：None = 规则包默认；数值 = CLI 覆盖（进产物参数来源块）。
    ``out_path``：给出即落盘（JSON，UTF-8、固定缩进）。
    返回 ``(ledger, exit_kind)``，exit_kind ∈ {"ok", "issues", "usage"}——
    与 import 的退出码契约同语义（文件级失败 2 / 行级问题 1 / 干净 0）。
    """
    package = _load_package()
    params = package.params

    ledger = import_files(
        files,
        platform=platform,
        column_aliases=package.aliases["column_aliases"],
        header_k=params.get("header_locate_k"),
        max_scan_lines=params.get("header_locate_max_scan_lines"),
    )

    effective_window = (
        params.get("dedup_window_seconds") if window_seconds is None else window_seconds
    )
    ledger["meta"]["params_digest"] = package.digest
    ledger["meta"]["ruleset_version"] = package.ruleset_version

    ledger = normalize_ledger(ledger, package.aliases)
    ledger = dedup_ledger(
        ledger,
        window_seconds=effective_window,
        platform_priority=params.get("platform_priority"),
    )
    ledger = classify_ledger(ledger, package.keywords)

    ledger["meta"]["pipeline"] = {
        "stages": ["import", "normalize", "dedup", "classify"],
        "report_pending": "report/subscription 接入计划于 M4（plan/05）",
    }
    if out_path is not None:
        _write_json(out_path, ledger)

    if ledger["file_issues"]:
        exit_kind = "usage"
    elif ledger["issues"]:
        exit_kind = "issues"
    else:
        exit_kind = "ok"
    return ledger, exit_kind


def summarize(ledger):
    """人读摘要（run 命令 stdout；行级/文件级问题清单仍全量走 stderr）。"""
    meta = ledger["meta"]
    lines = []
    lines.append("已处理 %d 个文件；记录 %d 条；行级问题 %d 条；文件级失败 %d 个" % (
        len(meta["sources"]), len(ledger["records"]),
        len(ledger["issues"]), len(ledger["file_issues"]),
    ))
    dedup = ledger.get("dedup", {})
    clusters = dedup.get("clusters", [])
    cross = [c for c in clusters if c["verdict"] == "duplicate_cross_platform"]
    same = [c for c in clusters if c["verdict"] == "candidate_same_platform"]
    lines.append(
        "去重：候选簇 %d 个（跨平台重复 %d / 同平台候选 %d；窗口 %s 秒）"
        % (len(clusters), len(cross), len(same),
           dedup.get("params", {}).get("window_seconds"))
    )
    net = dedup.get("net_summary", {})
    lines.append(
        "净额（已排除跨平台重复的非代表笔）：净支出 %.2f 元；净收入 %.2f 元"
        % (net.get("net_expense_cents", 0) / 100.0, net.get("net_income_cents", 0) / 100.0)
    )
    dist = ledger.get("classify", {}).get("distribution", {})
    lines.append("语义分布：" + "；".join(
        "%s=%d" % (k, v) for k, v in sorted(dist.items())
    ))
    unknown = ledger.get("classify", {}).get("unknown_rows", [])
    if unknown:
        total = sum(int(_cents(u["amount"])) for u in unknown if u.get("amount"))
        lines.append(
            "未知 %d 行（合计 %.2f 元；主口径未计入，若全部计入支出上限为 %.2f 元）"
            % (len(unknown), total / 100.0, total / 100.0)
        )
    lines.append("参数摘要 digest：%s（ruleset v%s）"
                 % (meta.get("params_digest"), meta.get("ruleset_version")))
    return "\n".join(lines)


def _cents(amount_text):
    from decimal import Decimal

    return int((Decimal(str(amount_text)) * 100).to_integral_value())


def run_normalize_stage(ledger, package):
    return normalize_ledger(ledger, package.aliases)


def run_dedup_stage(ledger, package, window_seconds):
    return dedup_ledger(
        ledger,
        window_seconds=window_seconds,
        platform_priority=package.params.get("platform_priority"),
    )


def run_classify_stage(ledger, package):
    return classify_ledger(ledger, package.keywords)

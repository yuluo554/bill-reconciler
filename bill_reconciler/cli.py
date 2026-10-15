"""bill-reconciler 命令行入口（argparse 子命令 + 退出码映射）。

退出码契约（plan/02 §4.5）：

- 0 完成且无未决事项
- 1 完成但检出需人工处理的问题（清单必打印）
- 2 用法或输入不可用（含骨架期占位命令"尚未实现"）
- 3 环境不可用（数据目录解析失败等）

骨架期（M0）说明：除 ``selftest`` 外，各子命令为占位实现，
打印"尚未实现（计划于 Mx）"并返回退出码 2；随对应里程碑逐一替换。
"""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .errors import (
    BillReconcilerError,
    EXIT_ISSUES,
    EXIT_OK,
    EXIT_USAGE,
    InputError,
    NotImplementedYet,
)
from .selftest import run_selftest

PROG = "bill-reconciler"

# 保持原样、不重配的编码：UTF-8 家族 + 中文控制台家族（避免本机中文变乱码）
_LEAVE_ENCODINGS = (
    "utf8",
    "cp936",
    "gbk",
    "gb2312",
    "gb18030",
    "big5",
    "cp950",
    "cp65001",
    "utf16",
    "utf16le",
    "utf16be",
)

# 占位命令表：(命令名, 帮助语, 计划里程碑)——import 于 M2、normalize/dedup/
# classify/run 于 M3 实装；report/bench 计划 M4
_STUB_COMMANDS = [
    ("report", "生成单文件 HTML 报告（模块⑤）", "M4"),
    ("bench", "运行内置基准套件", "M4"),
]


def _load_package():
    """规则包加载（M3 各命令共用；唯一访问点 params.py）。"""
    from .datadir import require_data_dir
    from .params import load_rules_package

    return load_rules_package(require_data_dir())


def _read_ledger(path):
    """读上游 ledger JSON（normalize/dedup/classify 单段入口的输入）。"""
    from .errors import InputError

    src = Path(path)
    if not src.is_file():
        raise InputError("上游 ledger 文件不存在：%s" % src)
    try:
        return json.loads(src.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise InputError("上游 ledger 文件不可解析 %s：%s" % (src, exc))


def _write_ledger(path, ledger):
    out_path = Path(path)
    if out_path.parent and not out_path.parent.exists():
        out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _write_and_report(out_path, ledger, summary):
    """落盘 + 摘要（stdout）+ 行级/文件级问题清单（stderr，全量）→ 退出码。"""
    _write_ledger(out_path, ledger)
    print(summary)
    import sys

    for issue in ledger.get("issues", []):
        where = issue.get("row_id") or "-"
        print("行级问题 [%s] %s：%s" % (issue["kind"], where, issue["detail"]),
              file=sys.stderr)
    for fi in ledger.get("file_issues", []):
        print("文件级失败 [%s] %s：%s" % (fi["code"], fi["file"], fi["detail"]),
              file=sys.stderr)
    if ledger.get("file_issues"):
        return EXIT_USAGE
    if ledger.get("issues"):
        return EXIT_ISSUES
    return EXIT_OK


def _ensure_utf8_stdio():
    """编码守卫（plan/03 §八）：非 UTF-8、非中文控制台的流切到 UTF-8。

    中文控制台（cp936 系）保持不动——本机可显示的中文不应变乱码；
    其余流（如 CI 上的 cp1252）改为 UTF-8，保证中文输出不抛 UnicodeEncodeError。
    在 main() 最前面执行；每个 tools/ 脚本入口同样执行。
    """
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if not encoding or encoding in _LEAVE_ENCODINGS:
            continue
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError, ValueError):
            pass


def _stub(command, milestone):
    def runner(args):
        raise NotImplementedYet(command, milestone)

    runner.__doc__ = "占位：%s（计划 %s 实现）" % (command, milestone)
    return runner


def _cmd_selftest(args):
    return run_selftest()


def _cmd_import(args):
    """import 子命令：账单文件 → ledger.json（IR）+ 问题清单（M2 实装）。

    退出码（plan/02 §4.5 最终语义，M2 锁定）：
    任一文件级失败 → 2；仅行级问题 → 1；全部干净 → 0。
    行级问题清单全量打印到 stderr（不截断）。
    """
    # 延迟导入：保持 selftest/--help 的启动开销最小
    from .datadir import require_data_dir
    from .ingest.importer import import_files

    data_dir = require_data_dir()
    aliases_doc = json.loads(
        (data_dir / "rules" / "aliases.json").read_text(encoding="utf-8")
    )
    column_aliases = aliases_doc["column_aliases"]
    manifest = json.loads(
        (data_dir / "rules" / "manifest.json").read_text(encoding="utf-8")
    )
    params = {p["id"]: p["value"] for p in manifest["params"]}

    ledger = import_files(
        args.files,
        platform=args.platform,
        column_aliases=column_aliases,
        header_k=params["header_locate_k"],
        max_scan_lines=params["header_locate_max_scan_lines"],
    )

    out_path = Path(args.out)
    if out_path.parent and not out_path.parent.exists():
        out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # 摘要（stdout）+ 行级问题清单（stderr，全量）
    sources = ledger["meta"]["sources"]
    total_ok = sum(s["rows_ok"] for s in sources)
    total_invalid = sum(s["rows_invalid"] for s in sources)
    total_unknown = sum(s["rows_unknown"] for s in sources)
    print("已导入 %d 个文件（清单：%s）" % (len(sources), out_path))
    for s in sources:
        print(
            "  %s [%s/%s] ok=%d invalid=%d unknown=%d"
            % (s["file"], s["platform"], s["encoding"], s["rows_ok"],
               s["rows_invalid"], s["rows_unknown"])
        )
    print("记录 %d 条；行级问题 %d 条；文件级失败 %d 个"
          % (len(ledger["records"]), len(ledger["issues"]), len(ledger["file_issues"])))

    for issue in ledger["issues"]:
        where = issue["row_id"] or "-"
        print("行级问题 [%s] %s：%s" % (issue["kind"], where, issue["detail"]),
              file=sys.stderr)

    if ledger["file_issues"]:
        for fi in ledger["file_issues"]:
            print("文件级失败 [%s] %s：%s" % (fi["code"], fi["file"], fi["detail"]),
                  file=sys.stderr)
        return EXIT_USAGE
    if ledger["issues"]:
        return EXIT_ISSUES
    return EXIT_OK


def _cmd_normalize(args):
    """normalize 子命令：商户名归一化（模块②，M3 实装）。

    输入上游 ledger（import 产物）或账单文件（--from-files 一步导入+归一）；
    退出码与 import 同语义。
    """
    from .normalize import normalize_ledger

    package = _load_package()
    if args.from_files:
        from .ingest.importer import import_files

        params = package.params
        ledger = import_files(
            args.from_files,
            column_aliases=package.aliases["column_aliases"],
            header_k=params.get("header_locate_k"),
            max_scan_lines=params.get("header_locate_max_scan_lines"),
        )
    else:
        ledger = _read_ledger(args.ledger)
    ledger = normalize_ledger(ledger, package.aliases)
    changed = sum(1 for e in ledger["normalize"]["entries"] if e["changed"])
    summary = "归一化：唯一名称 %d 个（发生归并 %d 个，未命中原样保留）" % (
        len(ledger["normalize"]["entries"]), changed
    )
    return _write_and_report(args.out, ledger, summary)


def _cmd_dedup(args):
    """dedup 子命令：跨平台去重（模块③，M3 实装）。"""
    from .dedup import dedup_ledger

    package = _load_package()
    ledger = _read_ledger(args.ledger)
    window = args.window_seconds
    if window is not None and window < 0:
        from .errors import UsageError

        raise UsageError("--window-seconds 不能为负：%r" % window)
    effective = (package.params.get("dedup_window_seconds")
                 if window is None else window)
    ledger = dedup_ledger(
        ledger, window_seconds=effective,
        platform_priority=package.params.get("platform_priority"),
    )
    clusters = ledger["dedup"]["clusters"]
    cross = sum(1 for c in clusters if c["verdict"] == "duplicate_cross_platform")
    same = sum(1 for c in clusters if c["verdict"] == "candidate_same_platform")
    excluded = len(ledger["dedup"]["net_summary"]["excluded_duplicate_ids"])
    summary = (
        "去重：候选簇 %d 个（跨平台重复 %d / 同平台候选 %d）；"
        "排除出净额 %d 条（窗口 %s 秒）"
        % (len(clusters), cross, same, excluded, effective)
    )
    return _write_and_report(args.out, ledger, summary)


def _cmd_classify(args):
    """classify 子命令：语义识别（模块④，M3 实装）。"""
    from .classify import classify_ledger

    package = _load_package()
    ledger = _read_ledger(args.ledger)
    ledger = classify_ledger(ledger, package.keywords)
    dist = ledger["classify"]["distribution"]
    unknown = len(ledger["classify"]["unknown_rows"])
    summary = "语义识别：%s；未知 %d 行（一等结论，不混入消费）" % (
        "；".join("%s=%d" % (k, v) for k, v in sorted(dist.items())) or "无记录",
        unknown,
    )
    return _write_and_report(args.out, ledger, summary)


def _cmd_run(args):
    """run 子命令：import→normalize→dedup→classify 一条命令（M3 接前三段）。

    report/subscription 接入计划于 M4（plan/03 §六"M2 起逐步接入"口径）。
    """
    from .pipeline import run_pipeline

    ledger, _exit_kind = run_pipeline(
        args.files,
        platform=args.platform,
        window_seconds=args.window_seconds,
        out_path=args.out,
    )
    return _finish_run(ledger, args.out)


def _finish_run(ledger, out_path):
    import sys

    _write_ledger(out_path, ledger)
    from .pipeline import summarize

    print(summarize(ledger))
    for issue in ledger.get("issues", []):
        where = issue.get("row_id") or "-"
        print("行级问题 [%s] %s：%s" % (issue["kind"], where, issue["detail"]),
              file=sys.stderr)
    for fi in ledger.get("file_issues", []):
        print("文件级失败 [%s] %s：%s" % (fi["code"], fi["file"], fi["detail"]),
              file=sys.stderr)
    if ledger["file_issues"]:
        return EXIT_USAGE
    if ledger["issues"]:
        return EXIT_ISSUES
    return EXIT_OK


def build_parser():
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=(
            "多平台账单『真实支出』对账器：合并微信/支付宝/银行导出账单，"
            "跨平台去重 + 转账语义识别，算出真正花掉的钱。纯本地零上传。"
        ),
    )
    parser.add_argument("--version", action="version", version="%s %s" % (PROG, __version__))

    sub = parser.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("import", help="导入账单文件（模块①，M2 实装）")
    sp.add_argument("files", nargs="+", help="账单文件（微信/支付宝/银行导出）")
    sp.add_argument("--out", default="ledger.json", help="输出 ledger.json 路径（默认 ./ledger.json）")
    sp.add_argument(
        "--platform",
        choices=None,
        default=None,
        help="显式指定平台（wechat/alipay/bank）；缺省按文件名前缀识别",
    )
    sp.set_defaults(func=_cmd_import)

    sp = sub.add_parser("normalize", help="商户名归一化（模块②，M3 实装）")
    sp.add_argument("--ledger", default=None, help="上游 ledger.json（与 --from-files 二选一）")
    sp.add_argument("--from-files", nargs="*", default=None,
                    help="直接给账单文件（先导入再归一）")
    sp.add_argument("--out", default="ledger-normalized.json", help="输出 JSON 路径")
    sp.set_defaults(func=_cmd_normalize)

    sp = sub.add_parser("dedup", help="跨平台去重（模块③，M3 实装）")
    sp.add_argument("--ledger", default="ledger-normalized.json", help="上游 ledger JSON")
    sp.add_argument("--window-seconds", type=int, default=None,
                    help="时间窗口秒数（覆盖规则包默认值；闭区间 |Δt| ≤ W）")
    sp.add_argument("--out", default="ledger-dedup.json", help="输出 JSON 路径")
    sp.set_defaults(func=_cmd_dedup)

    sp = sub.add_parser("classify", help="转账/退款/AA回款语义识别（模块④，M3 实装）")
    sp.add_argument("--ledger", default="ledger-dedup.json", help="上游 ledger JSON")
    sp.add_argument("--out", default="ledger-classified.json", help="输出 JSON 路径")
    sp.set_defaults(func=_cmd_classify)

    sp = sub.add_parser("run", help="一键流水线：导入→归一化→去重→语义（①→④，M3 实装）")
    sp.add_argument("files", nargs="+", help="账单文件（微信/支付宝/银行导出）")
    sp.add_argument("--platform", default=None,
                    help="显式指定平台（wechat/alipay/bank）；缺省按文件名前缀识别")
    sp.add_argument("--window-seconds", type=int, default=None,
                    help="去重时间窗口秒数（覆盖规则包默认值）")
    sp.add_argument("--out", default="ledger-full.json", help="输出 JSON 路径")
    sp.set_defaults(func=_cmd_run)

    for name, help_text, milestone in _STUB_COMMANDS:
        sp = sub.add_parser(name, help="%s（计划 %s）" % (help_text, milestone))
        sp.set_defaults(func=_stub(name, milestone))
    sp = sub.add_parser("selftest", help="环境与数据资产自检")
    sp.set_defaults(func=_cmd_selftest)
    return parser


def main(argv=None):
    """CLI 主入口；返回进程退出码（console script 与 python -m 共用）。"""
    _ensure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except BillReconcilerError as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    sys.exit(main())

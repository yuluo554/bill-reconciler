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

# 占位命令表：(命令名, 帮助语, 计划里程碑)——import 已于 M2 实装
_STUB_COMMANDS = [
    ("normalize", "商户名归一化（模块②）", "M3"),
    ("dedup", "跨平台去重（模块③）", "M3"),
    ("classify", "转账/退款/AA回款语义识别（模块④）", "M3"),
    ("report", "生成单文件 HTML 报告（模块⑤）", "M4"),
    ("run", "一键串起完整流水线（①→⑤）", "M2–M4"),
    ("bench", "运行内置基准套件", "M4"),
]


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

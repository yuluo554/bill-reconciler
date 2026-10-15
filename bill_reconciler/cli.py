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
import sys

from . import __version__
from .errors import BillReconcilerError, NotImplementedYet
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

# 占位命令表：(命令名, 帮助语, 计划里程碑)
_STUB_COMMANDS = [
    ("import", "导入账单文件（模块①）", "M2"),
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

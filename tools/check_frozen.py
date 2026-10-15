"""check_frozen.py — 冻结数据资产全量守门入口（M1）。

重跑全部生成器（gen_rules / gen_samples）的 ``--check``：重生成到内存、与入库件
逐字节比对，任一漂移即非零退出。M4 起 bench、M5 起交付验证都以本入口为守门第一站。

- 退出码 0：全部位级一致（``FROZEN_ALL_OK``）；
- 退出码 1：任一生成器漂移（``FROZEN_*_DRIFT``，逐文件列出）；
- 退出码 2：用法错误（未知 --only 名称）；
- ``--ledger``：打印全部冻结文件的 sha256 台账（随 data/README.md §六登记表核对）。
"""

import argparse
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _frozen_common import ensure_utf8_stdio  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

GENERATORS = [
    ("rules", "gen_rules.py"),
    ("samples", "gen_samples.py"),
]

_FROZEN_DIRS = ["data/rules", "data/truth", "data/samples"]


def _run_generator(script, extra=None):
    """进程内执行生成器 main()；返回退出码。"""
    import importlib.util

    path = Path(__file__).resolve().parent / script
    spec = importlib.util.spec_from_file_location("brc_gen_%s" % script[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main(list(extra or []))


def _ledger_lines():
    lines = []
    for dir_name in _FROZEN_DIRS:
        base = ROOT / dir_name
        if not base.is_dir():
            continue
        paths = sorted(p for p in base.rglob("*") if p.is_file())
        for path in paths:
            rel = path.relative_to(ROOT).as_posix()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            lines.append("%s  %s" % (digest, rel))
    return lines


def main(argv=None):
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="冻结数据资产全量 --check 守门")
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="只跑指定生成器（rules/samples），可多次；缺省全部",
    )
    parser.add_argument("--ledger", action="store_true", help="打印冻结文件 sha256 台账")
    args = parser.parse_args(argv)

    if args.ledger:
        lines = _ledger_lines()
        print("冻结文件 sha256 台账（%d 个）：" % len(lines))
        for line in lines:
            print(line)
        return 0

    names = args.only or [name for name, _ in GENERATORS]
    known = {name for name, _ in GENERATORS}
    for name in names:
        if name not in known:
            print("错误：未知 --only 名称 %s（可用：%s）" % (name, ", ".join(sorted(known))))
            return 2

    failed = []
    for name, script in GENERATORS:
        if name not in names:
            continue
        code = _run_generator(script, ["--check"])
        if code != 0:
            failed.append(script)

    if failed:
        print("FROZEN_DRIFT：%s 漂移（重生成不一致，禁手改入库件）" % ", ".join(failed))
        return 1
    print("FROZEN_ALL_OK：全部冻结数据资产与重生成位级一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())

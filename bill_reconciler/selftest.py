"""selftest：环境与数据资产自检（骨架期实装命令）。

检查项三态：

- PASS：当前已满足；
- FAIL：不满足（任一 FAIL → 退出码 1，"完成但检出需人工处理的问题"）；
- PENDING："计划于后续里程碑生成"的数据资产——显式列出，**绝不冒充通过**。

退出码另设"环境不可用"一态（3）：数据目录解析失败 / 不存在时，
检查项无法运行——这与"检出缺陷"（1）是两件事，与 ``bench`` 及
README 的退出码契约保持一致。

M1 起：规则包 / 合成样例生成后，对应项从 PENDING 翻转为 PASS
（tests/test_selftest.py 的期望同步翻转，注明"期望变更"）。
"""

import json
import platform
import sys

from . import __version__
from .datadir import ENV_VAR, find_data_dir
from .errors import EXIT_ENV, EXIT_ISSUES, EXIT_OK

_STATUS_PASS = "PASS"
_STATUS_FAIL = "FAIL"
_STATUS_PENDING = "PENDING"


def _check_python():
    ok = sys.version_info[:2] >= (3, 12)
    detail = "%s（要求 >= 3.12）" % platform.python_version()
    return (_STATUS_PASS if ok else _STATUS_FAIL), detail


def _check_package():
    return _STATUS_PASS, "bill_reconciler %s 可导入" % __version__


def _check_data_dir():
    try:
        data_dir = find_data_dir()
    except Exception as exc:  # EnvError：显式环境变量指向无效目录
        return None, _STATUS_FAIL, "数据目录解析失败：%s" % exc
    if data_dir is None:
        return None, _STATUS_FAIL, "未找到 data/ 目录（请在仓库根运行，或设置 %s）" % ENV_VAR
    return data_dir, _STATUS_PASS, "数据目录：%s" % data_dir


def _check_rules(data_dir):
    if data_dir is None:
        return _STATUS_PENDING, "规则包 data/rules/manifest.json（计划 M1 生成）"
    manifest = data_dir / "rules" / "manifest.json"
    if not manifest.is_file():
        return _STATUS_PENDING, "规则包 data/rules/manifest.json（计划 M1 生成）"
    try:
        json.loads(manifest.read_text(encoding="utf-8"))
    except Exception as exc:
        return _STATUS_FAIL, "规则包 manifest.json 不可解析：%s" % exc
    return _STATUS_PASS, "规则包 manifest.json 可加载"


def _check_samples(data_dir):
    if data_dir is None:
        return _STATUS_PENDING, "合成样例 data/samples/（计划 M1 生成）"
    samples = data_dir / "samples"
    files = [p for p in samples.rglob("*") if p.is_file()] if samples.is_dir() else []
    if not files:
        return _STATUS_PENDING, "合成样例 data/samples/（计划 M1 生成）"
    return _STATUS_PASS, "合成样例：%d 个文件" % len(files)


def _check_param_literals(data_dir):
    """零参数字面量门禁（M3）：引擎/CLI 源码零规则包数值词面。"""
    if data_dir is None:
        return _STATUS_FAIL, "数据目录不可用，门禁无法运行"
    from .lint_params import scan_param_literals
    from .params import load_rules_package

    package = load_rules_package(data_dir)
    violations = scan_param_literals(package)
    if violations:
        detail = "；".join(
            "%s:%s=%s" % (v["file"], v["line"], v["token"]) for v in violations[:5]
        )
        return _STATUS_FAIL, "源码出现规则包数值词面（%d 处）：%s" % (
            len(violations), detail
        )
    return _STATUS_PASS, "引擎/CLI 源码零参数字面量（token 集随规则包生成）"


def run_selftest():
    """运行全部检查并打印清单；返回退出码（0 全过 / 1 有 FAIL / 3 环境不可用）。"""
    print("bill-reconciler selftest %s" % __version__)

    data_dir, data_status, data_detail = _check_data_dir()

    # 数据目录不可用 → 环境不可用（3），与 bench 同一口径：
    # 这不是"检出需人工处理的问题"（1），而是检查项本身无法运行。
    # 因此**不打印检查清单**（清单里每一项都会是 FAIL，会把"环境不可用"伪装成"检出缺陷"）。
    if data_dir is None:
        print("错误：%s" % data_detail)
        return EXIT_ENV

    checks = [
        ("Python 解释器", *_check_python()),
        ("包导入", *_check_package()),
        ("数据目录", data_status, data_detail),
        ("规则包", *_check_rules(data_dir)),
        ("合成样例", *_check_samples(data_dir)),
        ("参数字面量门禁", *_check_param_literals(data_dir)),
    ]

    counts = {_STATUS_PASS: 0, _STATUS_PENDING: 0, _STATUS_FAIL: 0}
    for name, status, detail in checks:
        counts[status] += 1
        print("[%s] %s：%s" % (status, name, detail))
    print(
        "结论：%d PASS / %d PENDING / %d FAIL"
        % (counts[_STATUS_PASS], counts[_STATUS_PENDING], counts[_STATUS_FAIL])
    )
    if counts[_STATUS_FAIL]:
        return EXIT_ISSUES
    if counts[_STATUS_PENDING]:
        print("PENDING 项将按 plan/05-里程碑.md 的计划在对应里程碑生成（当前不冒充通过）。")
    return EXIT_OK

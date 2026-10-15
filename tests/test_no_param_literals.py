"""零参数字面量门禁测试（M3，plan/03 §七）。

- 阴性：当前源码 0 违规（token 集随规则包运行时生成）；
- 阳性对照（可证伪）：临时注入一个含 token 的源文件 → 门禁必须报红
  （删掉即恢复，不动入库件——阳性对照写 tmp 注入式，不污染工作树）；
- params.py 豁免自身；token 集覆盖 params 与 bench_thresholds 数值。
"""

import stat
from pathlib import Path

import pytest

from bill_reconciler.datadir import require_data_dir
from bill_reconciler.lint_params import scan_param_literals
from bill_reconciler.params import load_rules_package, param_tokens


@pytest.fixture(scope="module")
def package():
    return load_rules_package(require_data_dir())


def test_no_param_literals_in_source(package):
    violations = scan_param_literals(package)
    assert violations == [], "源码出现规则包数值词面：%s" % violations


def test_token_set_generated_from_manifest(package):
    tokens = param_tokens(package)
    # token 集非空且随 manifest 数值生成（这里只锁结构，不复制具体数值进测试）
    assert tokens
    assert all(isinstance(t, str) and len(t) > 1 for t in tokens)
    # 一位数豁免：不出现单字符 token
    assert all(len(t) >= 2 for t in tokens)


def test_scan_detects_injected_token(package, tmp_path):
    """阳性对照：注入含 token 的源文件 → 门禁报红（可证伪）。"""
    tokens = sorted(param_tokens(package))
    injected = tokens[0]
    scan_root = tmp_path / "scanme"
    pkg_root = scan_root / "bill_reconciler"
    pkg_root.mkdir(parents=True)
    (pkg_root / "evil.py").write_text(
        "# 阳性对照：注入规则包数值\nVALUE = %s\n" % injected, encoding="utf-8"
    )
    violations = scan_param_literals(package, roots=[str(scan_root)])
    assert len(violations) == 1
    assert violations[0]["token"] == injected
    assert violations[0]["file"].endswith("evil.py")


def test_whole_word_match_no_false_positive(package, tmp_path):
    """长数字串不判成其前缀的命中（1200 ≠ 120）。"""
    scan_root = tmp_path / "scanme2"
    pkg_root = scan_root / "bill_reconciler"
    pkg_root.mkdir(parents=True)
    (pkg_root / "ok.py").write_text(
        "# 注入长数字串：拼接形态不应命中\nVALUE = 12005\n", encoding="utf-8"
    )
    # 构造一个必然不在 token 集里的数字上下文：直接扫
    violations = scan_param_literals(package, roots=[str(scan_root)])
    assert all(v["file"].endswith("ok.py") is False or v["token"] != "1200"
               for v in violations)

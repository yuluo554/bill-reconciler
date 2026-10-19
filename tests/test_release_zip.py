"""发布 zip 打包器守门（M6，plan/06 G18 打包确定性子门；2026-10-16 审计修复）。

覆盖两点：

1. **确定性**：同一工作树打包两次，sha256 逐字节一致（`ZIP_STORED` +
   条目排序 + 固定 date_time / 外部属性）；
2. **自指排除**：``plan/RELEASE-M6.md`` 是本 zip 的发布留档（其内记录 zip 自身
   sha256），**必须**被排除在包外——否则"文件内容依赖 zip 摘要、zip 摘要又依赖
   文件内容"构成自指，任何真值都无法自洽（变异验证：把排除项去掉后本测试必红）。

测试以真实 `git ls-files` 追踪面为准（与打包器同一数据源），在 tmp 目录落 zip。
"""

import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKER = REPO_ROOT / "tools" / "make_release_zip.py"


def _run_packer(out_path):
    res = subprocess.run(
        [sys.executable, "-X", "utf8", str(PACKER), str(out_path)],
        capture_output=True, text=True, encoding="utf-8", cwd=str(REPO_ROOT),
    )
    assert res.returncode == 0, "打包器退出非 0：%s" % res.stderr
    return out_path


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_packer_deterministic_two_runs_byte_identical(tmp_path):
    a = _run_packer(tmp_path / "a.zip")
    b = _run_packer(tmp_path / "b.zip")
    assert _sha256(a) == _sha256(b), "两次打包 sha256 不一致（确定性子门失败）"


def test_packer_excludes_self_referential_release_ledger(tmp_path):
    """发布留档 `plan/RELEASE-M6.md` 必须在包外（防 sha256 自指）。"""
    out = _run_packer(tmp_path / "c.zip")
    names = zipfile.ZipFile(out).namelist()
    leaked = [n for n in names if n.endswith("plan/RELEASE-M6.md")]
    assert leaked == [], "自指文件被误打入包：%s" % leaked
    # 防"空包假绿"：包内确有正常源码文件
    assert any(n.endswith("bill_reconciler/cli.py") for n in names), (
        "包内未见预期源码（扫描面失效）"
    )


def test_packer_covers_tracked_face_minus_exclusion(tmp_path):
    """包内容 = git 追踪面 − 排除项（防漏文件/多文件）。"""
    tracked = subprocess.run(
        ["git", "-c", "core.quotepath=off", "ls-files"],
        capture_output=True, text=True, encoding="utf-8", cwd=str(REPO_ROOT),
        check=True,
    ).stdout.splitlines()
    expected = {t for t in tracked if t.strip() and t.strip() != "plan/RELEASE-M6.md"}
    out = _run_packer(tmp_path / "d.zip")
    # 顶层目录名跟随 __version__（打包器现取），测试同样现取——不写死版本，
    # 避免升版本时两处硬编码各自漂移。
    from bill_reconciler import __version__

    prefix = "bill-reconciler-%s/" % __version__
    got = {
        n.split(prefix, 1)[1]
        for n in zipfile.ZipFile(out).namelist()
    }
    assert got == expected, "打包面与追踪面不符：差集 %s" % (
        sorted(got ^ expected)
    )

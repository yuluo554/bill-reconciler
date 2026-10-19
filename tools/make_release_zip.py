"""M6 发布：确定性源码 zip 打包器（P6 默认形态）。

确定性口径（plan/06 G18 打包子门 + plan/05 M6）：
- 压缩 = ZIP_STORED（源码体量小，不做压缩以消除压缩库版本差异）；
- 条目顺序 = git ls-files 排序（以 git 追踪面为准，工作树未追踪文件不入包）；
- 元数据 = 固定 date_time（SOURCE_DATE_EPOCH 口径取 2026-10-15 00:00:00 UTC），
  固定外部属性（0644 可读），无目录条目（按文件条目隐含父目录）；
- 两次打包逐字节一致由 tests 外的 M6 验证流程比对 sha256 验证。

**包外件（自指文件，必须排除）**：``plan/RELEASE-M6.md`` 是本 zip 的**发布留档
台账**，其 §四/§六 记录**本 zip 自身的 sha256**。若把该文件打进 zip，则"文件内容
依赖 zip 摘要、zip 摘要又依赖文件内容"构成自指，任何真值都无法自洽（实测：改动
该文件 → 打包 sha256 必变）。故打包器**恒定排除**该文件（detached checksum 惯例：
校验和是包外件，不随包内容变化）。被排除件仍在 git 树内（tag/仓库可完整复核），
发布物可复核性不受影响。

用法：py -X utf8 tools/make_release_zip.py <输出.zip>
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

# 固定时间戳：2026-10-15 00:00:00 UTC（发布基准日）
FIXED_DATE_TIME = (2026, 10, 15, 0, 0, 0)
FIXED_EXTERNAL_ATTR = 0o100644 << 16  # 常规文件 rw-r--r--

# 包外件（自指文件）：见模块 docstring。恒定排除，保证打包确定性。
_EXCLUDED_NAMES = ("plan/RELEASE-M6.md",)


def _package_version(root: Path) -> str:
    """从 bill_reconciler/__init__.py 现取版本（唯一真源），不另设常量。

    发布 zip 的顶层目录名必须跟随版本号，否则升版本后包内前缀仍是旧版本
    （过 blame 会看到两处硬编码各自漂移）。
    """
    source = (root / "bill_reconciler" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', source, re.MULTILINE)
    if not match:
        print("FAIL: 无法从 bill_reconciler/__init__.py 解析 __version__", file=sys.stderr)
        raise SystemExit(2)
    return match.group(1)


def main() -> int:
    out = Path(sys.argv[1])
    root = Path(__file__).resolve().parent.parent
    names = sorted(
        line.strip()
        for line in subprocess_lsfiles(root)
        if line.strip() and line.strip() not in _EXCLUDED_NAMES
    )
    if not names:
        print("FAIL: git ls-files 为空，不在 git 仓库内？", file=sys.stderr)
        return 2
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as zf:
        prefix = "bill-reconciler-%s/" % _package_version(root)
        for name in names:
            data = (root / name).read_bytes()
            info = zipfile.ZipInfo(prefix + name, date_time=FIXED_DATE_TIME)
            info.external_attr = FIXED_EXTERNAL_ATTR
            info.compress_type = zipfile.ZIP_STORED
            zf.writestr(info, data)
    print(f"OK: {out} 条目数={len(names)}（包外件 {len(_EXCLUDED_NAMES)}）")
    return 0


def subprocess_lsfiles(root: Path) -> list[str]:
    import subprocess

    res = subprocess.run(
        ["git", "-c", "core.quotepath=off", "ls-files"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return res.stdout.splitlines()


if __name__ == "__main__":
    sys.exit(main())

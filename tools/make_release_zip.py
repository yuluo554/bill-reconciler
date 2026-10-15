"""M6 发布：确定性源码 zip 打包器（P6 默认形态）。

确定性口径（plan/06 G18 打包子门 + plan/05 M6）：
- 压缩 = ZIP_STORED（源码体量小，不做压缩以消除压缩库版本差异）；
- 条目顺序 = git ls-files 排序（以 git 追踪面为准，工作树未追踪文件不入包）；
- 元数据 = 固定 date_time（SOURCE_DATE_EPOCH 口径取 2026-10-15 00:00:00 UTC），
  固定外部属性（0644 可读），无目录条目（按文件条目隐含父目录）；
- 两次打包逐字节一致由 tests 外的 M6 验证流程比对 sha256 验证。

用法：py -X utf8 tools/make_release_zip.py <输出.zip>
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

# 固定时间戳：2026-10-15 00:00:00 UTC（发布基准日）
FIXED_DATE_TIME = (2026, 10, 15, 0, 0, 0)
FIXED_EXTERNAL_ATTR = 0o100644 << 16  # 常规文件 rw-r--r--


def main() -> int:
    out = Path(sys.argv[1])
    root = Path(__file__).resolve().parent.parent
    names = sorted(
        line.strip()
        for line in subprocess_lsfiles(root)
        if line.strip()
    )
    if not names:
        print("FAIL: git ls-files 为空，不在 git 仓库内？", file=sys.stderr)
        return 2
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as zf:
        prefix = "bill-reconciler-0.1.0/"
        for name in names:
            data = (root / name).read_bytes()
            info = zipfile.ZipInfo(prefix + name, date_time=FIXED_DATE_TIME)
            info.external_attr = FIXED_EXTERNAL_ATTR
            info.compress_type = zipfile.ZIP_STORED
            zf.writestr(info, data)
    print(f"OK: {out} 条目数={len(names)}")
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

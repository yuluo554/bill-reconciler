"""data/ 目录解析（全项目唯一入口）。

解析顺序（写死，plan/02 §4.3）：

1. 环境变量 ``BILL_RECONCILER_DATA``：显式指定 → 必须有效（含 README.md），
   无效即报错**不回落**（显式意图不静默）；
2. 从当前工作目录向上逐级探查（覆盖仓库根直跑、editable 安装、发布 zip 解压）。

**刻意不**从包文件位置探查：站点包内的路径是"装到哪算哪"，向上走会命中
开发机的仓库或其他项目的 data/——"数据目录"应该跟随用户所在位置或显式
声明，而不是跟随安装位置（实测：包位置探查会在仓库子目录误命中仓库根）。

任何功能代码不得自行拼接数据路径，一律经本模块。
"""

import os
from pathlib import Path

from .errors import EnvError

ENV_VAR = "BILL_RECONCILER_DATA"

# data 目录的标记文件：存在即认为该目录是项目数据目录
_MARKER = "README.md"

# 向上探查的最大层数（防御病态深路径；正常仓库远小于此）
_MAX_UP = 64


def _is_data_dir(path):
    return path.is_dir() and (path / _MARKER).is_file()


def find_data_dir(start=None, env=None):
    """返回 data/ 目录 Path；找不到返回 None；显式环境变量无效抛 EnvError。

    start：可选，先从这个目录开始向上探查（测试与显式调用用）。
    env：   可选，环境变量映射（默认 os.environ；测试注入用）。
    """
    env_map = os.environ if env is None else env
    explicit = env_map.get(ENV_VAR)
    if explicit:
        candidate = Path(explicit)
        if _is_data_dir(candidate):
            return candidate
        raise EnvError(
            "%s 指向的目录不可用：%s（需为含 %s 的 data 目录）" % (ENV_VAR, explicit, _MARKER)
        )

    starts = []
    if start is not None:
        starts.append(Path(start))
    starts.append(Path.cwd())  # 当前工作目录（仓库根直跑 / 发布 zip 解压场景）

    seen = set()
    for base in starts:
        current = base.resolve()
        for _ in range(_MAX_UP):
            if current in seen:
                break
            seen.add(current)
            candidate = current / "data"
            if _is_data_dir(candidate):
                return candidate
            parent = current.parent
            if parent == current:  # 已到根
                break
            current = parent
    return None


def require_data_dir(start=None, env=None):
    """同 find_data_dir，但找不到时抛 EnvError（退出码 3）。"""
    data_dir = find_data_dir(start=start, env=env)
    if data_dir is None:
        raise EnvError(
            "未找到数据目录 data/：请在仓库根目录运行，或设置环境变量 %s 指向 data 目录" % ENV_VAR
        )
    return data_dir

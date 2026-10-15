"""三面交叉守门（M5，G13）：测试面 = 安装面 = README 指令面。

三个面各配可证伪断言（把对应面的内容弄坏 → 本文件必红）：

1. **README 命令面**：README 中出现的每条 `python -m bill_reconciler <cmd>` /
   ``brc <cmd>`` / ``bill-reconciler <cmd>`` 与每个 `--flag`，都能在
   ``cli.build_parser()`` 的真实注册表里找到（防"README 写了不存在的命令/旗标"）；
   反向：CLI 八个子命令全部在 README 出现（防"实装了却没写进文档"）。
2. **测试 import 面**：tests/ 全部 import 的顶层模块 ∈ {标准库, pytest(dev extra),
   本包, tools 生成器（sys.path 注入的仓库内模块）}；第三方测试期依赖必须落在
   pyproject 的 dev extra 里（防"开发机碰巧装过，干净 venv/CI 才炸"）。
   标准库判定用冻结名单（``sys.stdlib_module_names`` 是 3.10+，底线 3.8 不可用）。
3. **安装面**：README 的 pip install 行引用的每个 extra 在 pyproject 里真实声明；
   pyproject 的 packages.find 收的就是仓库里的真实包（含 report 子包）——
   防"目录布局与打包配置不匹配、装完 console script 却 ModuleNotFoundError"。

判据输入全部来自仓库内文件与 AST，不随构建/运行环境变。
"""

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
PYPROJECT = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

# 3.8 兼容：标准库名单冻结快照（Python 3.8 文档 + 本仓库实际用到的全部标准库）。
# 维护口径：tests/ 新 import 了名单外的标准库 → 把它加进本名单（这不是参数值，
# 是判定词表；与 lint_params 的 token 集同理随扫描面扩张）。
_STDLIB = frozenset({
    "argparse", "ast", "codecs", "collections", "contextlib", "copy", "csv",
    "datetime", "decimal", "functools", "hashlib", "importlib", "io", "itertools",
    "json", "math", "os", "pathlib", "re", "shutil", "socket", "stat",
    "subprocess", "sys", "tempfile", "time", "typing", "unicodedata", "unittest",
    "urllib", "xml", "zipfile",
})

# 分发名 → import 名别名表（比对走 import 名，别直接拿分发名比）。
_ALIASES = {"pytest": "pytest"}

# tools/ 生成器经 sys.path 注入，不算第三方（仓库内模块）。
_TOOLS_MODULES = frozenset({"gen_rules", "gen_samples", "_frozen_common"})


def _cli_registry():
    """真实 CLI 注册表：子命令名集合 + 各子命令声明的旗标集合。"""
    import bill_reconciler.cli as cli
    parser = cli.build_parser()
    subparsers_action = next(
        a for a in parser._actions if a.dest == "command" and hasattr(a, "choices")
    )
    registry = {}
    for name, sub in subparsers_action.choices.items():
        flags = {a.option_strings[0] for a in sub._actions if a.option_strings}
        # argparse 自带的 --help 对任何子命令都合法，不计入 README 断言面
        flags.add("--help")
        registry[name] = flags
    return registry


def _readme_commands():
    """README 里出现的 CLI 调用：(命令名, 旗标集合)。

    命令与旗标按**同一行**关联（`--report-html` 只在 run 的调用行出现，
    就归给 run——防"把别的命令的旗标张冠李戴"）。另有一张"命令提及行"
    （README 的命令总表），只补命令名、不提供旗标。
    """

    commands = {}
    # python/py -m bill_reconciler <cmd>（含 -X utf8 等中间旗标）——按行关联旗标
    for line in README.splitlines():
        m = re.search(r"(?:python|py)(?:\s+-[\w.]+)*\s+-m\s+bill_reconciler\s+(\w+)", line)
        if not m:
            continue
        flags = commands.setdefault(m.group(1), set())
        flags.update(re.findall(r"(?<![\w-])--[a-z][a-z0-9-]*", line))
    # console script 两个名字 <cmd>——同样按行关联
    for line in README.splitlines():
        m = re.search(r"(?:^|\s)(?:brc|bill-reconciler)\s+(\w+)", line)
        if not m:
            continue
        flags = commands.setdefault(m.group(1), set())
        flags.update(re.findall(r"(?<![\w-])--[a-z][a-z0-9-]*", line))
    # 命令提及行（总表如 `import`（导入）· `normalize`…）——只补名字
    mention_line = re.search(r"^`import`（导入）.*$", README, re.M)
    if mention_line:
        for m in re.finditer(r"`([a-z][a-z0-9]*)`", mention_line.group(0)):
            commands.setdefault(m.group(1), set())
    return commands


def test_readme_commands_exist_in_cli_registry():
    """面 1 正向：README 每条命令/旗标都在真实 parser 注册表里。"""
    registry = _cli_registry()
    readme = _readme_commands()
    assert "selftest" in readme, "README 未出现任何 python -m bill_reconciler 调用"
    for name, flags in readme.items():
        assert name in registry, "README 提到的命令在 CLI 不存在：%s" % name
        for flag in flags:
            assert flag in registry[name], (
                "README 提到的旗标 %s 未在子命令 %s 声明" % (flag, name)
            )


def test_cli_subcommands_all_in_readme():
    """面 1 反向：CLI 注册的每个子命令都在 README 出现。"""
    registry = _cli_registry()
    readme = _readme_commands()
    missing = sorted(set(registry) - set(readme))
    assert not missing, "CLI 子命令未写进 README：%s" % ", ".join(missing)


def _test_imports():
    """tests/ 全部文件的 import 顶层名（含函数内惰性 import，从严收集）。"""
    names = set()
    for path in sorted((REPO_ROOT / "tests").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    names.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    return names


def test_test_imports_have_landing_in_install_face():
    """面 2：测试 import 的每个顶层模块都有落点（stdlib / dev extra / 本包 / tools）。"""
    imports = _test_imports()
    dev_extra_raw = re.search(r"^dev\s*=\s*\[(.*?)\]", PYPROJECT, re.M | re.S).group(1)
    dev_dists = {m.group(1).strip().split(">")[0].split("<")[0].split("=")[0].strip("\"' ")
                 for m in re.finditer(r"[\"']([^\"']+)[\"']", dev_extra_raw)}
    dev_import_names = {_ALIASES.get(d, d) for d in dev_dists}
    unknown = sorted(
        n for n in imports
        if n not in _STDLIB
        and n not in dev_import_names
        and n != "bill_reconciler"
        and n not in _TOOLS_MODULES
    )
    assert not unknown, (
        "tests import 的依赖没有落点（不在标准库名单 / dev extra / 本包 / tools）：%s" % unknown
    )


def test_readme_install_extras_declared_in_pyproject():
    """面 3 正向：README 安装行引用的每个 extra 在 pyproject 真实声明。"""
    extras_referenced = set()
    # 安装行形态：pip install ... -e ".[dev]" / pip install .（含双引号包裹）
    for m in re.finditer(r'pip install[^`\n]*?\.\[[a-z, ]+\]', README):
        for e in re.findall(r'\.\[([a-z, ]+)\]', m.group(0)):
            extras_referenced.update(x.strip() for x in e.split(",") if x.strip())
    assert extras_referenced, "README 中未发现任何带 extras 的 pip install 行（扫描面失效）"
    declared = set(re.findall(r"^([a-z_]+)\s*=\s*\[", PYPROJECT, re.M))
    missing = extras_referenced - declared
    assert not missing, "README 安装行引用了 pyproject 未声明的 extra：%s" % missing


def test_pyproject_packages_find_matches_layout():
    """面 3 反向：packages.find 的 include 模式能收住仓库里的真实包（含 report 子包）。"""
    include_raw = re.search(
        r"packages\.find\]\s*(.*?)$", PYPROJECT, re.S
    ).group(1)
    assert "bill_reconciler*" in include_raw, "pyproject packages.find 未收 bill_reconciler*"
    # 仓库里的真实包目录 → 每个都必须匹配 include 模式（防布局与打包配置漂移）
    import bill_reconciler
    pkg_dir = Path(bill_reconciler.__file__).resolve().parent
    assert pkg_dir.name == "bill_reconciler"
    assert (pkg_dir / "report" / "__init__.py").is_file(), "report 子包缺失"
    # 防数据目录/工具被误收进包：包内不允许出现 data/ 或 tools/ 目录
    for stray in ("data", "tools"):
        assert not (pkg_dir / stray).is_dir(), "包内不应携带 %s/ 目录" % stray

"""零参数字面量门禁（plan/03 §七：数值口径单点的静态扫描面）。

扫描对象：引擎/CLI/报告/基准源码（``bill_reconciler/`` 包内 .py，含
docstring 与注释）——被禁 token 从规则包**运行时生成**（``params.param_tokens``），
扫描器自身零词面（不携带任何"第几号参数是多少"的知识）。

豁免口径（写死，逐条理由）：

1. **params.py 自身**：唯一访问点必然引用参数值所在的数据结构（不是
   复制数值，是参数的家）；
2. **一位数（0–9）**：数组下标/循环基数等结构性小整数，不构成数值口径
   漂移风险（param_tokens 生成侧已按长度 >1 过滤）；
3. **ingest/ 的表头定位参数**：M2 已按"读规则包"实现，但历史注释含
   举例数值——只豁免 docstring 中带"如/例/默认"字样的行（防注释漂移
   不防代码漂移），代码行出现 token 仍然红。

发现 token → 列出 文件:行号:内容，返回失败（exit 语义由调用方/测试承载）。
"""

import ast
import re
from pathlib import Path

from .errors import InputError

# 扫描面：包内源码（引擎/CLI/报告/基准都住这里；tools/ 与 tests/ 不属运行时面）
_SCAN_ROOTS = ("bill_reconciler",)

# 豁免：参数唯一访问点自身
_EXEMPT_FILES = {"params.py"}

# 注释/文档行豁免：行内含"例""默认""如"举例语气才豁免（理由：举例值不是口径）
_EXEMPT_DOC_PATTERN = re.compile(r"(如|例|默认)")


def _extract_strings(node):
    """收集源码中所有字符串字面量 + 标识符（标识符也可能携带口径数字）。"""
    import ast

    strings = []
    for item in ast.walk(node):
        if isinstance(item, ast.Constant) and isinstance(item.value, str):
            strings.append((item.lineno, item.value))
        elif isinstance(item, ast.Name):
            strings.append((item.lineno, item.id))
    return strings


def scan_param_literals(package, roots=None):
    """扫描 → 违规清单 [ {file, line, token, text} ]（空清单 = 绿）。

    判定口径：token 以"整词"出现在**代码行**（import/赋值/字符串皆算）；
    注释行仅当不含举例语气词才判红。
    """
    tokens = param_token_set(package)
    roots = roots or _SCAN_ROOTS
    violations = []
    for root in roots:
        base = Path(root)
        if not base.is_dir():
            raise InputError("扫描根不存在：%s" % base)
        for py in sorted(base.rglob("*.py")):
            rel = py.as_posix()
            if rel.replace("\\", "/").split("/")[-1] in _EXEMPT_FILES:
                continue
            text = py.read_text(encoding="utf-8")
            try:
                tree = ast.parse(text)
            except SyntaxError as exc:
                raise InputError("扫描目标源码不可解析 %s：%s" % (rel, exc))
            str_nodes = _extract_strings(tree)
            # 代码行集合（AST 覆盖的行）；注释行 = 非代码行的含 token 行
            code_lines = {}
            for lineno, s in str_nodes:
                code_lines.setdefault(lineno, []).append(s)
            for lineno, line in enumerate(text.splitlines(), start=1):
                hit = _hit_token(line, tokens)
                if hit is None:
                    continue
                is_comment_line = lineno not in code_lines and line.lstrip().startswith("#")
                if is_comment_line and _EXEMPT_DOC_PATTERN.search(line):
                    continue
                violations.append({
                    "file": rel,
                    "line": lineno,
                    "token": hit,
                    "text": line.strip()[:100],
                })
    return violations


def _hit_token(line, tokens):
    """整词命中判定：token 前后紧邻字符都不是数字（长数字串不判成其前缀命中）。

    环绕是字母/标点/结尾都算命中；代码行与字符串字面量一视同仁。
    """
    for match in re.finditer(r"\d+(?:\.\d+)?", line):
        token = match.group(0)
        if token in tokens:
            before = line[match.start() - 1] if match.start() > 0 else ""
            after = line[match.end()] if match.end() < len(line) else ""
            if before.isdigit() or after.isdigit():
                continue
            return token
    return None


def param_token_set(package):
    from .params import param_tokens

    return param_tokens(package)

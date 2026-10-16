"""规则包参数唯一访问点（plan/03 §七：数值口径单点）。

全部可配置数值只在 ``data/rules/`` 定义；代码侧唯一访问点是本模块——

- ``load_rules_package()``：加载 manifest + aliases + keywords 三份冻结件，
  逐项结构校验（缺字段/类型不符 → InputError，exit 2 语义）；
- ``Params``：``get(param_id)`` / 属性访问（缺失即 InputError，绝不内联默认值）；
- ``RulesPackage.digest``：三份冻结件 sha256 的聚合摘要（结论可复现性锚点，
  进产物 meta 与报告参数来源块）；
- ``threshold(name)``：基准门槛（门槛是数据，缺失即 InputError）；
- ``param_tokens(manifest)``：零参数字面量门禁的禁用 token 集（**运行时从
  manifest 数值程序化生成**，源码与留档零词面——门禁扫描器只认生成的集合，
  不自带任何"第几号参数是多少"的知识）。

引擎/报告/基准不得出现第二份数值：违反即 ``tests/test_no_param_literals.py`` 红门。

**门禁残余面（显式登记，plan/03 §七）**：token 集只覆盖两位及以上数值，
故 ``subscription_min_repeats=3``、``subscription_interval_tolerance_days=2``、
``header_locate_k=2`` 三个真口径参数**不受静态门禁保护**（全局收窄会引入
退出码/步骤编号等大量误报）。兜底 = 行为穿透测试
``tests/test_param_caliber_fallback.py``（逐参数改规则包值并断言可观测行为
随之变化，硬编码口径即必红）；残余面清单由
``test_residual_face_is_registered`` 锁定防漂移。
"""

import hashlib
import json

from .errors import InputError


class Params:
    """规则包参数只读视图：缺失即 InputError（exit 2 配置错误语义）。"""

    def __init__(self, entries, ruleset_version):
        self._values = {}
        self._entries = {}
        for entry in entries:
            pid = entry["id"]
            self._values[pid] = entry["value"]
            self._entries[pid] = entry
        self.ruleset_version = ruleset_version

    def get(self, param_id):
        if param_id not in self._values:
            raise InputError("规则包缺少参数 %s（配置错误）" % param_id)
        return self._values[param_id]

    def entry(self, param_id):
        """完整条目（含 unit/source/notes——报告参数来源块用）。"""
        if param_id not in self._entries:
            raise InputError("规则包缺少参数 %s（配置错误）" % param_id)
        return self._entries[param_id]

    def ids(self):
        return sorted(self._values)

    def user_overridable(self, param_id):
        return bool(self.entry(param_id).get("user_configurable"))


def _require(mapping, key, where, types=None):
    if key not in mapping:
        raise InputError("%s 缺少字段 %s（配置错误）" % (where, key))
    value = mapping[key]
    if types is not None and not isinstance(value, types):
        raise InputError("%s 字段 %s 类型不符（期望 %s）" % (where, key, types))
    return value


def load_rules_package(data_dir):
    """加载并校验规则包 → RulesPackage；任何结构问题 → InputError。

    校验是"结构存在性"（字段齐、类型对），不复制任何具体数值。
    """
    rules_dir = data_dir / "rules"
    manifest = _load_json(rules_dir / "manifest.json")
    aliases = _load_json(rules_dir / "aliases.json")
    keywords = _load_json(rules_dir / "keywords.json")

    _require(manifest, "schema_version", "manifest.json", int)
    _require(manifest, "params", "manifest.json", list)
    _require(manifest, "bench_thresholds", "manifest.json", list)
    for entry in manifest["params"]:
        where = "params[%s]" % entry.get("id")
        _require(entry, "id", where, str)
        _require(entry, "value", where)
        _require(entry, "user_configurable", where, bool)
    for entry in manifest["bench_thresholds"]:
        _require(entry, "id", "bench_thresholds[%s]" % entry.get("id"), str)
        _require(entry, "value", "bench_thresholds[%s]" % entry.get("id"))

    _require(aliases, "suffix_strip", "aliases.json", list)
    _require(aliases, "aliases", "aliases.json", list)
    for entry in aliases["aliases"]:
        _require(entry, "canonical", "aliases.aliases", str)
        _require(entry, "variants", "aliases.aliases", list)

    _require(keywords, "rules", "keywords.json", list)
    for entry in keywords["rules"]:
        where = "keywords.rules[%s]" % entry.get("id")
        _require(entry, "id", where, str)
        _require(entry, "label", where, str)
        _require(entry, "direction_condition", where, str)
        if entry["direction_condition"] not in ("expense", "income", "neutral", "any"):
            raise InputError(
                "%s 的 direction_condition=%r 不在白名单" % (where, entry["direction_condition"])
            )
        _require(entry, "keywords", where, list)
        _require(entry, "priority", where, int)

    digest = RulesPackage.compute_digest(data_dir)
    return RulesPackage(
        data_dir=data_dir,
        manifest=manifest,
        aliases=aliases,
        keywords=keywords,
        params=Params(manifest["params"], manifest.get("ruleset_version")),
        digest=digest,
    )


def _load_json(path):
    if not path.is_file():
        raise InputError("规则包文件缺失：%s" % path.name)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise InputError("规则包文件不可解析 %s：%s" % (path.name, exc))


class RulesPackage:
    """加载后的规则包快照（不可变使用方约定：引擎不改写任何字段）。"""

    def __init__(self, data_dir, manifest, aliases, keywords, params, digest):
        self.data_dir = data_dir
        self.manifest = manifest
        self.aliases = aliases
        self.keywords = keywords
        self.params = params
        self.digest = digest

    @property
    def ruleset_version(self):
        return self.manifest.get("ruleset_version")

    def threshold(self, threshold_id):
        for entry in self.manifest["bench_thresholds"]:
            if entry["id"] == threshold_id:
                return entry["value"]
        raise InputError("规则包缺少基准门槛 %s（配置错误）" % threshold_id)

    @staticmethod
    def compute_digest(data_dir):
        """三份冻结件 sha256 的聚合摘要（按文件名排序串联后整体哈希）。

        任一文件字节变化 → digest 变化 → 结论可复现性锚点可审计。
        """
        rules_dir = data_dir / "rules"
        names = sorted(["manifest.json", "aliases.json", "keywords.json"])
        parts = []
        for name in names:
            data = (rules_dir / name).read_bytes()
            parts.append("%s:%s" % (name, hashlib.sha256(data).hexdigest()))
        return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def param_tokens(package):
    """零参数字面量门禁的禁用 token 集（运行时从规则包生成，零词面）。

    生成口径（写死、测试锁定）：

    - 数值型参数值 → 整数取十进制整串、浮点取 ``repr`` 的整数/小数双形式
      （如 2.0 → {"2.0", "2"}）；
    - 数值型门槛值 → 同上（bench_thresholds 也是数据下发的数值）；
    - 周期表 ``interval_days`` / ``tolerance_days`` 等嵌套数值 → 同口径展开；
    - 平台优先级列表是字符串序列（非数值），不生成 token；
    - 小于等于 9 的一位数不进集合（结构性小整数豁免，plan/03 §七豁免口径：
      数组下标、循环次数等出现频率高且不构成"数值口径漂移"风险——豁免
      逐条理由回写 plan/03 §七）。
    """
    tokens = set()

    def _from_number(value):
        if isinstance(value, bool):
            return
        if isinstance(value, int):
            _add(value)
        elif isinstance(value, float):
            _add(value)
            _add(int(value))

    def _add(value):
        text = str(value)
        if len(text) > 1:  # 一位数豁免（结构性小整数）
            tokens.add(text)

    for entry in package.manifest["params"]:
        _from_number(entry["value"])
        if isinstance(entry["value"], list):
            for item in entry["value"]:
                if isinstance(item, dict):
                    for inner in item.values():
                        _from_number(inner)
                else:
                    _from_number(item)
    for entry in package.manifest["bench_thresholds"]:
        _from_number(entry["value"])
    return tokens

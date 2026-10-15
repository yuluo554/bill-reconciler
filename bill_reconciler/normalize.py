"""模块② 商户名归一化（plan/03 §二）。

归并动作序列**写死**（顺序即语义，任何调序都是行为变更、必须测试翻红）：

1. 去空白（首尾 + 内部：全角空格 U+3000、制表符等全部 \\\\s 归空再压掉）；
2. 全半角统一（映射表来自冻结规则包 ``aliases.fullwidth_map``）；
3. 后缀剥离（白名单来自 ``aliases.suffix_strip``；剥离后非空才生效）；
4. 别名表命中（``aliases.aliases`` 的 variants→canonical；variants 过同一
   归一管线后建索引——否则"全角括号写法的变体"永远匹配不上）；
5. 未命中 → 原样保留（``normalized == original`` 且 ``actions == []``），
   "归并了"与"没归并"由依据显式区分（plan/03 §2.1）。

纯函数：同一原名在任何上下文归一结果恒定；不做编辑距离/分词/读音相似度。
逐条依据 ``{"rule": ..., "detail": ..., "evidence": ...}``——每次变化一条。
"""

import re

from .errors import InputError

# 归并动作 id（写死；与 plan/03 §2.1 一一对应）
RULE_WHITESPACE = "whitespace_collapse"
RULE_FULLWIDTH = "fullwidth_norm"
RULE_SUFFIX = "suffix_strip"
RULE_ALIAS = "alias_table"

# 去空白：首尾与内部空白全部移除（plan/03 §2.1 "去除首尾及内部空白字符"）
_WHITESPACE_RUN = re.compile(r"\s+")

# 别名表上限（防病态大表；正常表远小于此）
_MAX_ALIAS_ENTRIES = 4096


class AliasIndex:
    """冻结别名表的归一化索引（构建一次、纯查询）。

    variants 先过同一归一管线（去空白→全半角→后缀剥离）再建索引——
    保证"表中写法"与"流水写法"在同一口径下比较。
    """

    def __init__(self, aliases_doc):
        suffix_list = aliases_doc.get("suffix_strip", [])
        fullwidth_list = aliases_doc.get("fullwidth_map", [])
        alias_entries = aliases_doc.get("aliases", [])
        if len(alias_entries) > _MAX_ALIAS_ENTRIES:
            raise InputError("别名表条目数超上限 %d（疑似配置错误）" % _MAX_ALIAS_ENTRIES)
        self._suffixes = tuple(sorted((s for s in suffix_list if s), key=len, reverse=True))
        self._fullwidth = {}
        for entry in fullwidth_list:
            full, half = entry.get("full"), entry.get("half")
            if not full or half is None:
                raise InputError("fullwidth_map 条目缺少 full/half 字段")
            self._fullwidth[full] = half
        self._index = {}
        for entry in alias_entries:
            canonical = entry["canonical"]
            for variant in entry["variants"]:
                norm = self.normalize(variant)[0]
                self._index[norm] = canonical

    def normalize(self, original):
        """原名 → (归一名, actions)；动作序列写死，逐条依据（plan/03 §2.1）。"""
        actions = []
        value = original

        # 1. 去空白（首尾 + 内部全部移除）
        collapsed = _WHITESPACE_RUN.sub("", value)
        if collapsed != value:
            actions.append({
                "rule": RULE_WHITESPACE,
                "detail": "去除空白字符",
                "evidence": "aliases.normalize_note",
            })
            value = collapsed

        # 2. 全半角统一（映射表驱动）
        if value and any(ch in self._fullwidth for ch in value):
            mapped = "".join(self._fullwidth.get(ch, ch) for ch in value)
            if mapped != value:
                actions.append({
                    "rule": RULE_FULLWIDTH,
                    "detail": "全角转半角",
                    "evidence": "aliases.fullwidth_map",
                })
                value = mapped

        # 3. 后缀剥离（白名单、最长优先；剥离后非空才生效）
        for suffix in self._suffixes:
            if value.endswith(suffix) and len(value) > len(suffix):
                stripped = value[: -len(suffix)].strip()
                if stripped:
                    actions.append({
                        "rule": RULE_SUFFIX,
                        "detail": "剥离后缀 %r" % suffix,
                        "evidence": "aliases.suffix_strip",
                    })
                    value = stripped
                    break

        # 4. 别名表命中（variants 归一后索引 → canonical）
        if value in self._index:
            canonical = self._index[value]
            if canonical != value:
                actions.append({
                    "rule": RULE_ALIAS,
                    "detail": "别名归并 → %r" % canonical,
                    "evidence": "aliases.aliases",
                })
                value = canonical
        return value, actions


def normalize_ledger(ledger, aliases_doc):
    """IR ledger → 追加归一化段的视图（原始不可变：只增不改）。

    每条 record 增设 ``normalized_counterparty`` + ``normalize_actions``；
    归一化台账 ``normalize`` 段：逐名称的原名/归一名/依据（重复原名只记一次）。
    """
    index = AliasIndex(aliases_doc)
    records = []
    journal = {}
    journal_order = []
    for record in ledger.get("records", []):
        new_record = dict(record)
        original = record.get("counterparty") or ""
        if original:
            normalized, actions = index.normalize(original)
        else:
            normalized, actions = original, []
        new_record["normalized_counterparty"] = normalized
        new_record["normalize_actions"] = actions
        records.append(new_record)
        if original and original not in journal:
            journal[original] = {
                "original": original,
                "normalized": normalized,
                "actions": actions,
                "changed": bool(actions),
            }
            journal_order.append(original)

    out = dict(ledger)
    out["records"] = records
    out["normalize"] = {
        "order": journal_order,
        "entries": [journal[name] for name in journal_order],
    }
    return out

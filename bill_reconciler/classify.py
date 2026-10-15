"""模块④ 转账/退款/AA回款语义识别（plan/03 §四）。

判定 = 词面命中（冻结关键词表，子串匹配、区分大小写）+ 收支方向组合：

- 规则按 **priority 升序**评估（数值来自规则包，非代码内联）；
  priority 相同时按 id 升序（确定性，无字典序意外）；
- 方向条件不符 → 跳过（干扰例：支出方向的"退款"词、入账方向的张三转账
  都不得命中各自规则）；
- 同一行命中多条 → 按优先级取首个，但**全部命中条目都记录**（可审计）；
- **"未知"是一等结论**：未命中任何规则 → ``未知``，绝不 fallthrough 为"消费"
  （"消费"必须由正命中产生——那会让"真实支出"虚高，plan/03 §4.1）。

作用域 = 归一化对手方 + 商品说明（match_note 口径）。
"""

from .errors import InputError

LABEL_UNKNOWN = "未知"

_DIRECTION_FIELD = {"expense": "expense", "income": "income", "neutral": "neutral"}


def _direction_ok(condition, direction):
    if condition == "any":
        return True
    return direction == condition


def load_keyword_rules(keywords_doc):
    """关键词表 → 评估序列（priority 升序、同优先级 id 升序；确定性）。"""
    rules = []
    for entry in keywords_doc.get("rules", []):
        if not entry.get("keywords"):
            raise InputError("关键词规则 %s 的 keywords 为空（配置错误）" % entry.get("id"))
        rules.append(entry)
    rules.sort(key=lambda r: (r["priority"], r["id"]))
    return rules


def classify_record(record, rules):
    """单条记录 → 判定 dict。

    方向缺失（unknown 行）不参与方向条件判定——除 ``any`` 规则外全部跳过，
    结论为 ``未知``（依据显式记录"方向未知"）。
    """
    direction = record.get("direction")
    scope_text = "%s\n%s" % (record.get("normalized_counterparty") or record.get("counterparty") or "",
                             record.get("description") or "")

    hits = []
    for rule in rules:
        if not _direction_ok(rule["direction_condition"], direction):
            continue
        for keyword in rule["keywords"]:
            if keyword in scope_text:
                hits.append({
                    "rule_id": rule["id"],
                    "label": rule["label"],
                    "keyword": keyword,
                    "priority": rule["priority"],
                })
                break  # 同一规则内命中任一关键词即可（首个，确定性）

    if hits:
        chosen = hits[0]  # 评估序首个 = 优先级最高
        return {
            "label": chosen["label"],
            "rule_id": chosen["rule_id"],
            "matched_keywords": [h["keyword"] for h in hits],
            "all_hits": hits,
            "basis": {
                "rule": "keyword+direction",
                "detail": "命中规则 %s（priority=%d，方向条件=%s）"
                          % (chosen["rule_id"], chosen["priority"], rule_direction(chosen, rules)),
                "evidence": "keywords.json@%s" % chosen["rule_id"],
            },
        }
    # 未命中 → 未知（一等结论；方向缺失也在此显式注明）
    detail = ("方向未知，且无规则命中" if direction not in _DIRECTION_FIELD
              else "无规则命中（不得 fallthrough 为消费）")
    return {
        "label": LABEL_UNKNOWN,
        "rule_id": None,
        "matched_keywords": [],
        "all_hits": [],
        "basis": {"rule": "no_match", "detail": detail, "evidence": "keywords.json"},
    }


def rule_direction(rule_id_prefix_label, rules):
    """命中条目对应规则的方向条件（依据文本用）。"""
    for rule in rules:
        if rule["id"] == rule_id_prefix_label["rule_id"]:
            return rule["direction_condition"]
    return "?"


def classify_ledger(ledger, keywords_doc):
    """IR（归一化后）→ 追加语义标签段的视图（原始不可变，只增不改）。

    每条 record 增设 ``semantic_label`` + ``semantic_basis``；
    新增 ``classify`` 段（标签分布、未知行清单、规则快照）。
    """
    rules = load_keyword_rules(keywords_doc)
    records = []
    distribution = {}
    unknown_rows = []
    for record in ledger.get("records", []):
        new_record = dict(record)
        verdict = classify_record(record, rules)
        new_record["semantic_label"] = verdict["label"]
        new_record["semantic_basis"] = verdict
        records.append(new_record)
        distribution[verdict["label"]] = distribution.get(verdict["label"], 0) + 1
        if verdict["label"] == LABEL_UNKNOWN:
            unknown_rows.append({
                "id": record["id"],
                "direction": record.get("direction"),
                "counterparty": record.get("normalized_counterparty") or record.get("counterparty"),
                "description": record.get("description"),
                "amount": record.get("amount"),
                "reason": verdict["basis"]["detail"],
            })

    out = dict(ledger)
    out["records"] = records
    out["classify"] = {
        "rules_digest": [
            {"id": r["id"], "label": r["label"], "priority": r["priority"],
             "direction_condition": r["direction_condition"]}
            for r in rules
        ],
        "distribution": dict(sorted(distribution.items())),
        "unknown_rows": unknown_rows,
        "note": "『未知』是一等结论：主口径不把未知混入消费，也不假装未知不存在",
    }
    return out

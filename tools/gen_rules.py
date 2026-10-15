"""gen_rules.py — 冻结规则包生成器（M1）。

产出（唯一编辑面就是本脚本；改需求 = 改本脚本 + 整目录重生成 + --check 通过）：

- ``data/rules/manifest.json``：参数包（值/单位/用户可配 flag/来源标注/说明）
  + 基准门槛（门槛是数据不是代码）+ 规则包版本；
- ``data/rules/keywords.json``：语义关键词表（``{id, label, direction_condition,
  keywords[], priority, notes}``），一处定义、多处引用；
- ``data/rules/aliases.json``：商户别名表（规范名 → 变体列表）+ 归并规则参数
  （后缀剥离白名单、全半角映射表）。

纪律：禁 stdlib random、禁 set 迭代序、禁系统时钟；产物无时间戳；
--check 模式与入库件逐字节比对。
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _frozen_common import (  # noqa: E402
    compare_outputs,
    dumps_json_bytes,
    ensure_utf8_stdio,
    write_outputs,
)

ROOT = Path(__file__).resolve().parents[1]
# v2（2026-10-15，M2）：新增列名别名表 column_aliases（ingest 列映射同源数据）
GEN_VERSION = 2
RULESET_VERSION = 2
SOURCE_NOTE = "经验默认（非官方）：全部默认值为经验示例值，用户可经 CLI flag 覆盖"

_PERIOD_TOLERANCE_DAYS = 2

# 参数包：顺序即 JSON 输出顺序（固定，不依赖动态排序）
_PARAMS = [
    {
        "id": "dedup_window_seconds",
        "value": 120,
        "unit": "秒",
        "user_configurable": True,
        "cli_flag": "--window-seconds",
        "source": SOURCE_NOTE,
        "notes": "跨平台去重时间窗口，闭区间 |Δt| ≤ W；恰好等于 W 应合并",
    },
    {
        "id": "subscription_min_repeats",
        "value": 3,
        "unit": "次",
        "user_configurable": True,
        "cli_flag": "--min-repeats",
        "source": SOURCE_NOTE,
        "notes": "周期订阅最小重复次数（含首期）",
    },
    {
        "id": "subscription_interval_tolerance_days",
        "value": _PERIOD_TOLERANCE_DAYS,
        "unit": "天",
        "user_configurable": True,
        "cli_flag": "--interval-tolerance-days",
        "source": SOURCE_NOTE,
        "notes": "周期表内各周期未单独覆盖时的间隔容差默认值",
    },
    {
        "id": "price_change_min_percent",
        "value": 2.0,
        "unit": "%",
        "user_configurable": True,
        "cli_flag": "--price-change-percent",
        "source": SOURCE_NOTE,
        "notes": "涨价判定阈值：相邻周期金额变化 ≥ 该百分比记一条涨价记录",
    },
    {
        "id": "platform_priority",
        "value": ["wechat", "alipay", "bank"],
        "unit": "平台次序",
        "user_configurable": False,
        "cli_flag": None,
        "source": SOURCE_NOTE,
        "notes": "去重簇代表笔选择排序键（时间最早 → 本次序 → 来源行号）",
    },
    {
        "id": "header_locate_k",
        "value": 2,
        "unit": "列命中数",
        "user_configurable": False,
        "cli_flag": None,
        "source": SOURCE_NOTE,
        "notes": "表头定位：候选行命中的预期列名数 ≥ K 即判为表头",
    },
    {
        "id": "header_locate_max_scan_lines",
        "value": 20,
        "unit": "行",
        "user_configurable": False,
        "cli_flag": None,
        "source": SOURCE_NOTE,
        "notes": "表头定位扫描上限：只在前 N 行内找表头，超出即文件级失败",
    },
    {
        "id": "period_table",
        "value": [
            {
                "id": "monthly",
                "label": "月付",
                "interval_days": 30,
                "tolerance_days": _PERIOD_TOLERANCE_DAYS,
            },
            {
                "id": "quarterly",
                "label": "季付",
                "interval_days": 91,
                "tolerance_days": 3,
            },
            {
                "id": "yearly",
                "label": "年付",
                "interval_days": 365,
                "tolerance_days": 5,
            },
        ],
        "unit": "周期表",
        "user_configurable": False,
        "cli_flag": None,
        "source": SOURCE_NOTE,
        "notes": "订阅周期判定表：相邻间隔落在 interval_days ± tolerance_days 内即视为同周期",
    },
]

# 基准门槛（数据不是代码；M4 的 bench 只读）
_BENCH_THRESHOLDS = [
    {
        "id": "bench_b1_row_f1_min",
        "value": 0.95,
        "unit": "F1",
        "source": SOURCE_NOTE,
        "notes": "B1 导入：行级三态字段级 P/R/F1 下限",
    },
    {
        "id": "bench_b2_cluster_accuracy_min",
        "value": 0.95,
        "unit": "准确率",
        "source": SOURCE_NOTE,
        "notes": "B2 去重：簇级判定（应合并/不应合并）准确率下限",
    },
    {
        "id": "bench_b2_false_positive_max",
        "value": 0,
        "unit": "簇",
        "source": SOURCE_NOTE,
        "notes": "B2 去重：误报（把不应合并的合并）允许上限",
    },
    {
        "id": "bench_b3_label_accuracy_min",
        "value": 0.98,
        "unit": "准确率",
        "source": SOURCE_NOTE,
        "notes": "B3 语义：逐行标签准确率下限（含『未知』可区分性）",
    },
    {
        "id": "bench_b4_f1_min",
        "value": 0.90,
        "unit": "F1",
        "source": SOURCE_NOTE,
        "notes": "B4 订阅/涨价：周期条目与涨价记录 F1 下限",
    },
]

# 语义关键词表：规则按 priority 升序评估；方向条件不满足即跳过。
_KEYWORD_RULES = [
    {
        "id": "R10_refund",
        "label": "退款",
        "direction_condition": "income",
        "keywords": ["退款"],
        "priority": 10,
        "notes": "入账且出现『退款』字样；支出方向出现该词为干扰例，不得命中",
    },
    {
        "id": "R20_aa_collection",
        "label": "AA回款",
        "direction_condition": "income",
        "keywords": ["AA回款", "AA收款"],
        "priority": 20,
        "notes": "入账且出现 AA 回款/AA 收款字样",
    },
    {
        "id": "R30_reimbursement",
        "label": "报销",
        "direction_condition": "income",
        "keywords": ["报销"],
        "priority": 30,
        "notes": "入账且出现『报销』字样",
    },
    {
        "id": "R40_self_transfer",
        "label": "本人转账",
        "direction_condition": "any",
        "keywords": ["示例本人卡A", "示例本人卡B"],
        "priority": 40,
        "notes": "出现本人卡占位名即命中（含『不计收支』方向）；同事/房东转账不命中",
    },
    {
        "id": "R50_consumption_retail",
        "label": "消费",
        "direction_condition": "expense",
        "keywords": ["示例便利店甲", "示例快餐乙", "示例超市丙", "示例咖啡丁"],
        "priority": 50,
        "notes": "白名单零售/餐饮商户，支出方向命中消费",
    },
    {
        "id": "R51_consumption_travel",
        "label": "消费",
        "direction_condition": "expense",
        "keywords": ["示例打车平台"],
        "priority": 50,
        "notes": "出行商户，支出方向命中消费",
    },
    {
        "id": "R52_consumption_topup",
        "label": "消费",
        "direction_condition": "expense",
        "keywords": ["示例话费充值"],
        "priority": 50,
        "notes": "充值商户，支出方向命中消费",
    },
]

_ALIAS_ENTRIES = [
    {
        "canonical": "示例便利店甲",
        "variants": ["示例便利店甲（有限）公司", "示例 便利店甲"],
    },
    {
        "canonical": "示例快餐乙",
        "variants": ["示例快餐乙外卖店"],
    },
    {
        "canonical": "示例超市丙",
        "variants": ["示例超市丙 旗舰店"],
    },
    {
        "canonical": "示例咖啡丁",
        "variants": ["示例咖啡丁（五道口店）"],
    },
]

# 列名别名表（M2 ingest 用；与"表头定位预期列名集"同源规则包，plan/03 §1.3）
# canonical 用规范字段名（ingest.locate.F_* 的中文拼法）；platforms 为空 = 全平台生效
_COLUMN_ALIAS_ENTRIES = [
    {
        "canonical": "对手方",
        "variants": ["交易对象"],
        "platforms": ["alipay", "wechat", "bank"],
        "notes": "同义列名变体（col_synonym_variant 形态）",
    },
    {
        "canonical": "金额",
        "variants": ["金额(元)", "金额（元）", "金额"],
        "platforms": ["alipay", "wechat", "bank"],
        "notes": "金额列写法变体（半角/全角括号）",
    },
    {
        "canonical": "交易时间",
        "variants": ["交易创建时间"],
        "platforms": ["alipay"],
        "notes": "支付宝创建时间列即交易时间",
    },
    {
        "canonical": "商品说明",
        "variants": ["商品"],
        "platforms": ["alipay", "wechat"],
        "notes": "商品说明列写法变体",
    },
    {
        "canonical": "收支类型",
        "variants": ["收/支"],
        "platforms": ["alipay", "wechat"],
        "notes": "收支类型列写法变体",
    },
]


def _build_fullwidth_map():
    """ASCII 全角 → 半角映射表（程序化生成，固定顺序）。"""
    mapping = []
    for cp in range(0xFF01, 0xFF5F):  # ！ … ｚ 区段
        mapping.append({"full": chr(cp), "half": chr(cp - 0xFEE0)})
    mapping.append({"full": "\u3000", "half": " "})  # 全角空格
    return mapping


def build_outputs():
    """构造全部规则包产物（``{相对路径: 字节}``；纯函数、无时钟）。"""
    manifest = {
        "schema_version": 1,
        "kind": "rules-manifest",
        "ruleset_version": RULESET_VERSION,
        "generator": "tools/gen_rules.py",
        "generator_version": GEN_VERSION,
        "source_note": SOURCE_NOTE,
        "params": _PARAMS,
        "bench_thresholds": _BENCH_THRESHOLDS,
        "files": {
            "manifest": "data/rules/manifest.json",
            "keywords": "data/rules/keywords.json",
            "aliases": "data/rules/aliases.json",
        },
    }
    keywords = {
        "schema_version": 1,
        "kind": "keyword-rules",
        "ruleset_version": RULESET_VERSION,
        "match_note": (
            "关键词按子串匹配、区分大小写；作用域 = 交易对方 + 商品说明；"
            "规则按 priority 升序评估，方向条件不满足即跳过；"
            "全部未命中 → 『未知』（一等结论，不得 fallthrough 为消费）"
        ),
        "rules": _KEYWORD_RULES,
    }
    aliases = {
        "schema_version": 1,
        "kind": "alias-table",
        "ruleset_version": RULESET_VERSION,
        "normalize_note": (
            "归并动作顺序：去空白 → 全半角统一（本表映射）→ 后缀剥离（白名单）→ "
            "别名表命中；未命中任何规则则原样保留"
        ),
        "suffix_strip": ["有限公司", "有限责任公司", "股份有限公司", "集团有限公司"],
        "fullwidth_map": _build_fullwidth_map(),
        "aliases": _ALIAS_ENTRIES,
        "column_aliases": _COLUMN_ALIAS_ENTRIES,
    }
    return {
        "data/rules/manifest.json": dumps_json_bytes(manifest),
        "data/rules/keywords.json": dumps_json_bytes(keywords),
        "data/rules/aliases.json": dumps_json_bytes(aliases),
    }


def main(argv=None):
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="生成冻结规则包 data/rules/")
    parser.add_argument("--check", action="store_true", help="与入库件逐字节比对（不写盘）")
    args = parser.parse_args(argv)

    outputs = build_outputs()
    if args.check:
        diffs = compare_outputs(ROOT, outputs)
        if diffs:
            print("FROZEN_RULES_DRIFT：%d 个文件与重生成不一致：" % len(diffs))
            for item in diffs:
                print("  - %s" % item)
            return 1
        print("FROZEN_RULES_OK：%d 个文件与重生成位级一致" % len(outputs))
        return 0

    write_outputs(ROOT, outputs)
    for rel in sorted(outputs):
        print("写入 %s（%d 字节）" % (rel, len(outputs[rel])))
    return 0


if __name__ == "__main__":
    sys.exit(main())

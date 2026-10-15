"""gen_samples.py — 合成账单样例 + 真值台账生成器（M1，同源同一次运行）。

产出：

- ``data/samples/*``：三平台（微信/支付宝/银行）CSV/XLSX 合成账单，
  按形态矩阵（plan/04 §三）刻意注入全部导入/语义/去重/订阅形态；
- ``data/truth/truth.json``：真值台账——**只存输入与期望，观测由基准运行时实算**
  （出现 ``observed`` 类字段即门禁报红）；含覆盖度双登记（总数/采样数/清单）。

纪律（写入本脚本）：

- 自研 splitmix64；**禁 stdlib random、禁 set 迭代序、禁系统时钟**；产物无时间戳；
- XLSX：``ZIP_STORED`` + ``create_system=0`` + 固定 ``date_time`` → 跨平台重生成位级一致；
- 假商户白名单硬校验：样例中任何对手方必须含白名单名（白名单见 data/README.md §三）；
- 卡号黑名单自检：全部产物文本禁止出现 13~19 位连续数字（账户一律 ``****0000`` 占位）；
- ``--check``：重生成到内存与入库件逐字节比对（禁手改入库件）。
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _frozen_common import (  # noqa: E402
    SplitMix64,
    compare_outputs,
    dumps_json_bytes,
    ensure_utf8_stdio,
    write_outputs,
    xlsx_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
GEN_VERSION = 1
SEED = 20261015
BASIS_DATE = "2026-10-15"

# 假商户白名单（与 data/README.md §三 双登记；白名单外名称禁止出现在任何样例/真值）
WHITELIST = [
    "示例便利店甲",
    "示例快餐乙",
    "示例超市丙",
    "示例咖啡丁",
    "示例视频会员",
    "示例音乐会员",
    "示例云盘会员",
    "示例健身月卡",
    "示例本人卡A",
    "示例本人卡B",
    "示例同事张三",
    "示例房东李四",
    "示例打车平台",
    "示例话费充值",
    "示例医院门诊",
]

# 卡号黑名单：13~19 位连续数字（禁止可识别为真实卡号的数字串）
_CARD_RE = re.compile(r"\d{13,19}")

# 形态矩阵常量集（覆盖度分母的唯一来源；生成器强制"全注入"，缺失即构建失败）
FORM_IDS = {
    "import": [
        "enc_utf8_bom",
        "enc_utf8_no_bom",
        "enc_gbk",
        "enc_gb18030",
        "enc_bad",
        "header_ads_alipay",
        "header_ads_wechat",
        "col_synonym_variant",
        "col_space_variant",
        "col_unregistered",
        "amount_thousands",
        "amount_currency_symbol",
        "amount_split_columns",
        "amount_direction_column",
        "amount_neutral",
        "row_amount_not_numeric",
        "row_amount_missing",
        "row_time_unparseable",
        "row_column_count_mismatch",
        "file_empty",
        "file_header_only",
        "file_missing_required_column",
        "file_bad_encoding",
        "ftype_wechat_csv",
        "ftype_wechat_xlsx",
        "ftype_alipay_csv",
        "ftype_bank_csv",
        "ftype_bank_xlsx",
    ],
    "semantic": [
        "消费",
        "本人转账",
        "退款",
        "AA回款",
        "报销",
        "未知",
        "distractor_keyword_wrong_direction",
        "distractor_transfer_word_income",
    ],
    "dedup": [
        "cross_platform_2_platform",
        "cross_platform_3_platform",
        "boundary_exactly_window",
        "boundary_beyond_window",
        "same_platform_candidate",
        "fp_same_amount_over_window",
        "fp_diff_amount_within_window",
        "fp_one_cent_within_window",
    ],
    "subscription": [
        "monthly_plain",
        "price_rise",
        "quarterly",
        "yearly",
        "gap_interrupted",
        "non_periodic_distractor",
    ],
}

# 平台去向（去重/订阅口径引用 manifest 的 platform_priority，这里仅排序用）
_PLATFORM_PRIORITY = ["wechat", "alipay", "bank"]

_WECHAT_HEADER = [
    "交易时间",
    "交易类型",
    "交易对方",
    "商品",
    "收/支",
    "金额(元)",
    "支付方式",
    "当前状态",
    "交易单号",
    "商户单号",
]
_ALIPAY_HEADER = ["交易号", "交易创建时间", "交易对方", "商品说明", "金额（元）", "收/支", "交易状态"]
_ALIPAY_HEADER_DRIFT = [
    "交易号 ",
    "交易创建时间 ",
    "交易对象",
    "商品说明",
    "金额(元) ",
    " 收/支",
    "交易状态",
    "商户编号",
]
_BANK_HEADER = ["交易日期", "交易时间", "摘要", "对方户名", "支出金额", "收入金额", "账户尾号"]
_BANK_HEADER_MISSING_COL = ["交易日期", "交易时间", "摘要", "支出金额", "收入金额", "账户尾号"]


def _amt(cents):
    return "%d.%02d" % (cents // 100, cents % 100)


def _amt_thousands(cents):
    return "{:,}.{:02d}".format(cents // 100, cents % 100)


class _Builder:
    """构造期状态：文件行、key 注册表、覆盖度登记。"""

    def __init__(self):
        self.files = []          # [{name, platform, fmt, encoding, header, ads, rows, file_issue, note}]
        self.keys = {}           # scenario key -> {"row_id", "time", "platform", "file"}
        self.coverage = {}       # category -> form -> [items]
        self.texts = []          # 全部产物文本（白名单/卡号自检扫描面）
        self.rng = SplitMix64(SEED)
        self._order_no = 0

    # -- 覆盖度登记 ---------------------------------------------------------
    def cov(self, category, form, item):
        self.coverage.setdefault(category, {}).setdefault(form, []).append(item)

    # -- 文件登记 -----------------------------------------------------------
    def add_file(self, name, platform, fmt, encoding, ads, header, note=""):
        spec = {
            "name": name,
            "platform": platform,
            "fmt": fmt,
            "encoding": encoding,
            "ads": list(ads),
            "header": list(header),
            "rows": [],
            "file_issue": None,
            "note": note,
        }
        self.files.append(spec)
        return spec

    def add_row(self, spec, row):
        """row: dict（tx 或 raw 行）；返回该行在文件中的物理行号（1-based，含表头广告行）。"""
        row = dict(row)
        row["_lineno"] = len(spec["ads"]) + 1 + len(spec["rows"]) + 1
        spec["rows"].append(row)
        return row["_lineno"]

    # -- 行构造 -------------------------------------------------------------
    def tx(
        self,
        t,
        cents,
        cp,
        desc,
        dir_text,
        key=None,
        label=None,
        note="",
        amount_cell=None,
        status="ok",
        code=None,
        type_text=None,
    ):
        row = {
            "kind": "tx",
            "t": t,
            "cents": cents,
            "cp": cp,
            "desc": desc,
            "dir_text": dir_text,
            "key": key,
            "label": label,
            "note": note,
            "amount_cell": amount_cell,
            "status": status,
            "code": code,
            "type_text": type_text or ("商户消费" if label == "消费" else "转账"),
        }
        if cents is not None:
            row.setdefault("oid", "WX2026%04d" % (1000 + len(self.keys)))
        return row

    def register_key(self, key, spec, lineno):
        if key in self.keys:
            raise AssertionError("scenario key 重复：%s" % key)
        self.keys[key] = {
            "row_id": "%s#%d" % (spec["name"], lineno),
            "time": None,  # 由调用方补
            "platform": spec["platform"],
            "file": spec["name"],
        }

    # -- 渲染 ---------------------------------------------------------------
    def render(self, spec):
        """渲染为一个文件的文本行列表（unicode）。只支持 CSV 系；XLSX 另见 render_xlsx。"""
        lines = list(spec["ads"]) + ["\t".join(spec["header"])]
        for row in spec["rows"]:
            if row["kind"] == "raw":
                lines.append("\t".join(row["fields"]))
                continue
            lines.append("\t".join(self.render_tx_fields(spec, row)))
        return lines

    def render_tx_fields(self, spec, row):
        """按平台渲染 tx 行字段列表。金额列等形态变体经 amount_cell 覆盖。"""
        t = row["t"]
        if spec["platform"] == "wechat":
            amount = row["amount_cell"]
            if amount is None and row["cents"] is not None:
                amount = ("\u00a5" if spec["encoding"] != "gbk" else "\uffe5") + _amt(row["cents"])
            if amount is None:
                amount = ""
            oid = row.get("oid", "")
            mid = "M" + oid[2:] if oid else ""
            return [
                t,
                row["type_text"],
                row["cp"],
                row["desc"],
                row["dir_text"] or "",
                amount,
                "零钱",
                "支付成功",
                oid,
                mid,
            ]
        if spec["platform"] == "alipay":
            amount = row["amount_cell"]
            if amount is None and row["cents"] is not None:
                amount = _amt(row["cents"])
            if amount is None:
                amount = ""
            fields = [
                "ALI" + t.replace("-", "").replace(":", "").split(" ")[0],
                t,
                row["cp"],
                row["desc"],
                amount,
                row["dir_text"] or "",
                "交易成功",
            ]
            if len(spec["header"]) == 8:  # 漂移版：追加未登记列 商户编号
                fields.append("MCH-001")
            return fields
        if spec["platform"] == "bank":
            date, hms = t.split(" ")
            expense = income = ""
            if row["cents"] is not None:
                cell = row["amount_cell"]
                text = cell if cell is not None else _amt(row["cents"])
                if row["dir_text"] == "支出":
                    expense = text
                elif row["dir_text"] == "收入":
                    income = text
            return [date, hms, row["desc"], row["cp"], expense, income, "****0000"]
        raise AssertionError("未知平台：%s" % spec["platform"])

    def render_xlsx(self, spec):
        """渲染为二维字符串表（含表头行）。"""
        rows = [list(spec["header"])]
        for row in spec["rows"]:
            rows.append(self.render_tx_fields(spec, row))
        return rows

    # -- 文本收集（自检扫描面） ---------------------------------------------
    def collect_text(self, text):
        self.texts.append(text)


def _build_all():
    b = _Builder()

    # =====================================================================
    # 1) wechat-demo-01.csv — UTF-8 无 BOM；3 平台 2 平台簇 + 边界 + 反例 +
    #    订阅月付/中断 + 干扰例 + 本人转账 + 未知（房租）
    # =====================================================================
    f = b.add_file(
        "wechat-demo-01.csv",
        "wechat",
        "csv",
        "utf-8",
        [
            "微信支付账单明细，账户：示例账号（尾号****0000）",
            "导出类型：【全部票据】；导出时间：2026-10-01",
        ],
        _WECHAT_HEADER,
        note="微信式广告行（2 行）+ 核心形态",
    )
    b.cov("import", "enc_utf8_no_bom", "wechat-demo-01.csv")
    b.cov("import", "header_ads_wechat", "wechat-demo-01.csv")
    b.cov("import", "ftype_wechat_csv", "wechat-demo-01.csv")
    b.cov("import", "amount_currency_symbol", "wechat-demo-01.csv")
    b.cov("import", "amount_direction_column", "wechat-demo-01.csv")

    seq = [
        ("SUB-健身-1", "2026-04-03 08:00:00", 19900, "示例健身月卡", "月卡续费"),
        ("SUB-健身-2", "2026-05-03 08:00:00", 19900, "示例健身月卡", "月卡续费"),
        ("SUB-健身-3", "2026-07-03 08:00:00", 19900, "示例健身月卡", "月卡续费"),
        ("SUB-视频-1", "2026-07-05 10:00:00", 2500, "示例视频会员", "会员服务费"),
        ("DIST-打车-1", "2026-07-07 18:20:00", 2500, "示例打车平台", "行程费"),
        ("SUB-健身-4", "2026-08-03 08:00:00", 19900, "示例健身月卡", "月卡续费"),
        ("C1-w", "2026-08-03 12:00:00", 1250, "示例便利店甲", "扫码支付"),
        ("SUB-视频-2", "2026-08-04 10:00:00", 2500, "示例视频会员", "会员服务费"),
        ("FP-便利店-w2", "2026-08-05 12:00:00", 1250, "示例便利店甲", "扫码支付"),
        ("C2-w", "2026-08-10 19:00:00", 3580, "示例快餐乙", "订单支付"),
        ("C3-w", "2026-08-15 10:00:00", 8800, "示例超市丙", "采购"),
        ("FP-咖啡-w1", "2026-08-16 09:00:00", 2200, "示例咖啡丁", "咖啡"),
        ("DIST-打车-2", "2026-08-19 18:35:00", 2500, "示例打车平台", "行程费"),
        ("FP-咖啡-w2", "2026-08-20 09:00:00", 2200, "示例咖啡丁", "咖啡"),
        ("S1-w1", "2026-08-20 14:30:00", 6600, "示例打车平台", "行程费"),
        ("S1-w2", "2026-08-20 14:30:00", 6600, "示例打车平台", "行程费"),
        ("DIST-退款词", "2026-08-22 12:00:00", 3300, "示例超市丙", "已申请退款"),
        ("TR-卡A", "2026-08-25 15:00:00", 100000, "示例本人卡A", "转账-本人卡A"),
        ("UNK-李四", "2026-09-01 09:00:00", 350000, "示例房东李四", "房租-2026年9月"),
        ("SUB-视频-3", "2026-09-03 10:00:00", 2500, "示例视频会员", "会员服务费"),
        ("DIST-打车-3", "2026-09-21 18:40:00", 2500, "示例打车平台", "行程费"),
    ]
    labels = {
        "TR-卡A": "本人转账",
        "UNK-李四": "未知",
        "DIST-退款词": "消费",
    }
    for key, t, cents, cp, desc in seq:
        label = labels.get(key)
        if label is None and key.startswith("SUB-"):
            label = "消费"
        if label is None and not key.startswith(("C", "FP", "S1", "DIST")):
            label = "消费"
        if label is None and key.startswith(("C", "FP", "S1")):
            label = "消费"
        row = b.tx(t, cents, cp, desc, "支出", key=key, label=label)
        lineno = b.add_row(f, row)
        b.register_key(key, f, lineno)
        b.keys[key]["time"] = t

    # 语义形态登记
    b.cov("semantic", "本人转账", "TR-卡A")
    b.cov("semantic", "未知", "UNK-李四")
    b.cov("semantic", "distractor_keyword_wrong_direction", "DIST-退款词")
    b.cov("semantic", "消费", "C1-w")
    # 订阅登记
    b.cov("subscription", "gap_interrupted", "SUB-健身")
    b.cov("subscription", "monthly_plain", "SUB-视频")
    b.cov("subscription", "non_periodic_distractor", "DIST-打车")
    # 去重登记
    b.cov("dedup", "cross_platform_2_platform", "C1")
    b.cov("dedup", "cross_platform_3_platform", "C2")
    b.cov("dedup", "boundary_exactly_window", "C3")
    b.cov("dedup", "same_platform_candidate", "S1")
    b.cov("dedup", "fp_same_amount_over_window", "FP-便利店跨天")
    b.cov("dedup", "fp_same_amount_over_window", "FP-咖啡跨天")

    # =====================================================================
    # 2) wechat-demo-02.csv — GBK；千分位 + 行级异常（时间/金额空/列数）
    # =====================================================================
    f = b.add_file(
        "wechat-demo-02.csv",
        "wechat",
        "csv",
        "gbk",
        [
            "微信支付账单明细",
            "导出时间：2026-10-02 10:00:00",
            "以下是账单明细（含全部干扰与异常样例）",
        ],
        _WECHAT_HEADER,
        note="GBK 编码 + 千分位 + 3 类行级异常",
    )
    b.cov("import", "enc_gbk", "wechat-demo-02.csv")
    b.cov("import", "header_ads_wechat", "wechat-demo-02.csv")
    b.cov("import", "ftype_wechat_csv", "wechat-demo-02.csv")
    b.cov("import", "amount_thousands", "wechat-demo-02.csv")
    rows2 = [
        b.tx("2026-08-12 08:10:00", 990, "示例便利店甲", "扫码支付", "支出", label="消费"),
        b.tx("2026-08-13 25:61:00", 1800, "示例便利店甲", "扫码支付", "支出", status="invalid", code="time_unparseable"),
        b.tx("2026-08-14 09:30:00", 2800, "示例快餐乙", "订单支付", "支出", status="invalid", code="amount_missing", amount_cell=""),
        b.tx("2026-08-15 10:00:00", 5000, "示例超市丙", "采购", "支出", status="invalid", code="column_count_mismatch"),
        b.tx("2026-08-16 19:20:00", 2800, "示例快餐乙", "订单支付", "支出", label="消费"),
        b.tx("2026-09-25 11:00:00", 103450, "示例话费充值", "充值", "支出", label="消费", amount_cell="\uffe5" + _amt_thousands(103450)),
    ]
    for row in rows2:
        lineno = b.add_row(f, row)
        b.cov("import", "row_amount_missing", "wechat-demo-02.csv") if row["code"] == "amount_missing" else None
        b.cov("import", "row_time_unparseable", "wechat-demo-02.csv") if row["code"] == "time_unparseable" else None
        if row["code"] == "column_count_mismatch":
            b.cov("import", "row_column_count_mismatch", "wechat-demo-02.csv")
            # 该行渲染时追加 1 个多余字段（列数不匹配 → 行级拒绝）
            row["_extra_fields"] = 1
    _ = lineno

    # =====================================================================
    # 3) wechat-demo-03.xlsx — XLSX；退款/AA回款/本人转账(收入) + 3 平台簇 C4 的微信腿
    # =====================================================================
    f = b.add_file(
        "wechat-demo-03.xlsx",
        "wechat",
        "xlsx",
        "xlsx",
        [],
        _WECHAT_HEADER,
        note="XLSX（自写确定性 writer；ZIP_STORED + 固定 date_time）",
    )
    b.cov("import", "ftype_wechat_xlsx", "wechat-demo-03.xlsx")
    rows3 = [
        b.tx("2026-07-20 14:00:00", 4200, "示例超市丙", "退款-订单WX0718-01", "收入", key="R10-退款1", label="退款", type_text="退款"),
        b.tx("2026-08-01 19:30:00", 5800, "示例同事张三", "AA回款-聚餐", "收入", key="R20-AA1", label="AA回款", type_text="转账"),
        b.tx("2026-08-30 10:00:00", 200000, "示例本人卡B", "转入-本人卡B", "收入", key="TR-卡B入", label="本人转账", type_text="转账"),
        b.tx("2026-09-01 11:00:00", 15670, "示例超市丙", "采购", "支出", key="C4-w", label="消费"),
        b.tx("2026-09-10 08:45:00", 1990, "示例咖啡丁", "咖啡", "支出", label="消费"),
        b.tx("2026-09-12 21:00:00", 750, "示例便利店甲", "扫码支付", "支出", label="消费"),
    ]
    for row in rows3:
        lineno = b.add_row(f, row)
        if row["key"]:
            b.register_key(row["key"], f, lineno)
            b.keys[row["key"]]["time"] = row["t"]
    b.cov("semantic", "退款", "R10-退款1")
    b.cov("semantic", "AA回款", "R20-AA1")
    b.cov("semantic", "本人转账", "TR-卡B入")
    b.cov("dedup", "cross_platform_2_platform", "C4")

    # =====================================================================
    # 4) wechat-demo-bad-encoding.csv — 故意坏编码（UTF-8/GB18030 均不可解码）
    # =====================================================================
    b.cov("import", "enc_bad", "wechat-demo-bad-encoding.csv")
    b.cov("import", "file_bad_encoding", "wechat-demo-bad-encoding.csv")

    # =====================================================================
    # 5) alipay-demo-01.csv — GB18030；支付宝式 3 行广告 + 音乐会员涨价序列 +
    #    未知（医院/同事转账词）+ 报销 + C1/C2/C3 腿 + 反例
    # =====================================================================
    f = b.add_file(
        "alipay-demo-01.csv",
        "alipay",
        "csv",
        "gb18030",
        [
            "支付宝交易明细（示例合成数据，非真实账单）",
            "说明：本文件由 tools/gen_samples.py 程序化产出，仅用于演示与自检",
            "交易流水按创建时间排序",
        ],
        _ALIPAY_HEADER,
        note="支付宝式广告行（3 行）；GB18030 编码",
    )
    b.cov("import", "enc_gb18030", "alipay-demo-01.csv")
    b.cov("import", "header_ads_alipay", "alipay-demo-01.csv")
    b.cov("import", "ftype_alipay_csv", "alipay-demo-01.csv")
    b.cov("import", "amount_direction_column", "alipay-demo-01.csv")

    seq5 = [
        ("SUB-音乐-1", "2026-05-10 10:30:00", 1500, "示例音乐会员", "会员服务费", "支出", "消费"),
        ("SUB-音乐-2", "2026-06-10 10:30:00", 1500, "示例音乐会员", "会员服务费", "支出", "消费"),
        ("SUB-音乐-3", "2026-07-10 10:30:00", 1500, "示例音乐会员", "会员服务费", "支出", "消费"),
        ("UNK-医院", "2026-07-15 09:30:00", 24000, "示例医院门诊", "门诊缴费", "支出", "未知"),
        ("C1-a", "2026-08-03 12:00:30", 1250, "示例便利店甲", "扫码支付", "支出", "消费"),
        ("SUB-音乐-4", "2026-08-10 10:30:00", 1800, "示例音乐会员", "会员服务费", "支出", "消费"),
        ("FP-快餐-a2", "2026-08-10 19:00:30", 3680, "示例快餐乙", "订单支付", "支出", "消费"),
        ("C2-a", "2026-08-10 19:00:45", 3580, "示例快餐乙", "订单支付", "支出", "消费"),
        ("FP-8801", "2026-08-15 10:00:30", 8801, "示例超市丙", "采购", "支出", "消费"),
        ("C3-a", "2026-08-15 10:02:00", 8800, "示例超市丙", "采购", "支出", "消费"),
        ("FP-咖啡-a", "2026-08-16 09:02:01", 2200, "示例咖啡丁", "咖啡", "支出", "消费"),
        ("R30-报销", "2026-08-28 16:00:00", 35000, "示例同事张三", "报销款-8月差旅", "收入", "报销"),
        ("R10-退款2", "2026-09-12 15:00:00", 6800, "示例超市丙", "退款-订单AL0908", "收入", "退款"),
        ("UNK-张三转账", "2026-09-05 20:00:00", 12000, "示例同事张三", "转账", "收入", "未知"),
        ("SUB-音乐-5", "2026-09-10 10:30:00", 1800, "示例音乐会员", "会员服务费", "支出", "消费"),
        ("FILL-A1", "2026-09-28 12:30:00", 1560, "示例便利店甲", "扫码支付", "支出", "消费"),
    ]
    for key, t, cents, cp, desc, dir_text, label in seq5:
        type_text = "退款" if label == "退款" else ("转账" if label in ("本人转账", "AA回款") else "商户消费")
        row = b.tx(t, cents, cp, desc, dir_text, key=key, label=label, type_text=type_text)
        lineno = b.add_row(f, row)
        b.register_key(key, f, lineno)
        b.keys[key]["time"] = t
    b.cov("semantic", "报销", "R30-报销")
    b.cov("semantic", "退款", "R10-退款2")
    b.cov("semantic", "未知", "UNK-医院")
    b.cov("semantic", "distractor_transfer_word_income", "UNK-张三转账")
    b.cov("subscription", "price_rise", "SUB-音乐")
    b.cov("dedup", "boundary_beyond_window", "FP-咖啡-W+1")
    b.cov("dedup", "fp_diff_amount_within_window", "FP-快餐-a2")
    b.cov("dedup", "fp_one_cent_within_window", "FP-8801")

    # =====================================================================
    # 6) alipay-demo-02.csv — UTF-8 BOM；列名漂移（同义/空格/未登记列）+
    #    千分位/货币符号/不计收支/未登记收支撑
    # =====================================================================
    f = b.add_file(
        "alipay-demo-02.csv",
        "alipay",
        "csv",
        "utf-8-sig",
        [
            "支付宝交易明细（示例合成数据，列名漂移版）",
            "说明：表头含同义列名、空格变体与未登记列",
        ],
        _ALIPAY_HEADER_DRIFT,
        note="UTF-8 BOM + 列名漂移 + 未登记列（商户编号）",
    )
    b.cov("import", "enc_utf8_bom", "alipay-demo-02.csv")
    b.cov("import", "header_ads_alipay", "alipay-demo-02.csv")
    b.cov("import", "ftype_alipay_csv", "alipay-demo-02.csv")
    b.cov("import", "col_synonym_variant", "交易对象")
    b.cov("import", "col_space_variant", "金额(元) / 收/支 前后空格")
    b.cov("import", "col_unregistered", "商户编号")
    b.cov("import", "amount_thousands", "alipay-demo-02.csv")
    b.cov("import", "amount_currency_symbol", "alipay-demo-02.csv")
    b.cov("import", "amount_direction_column", "alipay-demo-02.csv")
    b.cov("import", "amount_neutral", "alipay-demo-02.csv")

    rows6 = [
        b.tx("2026-09-15 12:00:00", 123456, "示例超市丙", "采购", "支出", label="消费", amount_cell=_amt_thousands(123456)),
        b.tx("2026-09-16 08:30:00", 2390, "示例便利店甲", "扫码支付", "支出", label="消费", amount_cell="\uffe5" + _amt(2390)),
        b.tx("2026-09-18 21:00:00", 80000, "示例本人卡B", "转账-本人卡B", "支出", key="TR-卡B出", label="本人转账"),
        b.tx("2026-09-18 21:05:00", 50000, "示例本人卡A", "账户划转", "不计收支", key="TR-卡A中性", label="本人转账"),
        b.tx("2026-09-20 12:00:00", 2500, "示例医院门诊", "门诊缴费", "其他", key="UNK-其他方向", label="未知", status="unknown", code="unmapped_direction"),
        b.tx("2026-09-22 19:10:00", 3250, "示例快餐乙", "订单支付", "支出", label="消费"),
    ]
    for row in rows6:
        lineno = b.add_row(f, row)
        if row["key"]:
            b.register_key(row["key"], f, lineno)
            b.keys[row["key"]]["time"] = row["t"]
    b.cov("semantic", "本人转账", "TR-卡B出")
    b.cov("semantic", "本人转账", "TR-卡A中性")
    b.cov("semantic", "未知", "UNK-其他方向")

    # =====================================================================
    # 7) alipay-demo-empty.csv / alipay-demo-header-only.csv / bank-demo-missing-col.csv
    # =====================================================================
    b.cov("import", "file_empty", "alipay-demo-empty.csv")
    b.cov("import", "file_header_only", "alipay-demo-header-only.csv")
    b.cov("import", "file_missing_required_column", "bank-demo-missing-col.csv")

    # =====================================================================
    # 8) bank-demo-01.csv — UTF-8 BOM；收支分列 + 4 类行级异常 + C2/C4 银行腿
    # =====================================================================
    f = b.add_file(
        "bank-demo-01.csv",
        "bank",
        "csv",
        "utf-8-sig",
        ["示例银行储蓄卡账单（尾号****0000）", "统计期间：2026-01-01 至 2026-10-05"],
        _BANK_HEADER,
        note="收支分列 + 行级异常 4 类",
    )
    b.cov("import", "enc_utf8_bom", "bank-demo-01.csv")
    b.cov("import", "ftype_bank_csv", "bank-demo-01.csv")
    b.cov("import", "amount_split_columns", "bank-demo-01.csv")

    rows8 = [
        b.tx("2026-08-10 19:00:20", 3580, "示例快餐乙", "消费", "支出", key="C2-b", label="消费"),
        b.tx("2026-08-12 10:00:00", None, "示例便利店甲", "消费", "支出", status="invalid", code="amount_not_numeric", amount_cell="abc"),
        b.tx("2026-08-13 14:00:00", None, "示例快餐乙", "消费", "支出", status="invalid", code="amount_missing"),
        b.tx("2026-08-14 25:99:99", 1000, "示例超市丙", "消费", "支出", status="invalid", code="time_unparseable"),
        b.tx("2026-08-15 09:00:00", 2200, "示例咖啡丁", "消费", "支出", status="invalid", code="column_count_mismatch"),
        b.tx("2026-08-18 21:00:00", 300000, "示例本人卡B", "转入", "收入", key="TR-卡B-bank", label="本人转账"),
        b.tx("2026-09-01 11:01:00", 15670, "示例超市丙", "消费", "支出", key="C4-b", label="消费"),
    ]
    for row in rows8:
        lineno = b.add_row(f, row)
        if row["key"]:
            b.register_key(row["key"], f, lineno)
            b.keys[row["key"]]["time"] = row["t"]
        if row["code"] == "amount_not_numeric":
            b.cov("import", "row_amount_not_numeric", "bank-demo-01.csv")
        if row["code"] == "amount_missing":
            b.cov("import", "row_amount_missing", "bank-demo-01.csv")
        if row["code"] == "time_unparseable":
            b.cov("import", "row_time_unparseable", "bank-demo-01.csv")
        if row["code"] == "column_count_mismatch":
            b.cov("import", "row_column_count_mismatch", "bank-demo-01.csv")
    b.cov("semantic", "本人转账", "TR-卡B-bank")

    # =====================================================================
    # 9) bank-demo-02.csv — GBK；千分位 + AA收款（收入）
    # =====================================================================
    f = b.add_file(
        "bank-demo-02.csv",
        "bank",
        "csv",
        "gbk",
        ["示例银行储蓄卡账单（尾号****0000）"],
        _BANK_HEADER,
        note="GBK + 千分位",
    )
    b.cov("import", "enc_gbk", "bank-demo-02.csv")
    b.cov("import", "ftype_bank_csv", "bank-demo-02.csv")
    b.cov("import", "amount_split_columns", "bank-demo-02.csv")
    b.cov("import", "amount_thousands", "bank-demo-02.csv")
    rows9 = [
        b.tx("2026-07-12 11:00:00", 3000, "示例话费充值", "充值", "支出", label="消费"),
        b.tx("2026-08-01 20:30:00", 4520, "示例便利店甲", "消费", "支出", label="消费"),
        b.tx("2026-08-25 13:20:00", 2400, "示例快餐乙", "消费", "支出", label="消费"),
        b.tx("2026-09-20 16:40:00", 234567, "示例超市丙", "消费", "支出", label="消费", amount_cell=_amt_thousands(234567)),
        b.tx("2026-09-21 19:00:00", 6600, "示例同事张三", "AA收款", "收入", key="R20-AA2", label="AA回款"),
        b.tx("2026-09-26 09:50:00", 1680, "示例咖啡丁", "消费", "支出", label="消费"),
    ]
    for row in rows9:
        lineno = b.add_row(f, row)
        if row["key"]:
            b.register_key(row["key"], f, lineno)
            b.keys[row["key"]]["time"] = row["t"]
    b.cov("semantic", "AA回款", "R20-AA2")

    # =====================================================================
    # 10) bank-demo-03.xlsx — XLSX；季付/年付订阅 + 常规消费
    # =====================================================================
    f = b.add_file(
        "bank-demo-03.xlsx",
        "bank",
        "xlsx",
        "xlsx",
        [],
        _BANK_HEADER,
        note="XLSX：季付/年付订阅（跨年跨度）",
    )
    b.cov("import", "ftype_bank_xlsx", "bank-demo-03.xlsx")
    b.cov("import", "amount_split_columns", "bank-demo-03.xlsx")
    rows10 = [
        b.tx("2024-10-05 10:00:00", 25800, "示例视频会员", "会员服务费", "支出", key="SUB-年付-1", label="消费"),
        b.tx("2025-10-05 10:00:00", 25800, "示例视频会员", "会员服务费", "支出", key="SUB-年付-2", label="消费"),
        b.tx("2026-01-20 09:00:00", 9800, "示例云盘会员", "会员服务费", "支出", key="SUB-云盘-1", label="消费"),
        b.tx("2026-04-21 09:00:00", 9800, "示例云盘会员", "会员服务费", "支出", key="SUB-云盘-2", label="消费"),
        b.tx("2026-07-21 09:00:00", 9800, "示例云盘会员", "会员服务费", "支出", key="SUB-云盘-3", label="消费"),
        b.tx("2026-08-08 07:50:00", 3300, "示例便利店甲", "消费", "支出", label="消费"),
        b.tx("2026-08-09 12:10:00", 4150, "示例快餐乙", "消费", "支出", label="消费"),
        b.tx("2026-09-27 10:00:00", 10000, "示例话费充值", "充值", "支出", label="消费"),
        b.tx("2026-10-05 10:00:00", 25800, "示例视频会员", "会员服务费", "支出", key="SUB-年付-3", label="消费"),
    ]
    for row in rows10:
        lineno = b.add_row(f, row)
        if row["key"]:
            b.register_key(row["key"], f, lineno)
            b.keys[row["key"]]["time"] = row["t"]
    b.cov("subscription", "quarterly", "SUB-云盘")
    b.cov("subscription", "yearly", "SUB-年付")

    return b


def build_outputs():
    """构造全部样例与真值产物（``{相对路径: 字节}``；纯函数、无时钟）。"""
    b = _build_all()
    outputs = {}

    # ---- 装配特殊文件（非 tx 渲染） -------------------------------------
    by_name = {spec["name"]: spec for spec in b.files}

    # 空文件
    outputs["data/samples/alipay-demo-empty.csv"] = b""
    b.collect_text("")

    # 坏编码文件（在 UTF-8 与 GB18030 下均不可解码；非 UTF-16 BOM）
    bad = "WX-BILL-DEMO\n".encode("ascii") + b"\xff\xff\xff\xff broken bytes \xff\xff\n"
    outputs["data/samples/wechat-demo-bad-encoding.csv"] = bad
    b.collect_text("WX-BILL-DEMO\nbroken bytes\n")

    # 只有表头（支付宝式广告行 + 表头，无数据行）
    header_only_lines = [
        "支付宝交易明细（示例合成数据，空数据版）",
        "说明：仅表头、无数据行 → 文件级 invalid",
        "\t".join(_ALIPAY_HEADER),
    ]
    outputs["data/samples/alipay-demo-header-only.csv"] = ("\n".join(header_only_lines) + "\n").encode("utf-8")
    b.collect_text("\n".join(header_only_lines))

    # 缺必填列（无「对方户名」列）
    missing_col_lines = [
        "\t".join(_BANK_HEADER_MISSING_COL),
        "2026-08-01\t10:00:00\t消费\t35.80\t\t****0000",
    ]
    outputs["data/samples/bank-demo-missing-col.csv"] = ("\n".join(missing_col_lines) + "\n").encode("utf-8")
    b.collect_text("\n".join(missing_col_lines))

    # ---- 常规 CSV 渲染 ----------------------------------------------------
    for spec in b.files:
        if spec["fmt"] != "csv":
            continue
        lines = b.render(spec)
        # 列数不匹配行：追加多余字段（故意错位）
        fixed_lines = []
        for idx, line in enumerate(lines):
            row = None
            if idx >= len(spec["ads"]) + 1:
                row = spec["rows"][idx - len(spec["ads"]) - 1]
            if row is not None and row.get("_extra_fields"):
                line = line + "\tEXTRA"
            fixed_lines.append(line)
        text = "\n".join(fixed_lines) + "\n"
        outputs["data/samples/%s" % spec["name"]] = text.encode(spec["encoding"])
        b.collect_text(text)

    # ---- XLSX 渲染 --------------------------------------------------------
    for spec in b.files:
        if spec["fmt"] != "xlsx":
            continue
        table = b.render_xlsx(spec)
        outputs["data/samples/%s" % spec["name"]] = xlsx_bytes(table)
        b.collect_text("\n".join("\t".join(r) for r in table))

    # ---- 自检（白名单 / 卡号黑名单） --------------------------------------
    _self_check(b, outputs)

    # ---- 真值台账 ---------------------------------------------------------
    truth = _build_truth(b)
    outputs["data/truth/truth.json"] = dumps_json_bytes(truth)

    # ---- 覆盖度守门：分子必须等于分母（形态常量集全注入） -----------------
    expected = set(FORM_IDS.keys())
    actual = set(b.coverage.keys())
    if expected != actual:
        raise AssertionError("覆盖度类别缺口：%s" % (expected ^ actual))
    for category, forms in FORM_IDS.items():
        got = set(b.coverage[category].keys())
        if got != set(forms):
            raise AssertionError(
                "覆盖度形态缺口（%s）：%s" % (category, set(forms) ^ got)
            )
    return outputs


def _self_check(b, outputs):
    """白名单硬校验 + 卡号黑名单自检（扫描全部产物文本）。"""
    for spec in b.files:
        for row in spec["rows"]:
            if row["kind"] == "tx" and row["cp"]:
                if not any(name in row["cp"] for name in WHITELIST):
                    raise AssertionError(
                        "白名单外对手方：%s（文件 %s）" % (row["cp"], spec["name"])
                    )
    joined = "\n".join(b.texts)
    hit = _CARD_RE.search(joined)
    if hit:
        raise AssertionError("卡号黑名单命中：%s（禁止 13~19 位连续数字）" % hit.group(0))
    if not outputs:
        raise AssertionError("产物为空")


def _row_expect(spec, row, lineno):
    """由行构造 expect_import 条目。"""
    rid = "%s#%d" % (spec["name"], lineno)
    if row["status"] == "ok":
        return rid, {"status": "ok"}
    return rid, {"status": row["status"], "code": row["code"]}


def _build_truth(b):
    """组装真值台账（只存输入与期望；覆盖度双登记）。"""
    files_meta = []
    expect_import = {}
    expect_semantic = {}

    file_issues_defined = {
        "wechat-demo-bad-encoding.csv": ("invalid", ["encoding_undetermined"]),
        "alipay-demo-empty.csv": ("invalid", ["empty_file"]),
        "alipay-demo-header-only.csv": ("invalid", ["no_data_rows"]),
        "bank-demo-missing-col.csv": ("invalid", ["required_column_missing"]),
    }

    for spec in b.files:
        name = spec["name"]
        source = "data/samples/%s" % name
        if name in file_issues_defined:
            status, codes = file_issues_defined[name]
            files_meta.append(
                {
                    "file": source,
                    "platform": spec["platform"],
                    "format": spec["fmt"],
                    "encoding_expected": spec["encoding"],
                    "file_status": status,
                    "file_issue_codes": codes,
                    "note": spec["note"],
                }
            )
            expect_import[source] = {"file_status": status, "file_issue_codes": codes, "rows": {}}
            continue

        rows_map = {}
        for row in spec["rows"]:
            if row["kind"] != "tx":
                continue
            rid, entry = _row_expect(spec, row, row["_lineno"])
            rows_map[rid] = entry
            if row["label"] is not None:
                expect_semantic[rid] = {
                    "label": row["label"],
                    "scenario": row["key"],
                    "note": row["note"],
                }
        column_issues = []
        if name == "alipay-demo-02.csv":
            column_issues.append(
                {"kind": "unknown", "code": "unknown_column", "column": "商户编号"}
            )
        files_meta.append(
            {
                "file": source,
                "platform": spec["platform"],
                "format": spec["fmt"],
                "encoding_expected": spec["encoding"],
                "file_status": "ok",
                "file_issue_codes": [],
                "note": spec["note"],
            }
        )
        expect_import[source] = {
            "file_status": "ok",
            "file_issue_codes": [],
            "column_issues": column_issues,
            "rows": rows_map,
        }

    # ---- 去重期望 ---------------------------------------------------------
    def rid(key):
        return b.keys[key]["row_id"]

    def representative(keys):
        def sort_key(key):
            info = b.keys[key]
            return (info["time"], _PLATFORM_PRIORITY.index(info["platform"]), info["row_id"])

        return rid(min(keys, key=sort_key))

    clusters = [
        {
            "cluster_id": "C1",
            "verdict": "duplicate_cross_platform",
            "members": [rid("C1-w"), rid("C1-a")],
            "representative": representative(["C1-w", "C1-a"]),
            "note": "2 平台簇；代表笔按（时间最早 → 平台优先级 → 行号）",
        },
        {
            "cluster_id": "C2",
            "verdict": "duplicate_cross_platform",
            "members": [rid("C2-w"), rid("C2-b"), rid("C2-a")],
            "representative": representative(["C2-w", "C2-b", "C2-a"]),
            "note": "3 平台簇",
        },
        {
            "cluster_id": "C3",
            "verdict": "duplicate_cross_platform",
            "members": [rid("C3-w"), rid("C3-a")],
            "representative": representative(["C3-w", "C3-a"]),
            "note": "窗口边界：Δt=W=120s 恰好命中（闭区间）",
        },
        {
            "cluster_id": "C4",
            "verdict": "duplicate_cross_platform",
            "members": [rid("C4-w"), rid("C4-b")],
            "representative": representative(["C4-w", "C4-b"]),
            "note": "XLSX↔CSV 跨平台簇",
        },
        {
            "cluster_id": "S1",
            "verdict": "candidate_same_platform",
            "members": [rid("S1-w1"), rid("S1-w2")],
            "note": "同平台同金额同时刻：不合并，显式标注待人工复核",
        },
    ]
    must_not_merge = [
        {
            "pair": [rid("FP-咖啡-w1"), rid("FP-咖啡-a")],
            "form": "boundary_beyond_window",
            "note": "Δt=W+1s=121s：不合并",
        },
        {
            "pair": [rid("FP-咖啡-w1"), rid("FP-咖啡-w2")],
            "form": "fp_same_amount_over_window",
            "note": "同商户同金额跨天：不合并",
        },
        {
            "pair": [rid("C1-w"), rid("FP-便利店-w2")],
            "form": "fp_same_amount_over_window",
            "note": "同商户同金额跨天：不合并",
        },
        {
            "pair": [rid("FP-快餐-a2"), rid("C2-a")],
            "form": "fp_diff_amount_within_window",
            "note": "窗内同商户不同金额：不合并",
        },
        {
            "pair": [rid("FP-8801"), rid("C3-a")],
            "form": "fp_one_cent_within_window",
            "note": "窗内同商户同金额差 1 分：不合并",
        },
    ]

    # ---- 订阅期望 ---------------------------------------------------------
    def rids(*keys):
        return [rid(k) for k in keys]

    expect_subscription = [
        {
            "subscription_id": "SUB-A",
            "expect_form": "monthly_plain",
            "merchant": "示例视频会员",
            "amounts": ["25.00"],
            "period": "monthly",
            "entries": rids("SUB-视频-1", "SUB-视频-2", "SUB-视频-3"),
            "price_changes": [],
            "gaps": [],
            "note": "月付：间隔 30/30 天（容差 ±2）",
        },
        {
            "subscription_id": "SUB-B",
            "expect_form": "price_rise",
            "merchant": "示例音乐会员",
            "amounts": ["15.00", "18.00"],
            "period": "monthly",
            "entries": rids("SUB-音乐-1", "SUB-音乐-2", "SUB-音乐-3", "SUB-音乐-4", "SUB-音乐-5"),
            "price_changes": [
                {"entry": rid("SUB-音乐-4"), "from_amount": "15.00", "to_amount": "18.00"}
            ],
            "gaps": [],
            "note": "涨价序列：仅记录观测到的变动，不做预测",
        },
        {
            "subscription_id": "SUB-C",
            "expect_form": "quarterly",
            "merchant": "示例云盘会员",
            "amounts": ["98.00"],
            "period": "quarterly",
            "entries": rids("SUB-云盘-1", "SUB-云盘-2", "SUB-云盘-3"),
            "price_changes": [],
            "gaps": [],
            "note": "季付：间隔 91/91 天（容差 ±3）",
        },
        {
            "subscription_id": "SUB-D",
            "expect_form": "yearly",
            "merchant": "示例视频会员",
            "amounts": ["258.00"],
            "period": "yearly",
            "entries": rids("SUB-年付-1", "SUB-年付-2", "SUB-年付-3"),
            "price_changes": [],
            "gaps": [],
            "note": "年付：间隔 365/365 天（容差 ±5）",
        },
        {
            "subscription_id": "SUB-E",
            "expect_form": "gap_interrupted",
            "merchant": "示例健身月卡",
            "amounts": ["199.00"],
            "period": "monthly",
            "entries": rids("SUB-健身-1", "SUB-健身-2", "SUB-健身-3", "SUB-健身-4"),
            "price_changes": [],
            "gaps": ["2026-06"],
            "note": "周期中断（漏 2026-06 一期）：规则写死并测试（M4 定稿）",
        },
    ]
    non_periodic_distractor = {
        "expect_form": "non_periodic_distractor",
        "merchant": "示例打车平台",
        "amounts": ["25.00", "66.00"],
        "entries": rids("DIST-打车-1", "DIST-打车-2", "DIST-打车-3"),
        "note": "非周期相似金额：不得判为订阅（间隔 43/33 天不落任何周期容差）",
    }

    # ---- 覆盖度双登记 -----------------------------------------------------
    coverage = {}
    for category, forms in FORM_IDS.items():
        coverage[category] = {}
        for form in forms:
            items = sorted(b.coverage[category][form])
            coverage[category][form] = {
                "total": len(items),
                "sampled": len(items),
                "items": items,
            }

    # 「未知」注入存在性专门断言
    unknown_rows = [
        k for k, v in expect_semantic.items() if v.get("label") == "未知"
    ]
    if not unknown_rows:
        raise AssertionError("『未知』必须被注入（当前 0 例）")

    truth = {
        "schema_version": 1,
        "kind": "truth-ledger",
        "generator": "tools/gen_samples.py",
        "generator_version": GEN_VERSION,
        "seed": SEED,
        "basis_date": BASIS_DATE,
        "rules_dependency": (
            "参数口径引用 data/rules/manifest.json（dedup_window_seconds=120 / "
            "subscription_min_repeats=3 / period_table 等）；真值只存输入与期望，"
            "观测由基准运行时实算（禁止观测类字段，门禁扫描面见测试）"
        ),
        "files": files_meta,
        "coverage": coverage,
        "expect_import": expect_import,
        "expect_semantic": expect_semantic,
        "expect_dedup": {
            "clustering_note": (
                "聚类键=（归一对手方,金额,方向）；组内按时间排序链式相邻聚类，"
                "闭区间 |Δt| ≤ W（W=manifest.dedup_window_seconds）；"
                "跨平台前提：簇内 ≥2 平台才判定重复"
            ),
            "clusters": clusters,
            "must_not_merge": must_not_merge,
        },
        "expect_subscription": {
            "subscriptions": expect_subscription,
            "non_periodic_distractors": [non_periodic_distractor],
        },
    }
    return truth


def main(argv=None):
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="生成合成账单样例 data/samples/ + 真值台账 data/truth/")
    parser.add_argument("--check", action="store_true", help="与入库件逐字节比对（不写盘）")
    args = parser.parse_args(argv)

    outputs = build_outputs()
    if args.check:
        diffs = compare_outputs(ROOT, outputs)
        if diffs:
            print("FROZEN_SAMPLES_DRIFT：%d 个文件与重生成不一致：" % len(diffs))
            for item in diffs:
                print("  - %s" % item)
            return 1
        print("FROZEN_SAMPLES_OK：%d 个文件与重生成位级一致" % len(outputs))
        return 0

    write_outputs(ROOT, outputs)
    for rel in sorted(outputs):
        print("写入 %s（%d 字节）" % (rel, len(outputs[rel])))
    return 0


if __name__ == "__main__":
    sys.exit(main())

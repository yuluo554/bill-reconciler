"""表头定位与列名映射（plan/03 §1.2 / §1.3）。

- 表头定位：前 N 行（manifest ``header_locate_max_scan_lines``）内找第一行
  "预期列名命中数 ≥ K（manifest ``header_locate_k``）"的行；预期列名集来自
  本模块的平台常量（列名形态与三平台官方导出一致）。失败 → ``header_not_found``。
- 列名映射：精确 → 去空白 → 别名表（``aliases.json`` 的 ``column_aliases``，
  与表头定位同源规则包）；未登记列 → unknown（入 issues，不拒行）；
  必填字段（交易时间/金额/对手方）任一列映射失败 → ``required_column_missing``。
"""

from ..errors import InputError

# 规范字段名（IR 语义字段的唯一拼法）
F_TIME = "交易时间"
F_AMOUNT = "金额"
F_DIRECTION = "收支类型"
F_COUNTERPARTY = "对手方"
F_DESCRIPTION = "商品说明"

# 必填字段（plan/03 §1.3）：任一列映射失败 → 文件级 invalid
REQUIRED_FIELDS = (F_TIME, F_AMOUNT, F_COUNTERPARTY)

# 平台 → 登记列名全集（表头定位命中判据 + unknown 判定的"已登记"边界；
# 同义/空格变体由别名层覆盖，未列名 → unknown_column）
PLATFORM_EXPECTED_COLUMNS = {
    "wechat": ["交易时间", "交易类型", "交易对方", "商品", "收/支", "金额(元)",
               "支付方式", "当前状态", "交易单号", "商户单号"],
    "alipay": ["交易号", "交易创建时间", "交易对方", "商品说明", "金额（元）",
               "收/支", "交易状态"],
    "bank": ["交易日期", "交易时间", "摘要", "对方户名", "支出金额", "收入金额",
             "账户尾号"],
}

# 表头定位的命中判据列（预期核心列；从登记列名中选取——K=2 时用于区分
# "说明文字行"与"表头行"）
PLATFORM_HEADER_ANCHORS = {
    "wechat": ["交易时间", "交易对方", "金额(元)", "收/支", "商品"],
    "alipay": ["交易创建时间", "交易对方", "金额（元）", "收/支", "商品说明"],
    "bank": ["交易日期", "交易时间", "对方户名", "支出金额", "收入金额"],
}

# 平台预期列名 → 规范字段（精确层映射）
_CANONICAL_BY_COLUMN = {
    "交易时间": F_TIME,
    "交易创建时间": F_TIME,
    "交易日期": F_TIME,
    "交易对方": F_COUNTERPARTY,
    "对方户名": F_COUNTERPARTY,
    "商品": F_DESCRIPTION,
    "商品说明": F_DESCRIPTION,
    "摘要": F_DESCRIPTION,
    "收/支": F_DIRECTION,
    "金额(元)": F_AMOUNT,
    "金额（元）": F_AMOUNT,
    "金额": F_AMOUNT,
    "支出金额": F_AMOUNT,
    "收入金额": F_AMOUNT,
}


class HeaderError(InputError):
    """表头定位失败（header_not_found）。"""


class RequiredColumnError(InputError):
    """必填列缺失（required_column_missing）。"""


def locate_header(lines, platform, header_k, max_scan_lines):
    """在前 max_scan_lines 行内定位表头行。

    返回 (header_index, header_fields)。判据：该行字段（strip 后）在平台
    表头锚定列（PLATFORM_HEADER_ANCHORS）中的命中数 ≥ header_k。
    失败抛 HeaderError（附尝试过的候选行）。
    """
    anchors = set(PLATFORM_HEADER_ANCHORS[platform])
    tried = []
    for idx, line in enumerate(lines[: max_scan_lines]):
        fields = [f.strip() for f in line.split("\t")]
        hit = sum(1 for f in fields if f in anchors)
        if hit >= header_k:
            return idx, fields
        if hit > 0:
            tried.append("第%d行（命中%d列）" % (idx + 1, hit))
    raise HeaderError(
        "表头定位失败（平台 %s，K=%d，扫描上限 %d 行；候选：%s）"
        % (platform, header_k, max_scan_lines, "；".join(tried) or "无")
    )


def _norm_cell(text):
    """列名匹配前的轻量归一：去首尾及内部全部空白（表头空格变体形态）。"""
    return "".join(text.split())


def build_column_map(header_fields, platform, column_aliases):
    """把表头字段映射到规范字段。

    ``column_aliases``：``aliases.json`` 的 ``column_aliases`` 段（条目
    ``{canonical, variants[], platforms[], notes}``）。

    返回 (field_map, unknown_columns)：
    - field_map: {规范字段名: 列下标}；同名规范字段取首个命中列
      （银行"支出金额/收入金额"两列都映射到"金额"，由解析器区分方向）；
    - unknown_columns: 未登记列名列表（入 issues，不拒行）。

    已登记但非语义的列（交易单号/支付方式/交易状态等审计列）既不进
    field_map 也不报 unknown——原值经 raw_fields 保留。
    """
    alias_lookup = {}
    for entry in column_aliases:
        if entry.get("platforms") and platform not in entry["platforms"]:
            continue
        for variant in entry["variants"]:
            alias_lookup.setdefault(_norm_cell(variant), entry["canonical"])

    registered = set(PLATFORM_EXPECTED_COLUMNS[platform])
    field_map = {}
    unknown = []
    for idx, raw in enumerate(header_fields):
        name = raw.strip()
        if not name:
            continue
        canonical = _CANONICAL_BY_COLUMN.get(name)
        if canonical is None:
            canonical = alias_lookup.get(_norm_cell(name))
        if canonical is not None:
            field_map.setdefault(canonical, idx)
        elif name not in registered:
            unknown.append(name)
    return field_map, unknown


def require_fields(field_map, source_name):
    """必填字段缺失 → RequiredColumnError（文件级失败，不猜测）。"""
    missing = [f for f in REQUIRED_FIELDS if f not in field_map]
    if missing:
        raise RequiredColumnError(
            "%s：必填列缺失（%s）" % (source_name, "、".join(missing))
        )
    return field_map

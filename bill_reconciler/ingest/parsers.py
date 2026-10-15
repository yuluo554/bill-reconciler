"""三平台行级解析器（plan/03 §1.4）。

输入：一行字段列表 + 表头字段 + 列映射（locate.build_column_map 产物）。
输出：``ParsedRow``（三态：ok / invalid / unknown）。

金额纪律：
- 去千分位（`,`）→ 去货币符号（白名单：``¥ U+00A5`` 与 ``￥ U+FFE5`` 都在列——
  GBK 通道编码不了 U+00A5，生成器按通道取值，plan/04 §二勘误）→ Decimal；
- 收支两种注入形态：收支类型列（微信/支付宝：支出/收入/不计收支）与
  收支分列（银行：支出金额/收入金额两列）；单列正负号本期未注入，
  解析器不做猜测（负号金额按"该列即金额"取绝对值，方向由列决定）；
- ``neutral``（"不计收支"）不是异常：入库只标记方向；
- 非数值/空金额/时间不可解析/列数不匹配 → 行级 invalid（宁可少一行，不可错位入库）；
- 未登记收支取值（如"其他"）→ unknown 行（入库 + issues 显式列出）。

时间纪律：``YYYY-MM-DD HH:MM:SS`` 固定格式严格解析；银行文件日期与时分秒
分列 → 先拼再解析；任何不可解析 → invalid。
"""

import datetime
from decimal import Decimal, InvalidOperation

from .locate import (
    F_AMOUNT,
    F_COUNTERPARTY,
    F_DESCRIPTION,
    F_DIRECTION,
    F_TIME,
)

# 货币符号白名单（U+00A5 半角形 + U+FFE5 全角形 + 美元；plan/04 §二勘误）
_CURRENCY_CHARS = "¥￥$"
_THOUSANDS_SEP = ","

# 收支类型列取值白名单（微信/支付宝）
DIRECTION_EXPENSE = "支出"
DIRECTION_INCOME = "收入"
DIRECTION_NEUTRAL = "不计收支"

# IR 的 direction 值
DIR_EXPENSE = "expense"
DIR_INCOME = "income"
DIR_NEUTRAL = "neutral"

_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# 银行表头的固定列名（收支分列形态）
_BANK_EXPENSE_COL = "支出金额"
_BANK_INCOME_COL = "收入金额"
_BANK_TIME_COL = "交易时间"      # 时分秒列（表头名与微信同、语义不同）
_BANK_DATE_COL = "交易日期"


class ParsedRow(object):
    """单行解析产物（三态）。"""

    __slots__ = ("status", "code", "detail", "time", "amount", "direction",
                 "counterparty", "description", "raw_fields")

    def __init__(self, status, raw_fields, code=None, detail="", time=None,
                 amount=None, direction=None, counterparty=None, description=None):
        self.status = status          # ok | invalid | unknown
        self.code = code              # invalid/unknown 的错误码
        self.detail = detail
        self.time = time
        self.amount = amount          # Decimal（正数）或 None
        self.direction = direction    # expense/income/neutral 或 None
        self.counterparty = counterparty
        self.description = description
        self.raw_fields = raw_fields


def _parse_time(text):
    """固定格式严格解析；返回规范化字符串或 None（空/不可解析）。"""
    text = (text or "").strip()
    if not text:
        return None
    try:
        moment = datetime.datetime.strptime(text, _TIME_FORMAT)
    except ValueError:
        return None
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def _parse_amount_cell(text):
    """金额单元格 → Decimal（正数）或 None（空/非数值）。

    去千分位与货币符号后必须整体合法；残留非数值字符（如 "abc"）→ None。
    """
    text = (text or "").strip()
    if not text:
        return None
    cleaned = text
    for ch in _CURRENCY_CHARS:
        cleaned = cleaned.replace(ch, "")
    cleaned = cleaned.replace(_THOUSANDS_SEP, "").strip()
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    if not value.is_finite():
        return None
    return abs(value)


def _direction_from_text(text):
    """收支类型列取值 → IR direction；未登记取值返回 None（unknown 行）。"""
    text = (text or "").strip()
    if text == DIRECTION_EXPENSE:
        return DIR_EXPENSE
    if text == DIRECTION_INCOME:
        return DIR_INCOME
    if text == DIRECTION_NEUTRAL:
        return DIR_NEUTRAL
    return None


def _to_plain(value):
    """Decimal → 定点字符串（无科学计数法）。"""
    return format(value, "f")


def _cell(fields, idx):
    if idx is None or idx >= len(fields):
        return ""
    return fields[idx].strip()


def _zip_raw(header_fields, fields):
    """原始行字段（表头名 → 原值）；多余字段记 ``_extra:N``（列数不匹配可审计）。"""
    out = {}
    for idx, name in enumerate(header_fields):
        out[name] = fields[idx] if idx < len(fields) else None
    for i in range(len(header_fields), len(fields)):
        out["_extra:%d" % i] = fields[i]
    return out


def parse_row_wechat(fields, header_fields, field_map):
    """微信行：单金额列 + 收支类型列。"""
    return _parse_direction_column_row(fields, header_fields, field_map)


def parse_row_alipay(fields, header_fields, field_map):
    """支付宝行：单金额列 + 收支类型列（与微信同构）。"""
    return _parse_direction_column_row(fields, header_fields, field_map)


def _parse_direction_column_row(fields, header_fields, field_map):
    raw_fields = _zip_raw(header_fields, fields)
    if len(fields) != len(header_fields):
        return ParsedRow("invalid", raw_fields, code="column_count_mismatch",
                         detail="字段数 %d ≠ 表头列数 %d" % (len(fields), len(header_fields)))

    time_text = _parse_time(_cell(fields, field_map.get(F_TIME)))
    if time_text is None:
        return ParsedRow("invalid", raw_fields, code="time_unparseable",
                         detail="时间不可解析（须为 YYYY-MM-DD HH:MM:SS）")

    direction_text = _cell(fields, field_map.get(F_DIRECTION))
    direction = _direction_from_text(direction_text)
    if direction is None:
        # 未登记收支取值 → unknown 行（入库 + issues 显式列出）
        return ParsedRow(
            "unknown", raw_fields, code="unmapped_direction",
            detail="未登记的收/支取值：%s" % direction_text,
            time=time_text,
            amount=_parse_amount_cell(_cell(fields, field_map.get(F_AMOUNT))),
            counterparty=_cell(fields, field_map.get(F_COUNTERPARTY)),
            description=_cell(fields, field_map.get(F_DESCRIPTION)),
        )

    amount_cell = _cell(fields, field_map.get(F_AMOUNT))
    amount = _parse_amount_cell(amount_cell)
    if amount is None:
        # 空单元格与"非数值内容"是两个问题码（真值台账区分形态）
        code = "amount_missing" if not amount_cell.strip() else "amount_not_numeric"
        return ParsedRow("invalid", raw_fields, code=code,
                         detail="金额为空" if code == "amount_missing"
                         else "金额非数值：%s" % amount_cell)
    return ParsedRow("ok", raw_fields, time=time_text, amount=amount,
                     direction=direction,
                     counterparty=_cell(fields, field_map.get(F_COUNTERPARTY)),
                     description=_cell(fields, field_map.get(F_DESCRIPTION)))


def parse_row_bank(fields, header_fields, field_map):
    """银行行：收支分列（支出金额/收入金额）+ 日期与时分秒分列。"""
    raw_fields = _zip_raw(header_fields, fields)
    if len(fields) != len(header_fields):
        return ParsedRow("invalid", raw_fields, code="column_count_mismatch",
                         detail="字段数 %d ≠ 表头列数 %d" % (len(fields), len(header_fields)))

    # 银行的 field_map[F_TIME] 指向"交易日期"列；时分秒列按表头名定位
    date_idx = field_map.get(F_TIME)
    hms_idx = _index_of(header_fields, _BANK_TIME_COL)
    time_text = _parse_time("%s %s" % (_cell(fields, date_idx), _cell(fields, hms_idx)))
    if time_text is None:
        return ParsedRow("invalid", raw_fields, code="time_unparseable",
                         detail="时间不可解析（日期+时分秒拼接后须为 YYYY-MM-DD HH:MM:SS）")

    expense_idx = _index_of(header_fields, _BANK_EXPENSE_COL)
    income_idx = _index_of(header_fields, _BANK_INCOME_COL)
    expense_cell = _cell(fields, expense_idx)
    income_cell = _cell(fields, income_idx)
    expense = _parse_amount_cell(expense_cell)
    income = _parse_amount_cell(income_cell)
    if expense is not None and income is not None:
        return ParsedRow("invalid", raw_fields, code="amount_ambiguous",
                         detail="支出金额与收入金额同时非空")
    direction = None
    amount = None
    if expense is not None:
        direction, amount = DIR_EXPENSE, expense
    elif income is not None:
        direction, amount = DIR_INCOME, income
    else:
        # 空单元格与"非数值内容"是两个问题码（真值台账区分形态）
        non_empty = expense_cell.strip() or income_cell.strip()
        if non_empty:
            return ParsedRow("invalid", raw_fields, code="amount_not_numeric",
                             detail="金额非数值：%s" % non_empty)
        return ParsedRow("invalid", raw_fields, code="amount_missing",
                         detail="支出金额与收入金额均为空")
    return ParsedRow("ok", raw_fields, time=time_text, amount=amount,
                     direction=direction,
                     counterparty=_cell(fields, field_map.get(F_COUNTERPARTY)),
                     description=_cell(fields, field_map.get(F_DESCRIPTION)))


def _index_of(header_fields, name):
    for idx, cell in enumerate(header_fields):
        if cell.strip() == name:
            return idx
    return None

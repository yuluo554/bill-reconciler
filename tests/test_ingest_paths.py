"""ingest 失败路径与边界（M2）：文件级错误码、编码探测顺序、XLSX 覆盖度、金额/时间解析。

文件级失败（plan/03 §一 / HANDOFF-M2 待办 3）：坏编码 / 表头未定位 / 缺必填列 /
空文件 → 文件级问题、退出码 2 语义（CLI 侧在 test_import_cli.py 锁定）。
"""

import io
import zipfile

import pytest

from bill_reconciler.errors import InputError
from bill_reconciler.ingest.detect import ORDER_NOTE, decode_bytes, detect_encoding
from bill_reconciler.ingest.importer import import_files
from bill_reconciler.ingest.locate import (
    PLATFORM_EXPECTED_COLUMNS,
    build_column_map,
    locate_header,
)
from bill_reconciler.ingest.parsers import _parse_amount_cell, _parse_time
from bill_reconciler.ingest.xlsx_reader import XlsxFeatureError, read_xlsx
from bill_reconciler.datadir import require_data_dir


# 列别名夹具：与 data/rules/aliases.json 的 column_aliases 同构（测试自足，
# 不依赖规则包内容漂移；规则包同源性由冻结守门与 test_import.py 保障）
ALIASES = [
    {"canonical": "对手方", "variants": ["交易对象"], "platforms": ["alipay", "wechat", "bank"]},
    {"canonical": "金额", "variants": ["金额(元)", "金额（元）", "金额"], "platforms": ["alipay", "wechat", "bank"]},
]


def _tmp_file(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


# --- 编码探测（顺序写死 + 正/反向样例） --------------------------------------


def test_encoding_order_note_is_locked():
    assert ORDER_NOTE == "BOM → UTF-8 严格 → GB18030 → 失败报错"


def test_detect_bom_variants():
    import codecs

    assert detect_encoding(b"\xef\xbb\xbfhello") == "utf-8-sig"
    assert detect_encoding(codecs.BOM_UTF16_LE + "中文".encode("utf-16-le")) == "utf-16"
    assert detect_encoding(codecs.BOM_UTF16_BE + "中文".encode("utf-16-be")) == "utf-16"


def test_detect_utf8_before_gb18030():
    """反向样例：UTF-8 中文文本在 GB18030 下也常"能解"，必须先试 UTF-8。"""
    text = "交易时间\t交易对方\n2026-01-01 08:00:00\t示例便利店甲"
    data = text.encode("utf-8")
    encoding, decoded = decode_bytes(data)
    assert encoding == "utf-8"
    assert decoded == text  # 若误走 GB18030 会产出乱码


def test_detect_gb18030_fallback():
    text = "交易时间\t交易对方\n微信账单"
    data = text.encode("gb18030")
    encoding, decoded = decode_bytes(data)
    assert encoding == "gb18030"
    assert decoded == text


def test_detect_failure_raises():
    bad = b"WX-BILL-DEMO\n\xff\xff\xff\xff broken bytes \xff\xff\n"
    assert detect_encoding(bad) is None
    with pytest.raises(UnicodeDecodeError):
        decode_bytes(bad)


# --- 表头定位 / 列映射 --------------------------------------------------------


def test_locate_header_finds_amid_ad_lines():
    lines = [
        "微信支付账单明细",
        "导出时间：2026-10-01",
        "交易时间\t交易类型\t交易对方\t商品\t收/支\t金额(元)",
    ]
    idx, fields = locate_header(lines, "wechat", header_k=2, max_scan_lines=20)
    assert idx == 2
    assert fields[0] == "交易时间"


def test_locate_header_failure_lists_candidates():
    lines = ["说明一", "说明二", "说明三"]
    with pytest.raises(InputError) as exc_info:
        locate_header(lines, "wechat", header_k=2, max_scan_lines=20)
    assert "header" in str(exc_info.value) or "表头" in str(exc_info.value)


def test_locate_header_respects_scan_limit():
    lines = ["占位"] * 25 + ["交易时间\t交易对方\t金额(元)"]
    with pytest.raises(InputError):
        locate_header(lines, "wechat", header_k=2, max_scan_lines=20)


def test_column_map_synonym_and_space_variants():
    header = ["交易号 ", "交易创建时间 ", "交易对象", "商品说明", "金额(元) ", " 收/支", "交易状态", "商户编号"]
    field_map, unknown = build_column_map(header, "alipay", ALIASES)
    # 同义列名经别名表命中；空格变体经去空白命中
    assert field_map.get("对手方") == 2
    assert unknown == ["商户编号"]  # 未登记列显式报告


def test_required_column_missing(tmp_path):
    data = "交易日期\t摘要\t支出金额\n2026-08-01\t消费\t1.00\n".encode("utf-8")
    path = _tmp_file(tmp_path, "bank-x.csv", data)
    ledger = import_files([path], platform="bank", column_aliases=[])
    assert ledger["file_issues"][0]["code"] == "required_column_missing"


# --- 金额 / 时间解析单元 ------------------------------------------------------


def test_amount_parsing_forms():
    from decimal import Decimal

    assert _parse_amount_cell("1,234.56") == Decimal("1234.56")   # 千分位
    assert _parse_amount_cell("¥199.00") == Decimal("199.00")     # 半角货币符
    assert _parse_amount_cell("￥199.00") == Decimal("199.00")    # 全角货币符（GBK 通道）
    assert _parse_amount_cell("abc") is None                      # 非数值
    assert _parse_amount_cell("") is None                         # 空
    assert _parse_amount_cell("   ") is None


def test_time_parsing_strict():
    assert _parse_time("2026-08-12 08:10:00") == "2026-08-12 08:10:00"
    assert _parse_time("2026-08-13 25:61:00") is None             # 非法时刻
    assert _parse_time("") is None
    assert _parse_time("2026/08/12 08:10:00") is None             # 非约定格式


# --- XLSX 读取器（覆盖度声明：不支持特性 → 显式错误码，不猜测） ----------------


def _xlsx_of(rows, compress_type=zipfile.ZIP_STORED):
    """用与 _frozen_common 相同的结构打一个 XLSX（可注入变体）。"""
    from xml.sax.saxutils import escape

    sheet_cells = []
    for row_idx, row in enumerate(rows, start=1):
        cells = "".join(
            '<c t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % escape(v)
            for v in row
        )
        sheet_cells.append('<row r="%d">%s</row>' % (row_idx, cells))
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>%s</sheetData></worksheet>" % "".join(sheet_cells)
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in [
            ("[Content_Types].xml", content_types),
            ("_rels/.rels", rels),
            ("xl/workbook.xml", workbook),
            ("xl/_rels/workbook.xml.rels", workbook_rels),
            ("xl/worksheets/sheet1.xml", sheet_xml),
        ]:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = compress_type
            info.create_system = 0
            archive.writestr(info, text.encode("utf-8"))
    return buffer.getvalue()


def test_xlsx_reader_roundtrip():
    rows = [["交易时间", "金额"], ["2026-01-01 00:00:00", "1.00"]]
    table = read_xlsx(_xlsx_of(rows))
    assert table == rows


def test_xlsx_rejects_compression():
    with pytest.raises(XlsxFeatureError) as exc_info:
        read_xlsx(_xlsx_of([["a"]], compress_type=zipfile.ZIP_DEFLATED))
    assert exc_info.value.code == "xlsx_compression"


def test_xlsx_rejects_non_zip():
    with pytest.raises(XlsxFeatureError) as exc_info:
        read_xlsx(b"not a zip at all --------------------")
    assert exc_info.value.code == "xlsx_unreadable"


def test_xlsx_rejects_shared_strings():
    data = _xlsx_of([["a"]])
    buffer = io.BytesIO(data)
    with zipfile.ZipFile(buffer, "a") as archive:
        info = zipfile.ZipInfo("xl/sharedStrings.xml", date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, '<sst xmlns="x"></sst>')
    with pytest.raises(XlsxFeatureError) as exc_info:
        read_xlsx(buffer.getvalue())
    assert exc_info.value.code == "xlsx_shared_strings"


def test_xlsx_rejects_multi_sheet():
    data = _xlsx_of([["a"]])
    # 重写 workbook.xml 加入第二个 sheet
    src = io.BytesIO(data)
    out = io.BytesIO()
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(out, "w") as zout:
        for name in zin.namelist():
            content = zin.read(name)
            if name == "xl/workbook.xml":
                content = content.replace(
                    b"</sheets>",
                    b'<sheet name="sheet2" sheetId="2" r:id="rId2"/></sheets>',
                )
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 0
            zout.writestr(info, content)
    with pytest.raises(XlsxFeatureError) as exc_info:
        read_xlsx(out.getvalue())
    assert exc_info.value.code == "xlsx_multi_sheet"


def test_xlsx_unsupported_suffix_file_level(tmp_path):
    """不支持的扩展名 → 文件级 unsupported_format。"""
    path = _tmp_file(tmp_path, "wechat-demo.pdf", b"%PDF-1.4 fake")
    ledger = import_files([path], platform="wechat")
    assert ledger["file_issues"][0]["code"] == "unsupported_format"


# --- 文件级失败路径全谱（bad encoding / header / empty / missing col） ---------


@pytest.fixture(scope="module")
def rules_env(request):
    data_dir = require_data_dir()
    aliases_doc = json.loads(
        (data_dir / "rules" / "aliases.json").read_text(encoding="utf-8")
    )
    return {"data_dir": data_dir, "aliases": aliases_doc["column_aliases"]}


import json  # noqa: E402


def test_frozen_bad_encoding_sample_is_file_level_invalid(rules_env, tmp_path):
    """坏编码冻结样例 → encoding_undetermined（不猜测）。"""
    src = rules_env["data_dir"] / "samples" / "wechat-demo-bad-encoding.csv"
    ledger = import_files([str(src)], column_aliases=rules_env["aliases"])
    assert ledger["file_issues"][0]["code"] == "encoding_undetermined"


def test_empty_and_header_only_samples(rules_env):
    """空文件 → empty_file；仅表头（无数据行）→ 空数据不算失败、0 记录。"""
    data_dir = rules_env["data_dir"]
    ledger = import_files(
        [str(data_dir / "samples" / "alipay-demo-empty.csv")],
        column_aliases=rules_env["aliases"],
    )
    assert ledger["file_issues"][0]["code"] == "empty_file"
    ledger2 = import_files(
        [str(data_dir / "samples" / "alipay-demo-header-only.csv")],
        column_aliases=rules_env["aliases"],
    )
    assert not ledger2["file_issues"]
    assert ledger2["records"] == []

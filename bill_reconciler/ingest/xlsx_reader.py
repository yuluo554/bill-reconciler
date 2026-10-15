"""自写最小 XLSX 读取器（零第三方依赖）。

只承诺读取**本项目 ``tools/_frozen_common.xlsx_bytes`` 形态**的工作簿：
inlineStr 单元格、单 sheet、无共享字符串表。覆盖度声明（plan/03 §DoD）：

- 不支持共享字符串（sharedStrings.xml）→ ``xlsx_shared_strings``；
- 不支持数字/公式/样式单元格（``t`` 属性非 inlineStr 或缺失）→ ``xlsx_cell_type``；
- 不支持多 sheet（workbook 声明多个 sheet）→ ``xlsx_multi_sheet``；
- 压缩方式非 ZIP_STORED → ``xlsx_compression``；
- zip 损坏 / 非 zip → ``xlsx_unreadable``。

全部以 :class:`XlsxFeatureError`（带错误码）显式报错，**不猜测、不静默降级**。
"""

import io
import re
import zipfile
from xml.etree import ElementTree

from ..errors import InputError

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


class XlsxFeatureError(InputError):
    """XLSX 含本读取器不支持的特征（错误码显式，不猜测）。"""

    def __init__(self, code, detail):
        super().__init__("%s（%s）" % (code, detail))
        self.code = code


def _cell_text(cell):
    """取 inlineStr 单元格文本；非文本形态 → 显式错误。"""
    if cell.get("t") != "inlineStr":
        raise XlsxFeatureError(
            "xlsx_cell_type",
            "仅支持 inlineStr 单元格，遇到 t=%r" % cell.get("t"),
        )
    is_el = cell.find("%sis" % _NS)
    if is_el is None:
        raise XlsxFeatureError("xlsx_cell_type", "inlineStr 单元格缺少 <is> 节点")
    texts = [t.text or "" for t in is_el.findall("%st" % _NS)]
    return "".join(texts)


def read_xlsx(data):
    """读取 XLSX 字节 → 二维字符串表（首行表头行起，含全部行）。

    只支持本项目 writer 形态（ZIP_STORED / 单 sheet / inlineStr / 无 sharedStrings）；
    超出声明即抛 XlsxFeatureError。
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise XlsxFeatureError("xlsx_unreadable", "不是合法的 zip 容器")
    with archive:
        names = archive.namelist()
        if "xl/workbook.xml" not in names or "xl/worksheets/sheet1.xml" not in names:
            raise XlsxFeatureError(
                "xlsx_structure", "缺少 xl/workbook.xml 或 xl/worksheets/sheet1.xml"
            )
        for name in names:
            info = archive.getinfo(name)
            if info.compress_type != zipfile.ZIP_STORED:
                raise XlsxFeatureError(
                    "xlsx_compression", "条目 %s 使用了压缩（仅支持 ZIP_STORED 形态）" % name
                )
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        sheets = workbook.findall("%ssheets/%ssheet" % (_NS, _NS))
        if len(sheets) != 1:
            raise XlsxFeatureError(
                "xlsx_multi_sheet", "工作簿含 %d 个 sheet（仅支持单 sheet）" % len(sheets)
            )
        if "xl/sharedStrings.xml" in names:
            raise XlsxFeatureError(
                "xlsx_shared_strings", "存在共享字符串表（本读取器仅支持 inlineStr 形态）"
            )
        sheet = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))

    rows = []
    for row_el in sheet.findall("%ssheetData/%srow" % (_NS, _NS)):
        cells = []
        for cell in row_el.findall("%sc" % _NS):
            cells.append(_cell_text(cell))
        rows.append(cells)
    return rows

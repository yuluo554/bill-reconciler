"""tools 生成器公共件（仅标准库；不进包安装面）。

提供冻结产物的确定性基建：

- ``ensure_utf8_stdio()``：编码守卫（与 ``bill_reconciler.cli`` 同款，K4）；
- ``SplitMix64``：自研确定性 RNG（**禁 stdlib random / set 迭代序 / 系统时钟**）；
- ``dumps_json_bytes()``：规范化 JSON 字节（ensure_ascii=False + 固定缩进 + LF）；
- ``xlsx_bytes()``：自写最小 XLSX writer（``ZIP_STORED`` + ``create_system=0`` +
  固定 ``date_time`` + 条目固定顺序 → **任意平台重生成位级一致**）；
- ``sha256_hex()`` / ``compare_outputs()``：冻结比对（--check 用）。
"""

import hashlib
import io
import json
import sys
import zipfile

_MASK64 = (1 << 64) - 1

# XLSX zip 条目的固定元数据：date_time 固定常量、create_system=0（跨平台一致）
_FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)
_FIXED_EXTERNAL_ATTR = 0o600 << 16


def ensure_utf8_stdio():
    """编码守卫（K4）：非 UTF-8、非中文控制台的流切到 UTF-8。

    中文控制台（cp936 系）保持不动；其余流（如 CI 上的 cp1252）改为 UTF-8。
    每个 ``tools/`` 脚本入口最先执行。
    """
    leave = (
        "utf8",
        "cp936",
        "gbk",
        "gb2312",
        "gb18030",
        "big5",
        "cp950",
        "cp65001",
        "utf16",
        "utf16le",
        "utf16be",
    )
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if not encoding or encoding in leave:
            continue
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError, ValueError):
            pass


class SplitMix64:
    """splitmix64：自研确定性 PRNG（固定 seed → 固定序列，跨解释器一致）。"""

    def __init__(self, seed):
        self.state = seed & _MASK64

    def next_u64(self):
        self.state = (self.state + 0x9E3779B97F4A7C15) & _MASK64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK64
        return z ^ (z >> 31)

    def below(self, n):
        """返回 [0, n) 的确定性取值（``n`` 必须为正整数）。"""
        if n <= 0:
            raise ValueError("n 必须为正整数")
        return self.next_u64() % n


def dumps_json_bytes(obj):
    """规范化 JSON 字节：无 BOM、LF 结尾、ensure_ascii=False、固定 2 空格缩进。

    键序由构造顺序固定（调用方不得依赖动态键排序）。
    """
    text = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False)
    return (text + "\n").encode("utf-8")


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def _xml_escape(text):
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def xlsx_bytes(rows):
    """最小确定性 XLSX：``rows`` 为字符串二维表；全部单元格按 inlineStr 写入。

    位级一致的关键：``ZIP_STORED``（不压缩）+ 条目固定顺序 +
    固定 ``date_time`` + ``create_system=0`` + 固定 external_attr。
    """
    sheet_cells = []
    for row_idx, row in enumerate(rows, start=1):
        cells = []
        for value in row:
            cells.append(
                '<c t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
                % _xml_escape(value)
            )
        sheet_cells.append('<row r="%d">%s</row>' % (row_idx, "".join(cells)))
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

    parts = [
        ("[Content_Types].xml", content_types),
        ("_rels/.rels", rels),
        ("xl/workbook.xml", workbook),
        ("xl/_rels/workbook.xml.rels", workbook_rels),
        ("xl/worksheets/sheet1.xml", sheet_xml),
    ]

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in parts:
            info = zipfile.ZipInfo(name, date_time=_FIXED_DATE_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 0
            info.external_attr = _FIXED_EXTERNAL_ATTR
            archive.writestr(info, text.encode("utf-8"))
    return buffer.getvalue()


def compare_outputs(root, outputs):
    """比对 ``{相对路径: 期望字节}`` 与 ``root`` 下入库件；返回差异清单。

    差异形如 ``["data/rules/manifest.json: missing", "data/samples/x.csv: byte-diff"]``。
    """
    diffs = []
    for rel, expected in sorted(outputs.items()):
        path = root / rel
        if not path.is_file():
            diffs.append("%s: missing" % rel)
            continue
        actual = path.read_bytes()
        if actual != expected:
            diffs.append(
                "%s: byte-diff (disk sha256=%s, regen sha256=%s)"
                % (rel, sha256_hex(actual)[:16], sha256_hex(expected)[:16])
            )
    return diffs


def write_outputs(root, outputs):
    """把 ``{相对路径: 字节}`` 写入 ``root``（父目录自动创建）。"""
    for rel, data in sorted(outputs.items()):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

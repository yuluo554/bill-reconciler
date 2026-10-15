"""编码探测：顺序写死（plan/03 §1.1），测试锁定。

1. BOM 探测（utf-8-sig / utf-16 LE·BE）→ 命中即用；
2. UTF-8 严格解码（含纯 ASCII）；
3. GB18030 解码尝试（GBK 超集）；
4. 全部失败 → ``encoding_undetermined``（文件级失败，不猜测）。

第 2 步必须先于第 3 步：UTF-8 中文文本在 GB18030 下几乎总能"解码成功"
（产出一堆乱码），顺序反了会把正常 UTF-8 文件译成乱码且不报错。
"""

BOM_UTF8 = b"\xef\xbb\xbf"
BOM_UTF16_LE = b"\xff\xfe"
BOM_UTF16_BE = b"\xfe\xff"

# 探测顺序的显式白名单（文档化 + 测试锁定）
ORDER_NOTE = "BOM → UTF-8 严格 → GB18030 → 失败报错"


def detect_encoding(data):
    """返回 (编码名, 解码函数) 或 None（全部失败）。

    编码名用于 meta.sources[].encoding（显式记录实际采用的解码通道）。
    """
    if data.startswith(BOM_UTF8):
        return "utf-8-sig"
    if data.startswith(BOM_UTF16_LE) or data.startswith(BOM_UTF16_BE):
        return "utf-16"
    try:
        data.decode("utf-8", "strict")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        data.decode("gb18030", "strict")
        return "gb18030"
    except UnicodeDecodeError:
        pass
    return None


def decode_bytes(data):
    """按写死顺序解码；失败抛 ``UnicodeDecodeError``（调用方转为文件级问题）。

    返回 (encoding, text)。
    """
    encoding = detect_encoding(data)
    if encoding is None:
        raise UnicodeDecodeError(
            "brc-ingest", data, 0, len(data), "编码探测失败（BOM/UTF-8/GB18030 均不可解）"
        )
    return encoding, data.decode(encoding, "strict")

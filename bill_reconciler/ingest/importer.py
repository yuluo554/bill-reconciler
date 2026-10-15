"""import 编排：文件 → IR（ledger）+ 问题清单（plan/03 §〇 / §一）。

流程（每文件独立，一个文件失败不影响其余文件）：

1. 读字节 → 按扩展名分流：XLSX 先结构解析（xlsx_reader，覆盖度外特征显式报错），
   文本格式再编码探测（detect.decode_bytes；失败 → 文件级 ``encoding_undetermined``）；
2. 表头定位（locate.locate_header；失败 → ``header_not_found``）；
3. 列映射（locate.build_column_map；必填缺失 → ``required_column_missing``；
   未登记列 → unknown_column issues，不拒行）;
4. 逐行解析（parsers，平台分发）→ records / issues；
5. meta.sources 记审计凭证（sha256、bytes、encoding、行计数）。

退出码语义（M2 锁定）：任一文件级失败 → 2；仅行级问题 → 1；全部干净 → 0。
``unknown`` 行/列入 issues 不拒行；行级问题清单全量打印（不截断）。
"""

import hashlib
from pathlib import Path

from .detect import decode_bytes
from .locate import (
    HeaderError,
    RequiredColumnError,
    build_column_map,
    locate_header,
    require_fields,
)
from .parsers import (
    _to_plain,
    parse_row_alipay,
    parse_row_bank,
    parse_row_wechat,
)
from .xlsx_reader import XlsxFeatureError, read_xlsx
from ..errors import InputError

SCHEMA_VERSION = 1

# 平台名 → 行解析器（平台识别：显式 --platform 优先，缺省按文件名前缀——不猜测）
PARSERS = {
    "wechat": parse_row_wechat,
    "alipay": parse_row_alipay,
    "bank": parse_row_bank,
}

KNOWN_PLATFORMS = tuple(sorted(PARSERS))

# 支持的扩展名（其余 → 文件级 unsupported_format）
SUPPORTED_SUFFIXES = (".csv", ".tsv", ".xlsx")


class UnknownPlatformError(InputError):
    """未知平台（--platform 取值不在白名单）。"""


def _detect_platform(path, explicit_platform):
    """平台来源：显式指定优先；否则按文件名前缀（wechat-/alipay-/bank-，
    与冻结样例命名一致）；对不上 → 文件级 unknown_platform（不猜测）。
    """
    if explicit_platform:
        return explicit_platform
    name = Path(path).name.lower()
    for platform in KNOWN_PLATFORMS:
        if name.startswith(platform + "-") or name.startswith(platform + "_"):
            return platform
    raise InputError(
        "%s：无法识别平台（文件名需以 %s- 前缀开头，或用 --platform 显式指定）"
        % (Path(path).name, "/".join(KNOWN_PLATFORMS))
    )


def _split_lines(text):
    """按行拆分（容忍 \\r\\n 与结尾空行）。"""
    return [line for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]


def import_one_file(path, platform, column_aliases, header_k, max_scan_lines):
    """导入单文件 → (source_meta, records, issues, column_issues)。

    文件级失败抛 InputError 子类（调用方收集为 file_issues）。
    行物理行号 1-based（含表头与广告行），与真值 ``文件名#行号`` 口径一致。
    """
    data = Path(path).read_bytes()
    source_name = Path(path).name
    suffix = Path(path).suffix.lower()

    if suffix == ".xlsx":
        # XLSX 是 zip 容器（几乎必然过不了文本编码探测）：先结构解析再定 "xlsx" 通道
        try:
            table = read_xlsx(data)
        except XlsxFeatureError as exc:
            raise InputError("%s：%s" % (source_name, exc))
        encoding = "xlsx"
        lines = ["\t".join(row) for row in table]
    else:
        try:
            encoding, text = decode_bytes(data)
        except UnicodeDecodeError:
            raise InputError("%s：编码探测失败（BOM/UTF-8/GB18030 均不可解，不猜测）" % source_name)
        if suffix in (".csv", ".tsv"):
            lines = _split_lines(text)
            # 去掉结尾因换行产生的空行（中间空行保留——行号口径可见）
            while lines and lines[-1] == "":
                lines.pop()
        else:
            raise InputError(
                "%s：不支持的格式 %s（支持：%s）"
                % (source_name, suffix, "/".join(SUPPORTED_SUFFIXES))
            )

    if not lines:
        raise InputError("%s：空文件（无任何内容）" % source_name)

    try:
        header_idx, header_fields = locate_header(lines, platform, header_k, max_scan_lines)
    except HeaderError as exc:
        raise InputError("%s：%s" % (source_name, exc))

    field_map, unknown_columns = build_column_map(header_fields, platform, column_aliases)
    try:
        require_fields(field_map, source_name)
    except RequiredColumnError as exc:
        raise InputError("%s：%s" % (source_name, exc))

    parser = PARSERS[platform]
    records = []
    issues = []
    rows_ok = rows_invalid = rows_unknown = 0

    # column_issues：未登记列名（unknown_column；每列一条，不逐行重复）
    column_issues = [
        {"kind": "unknown", "code": "unknown_column", "column": name}
        for name in unknown_columns
    ]

    for offset, line in enumerate(lines[header_idx + 1:], start=header_idx + 2):
        lineno = offset  # 物理行号（1-based）
        if line == "":
            # 中间空行：跳过但保留行号口径（不入 issues——空行不是"行级问题"）
            continue
        fields = line.split("\t")
        parsed = parser(fields, header_fields, field_map)
        row_id = "%s#%d" % (source_name, lineno)
        if parsed.status == "invalid":
            rows_invalid += 1
            issues.append({
                "source_file": source_name,
                "row_id": row_id,
                "kind": "invalid",
                "code": parsed.code,
                "detail": parsed.detail,
            })
            continue
        # ok / unknown 都入库
        if parsed.status == "unknown":
            rows_unknown += 1
            issues.append({
                "source_file": source_name,
                "row_id": row_id,
                "kind": "unknown",
                "code": parsed.code,
                "detail": parsed.detail,
            })
        else:
            rows_ok += 1
        records.append({
            "id": row_id,
            "source_platform": platform,
            "source_file": source_name,
            "source_row": lineno,
            "time": parsed.time,
            "amount": _to_plain(parsed.amount) if parsed.amount is not None else None,
            "direction": parsed.direction,
            "counterparty": parsed.counterparty,
            "description": parsed.description,
            "raw_fields": parsed.raw_fields,
            "row_status": parsed.status,
        })

    source_meta = {
        "file": source_name,
        "platform": platform,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "encoding": encoding,
        "header_skipped_lines": header_idx,
        "rows_total": rows_ok + rows_invalid + rows_unknown,
        "rows_ok": rows_ok,
        "rows_invalid": rows_invalid,
        "rows_unknown": rows_unknown,
    }
    return source_meta, records, issues, column_issues


def import_files(paths, platform=None, column_aliases=None, header_k=2, max_scan_lines=20):
    """导入多文件 → ledger dict（IR）。

    退出码语义由调用方据 ``file_issues/issues`` 判定：
    任一 file_issue → 2；仅行级 issues → 1；全干净 → 0。
    """
    if platform is not None and platform not in KNOWN_PLATFORMS:
        raise UnknownPlatformError(
            "未知平台 %r（可用：%s）" % (platform, "/".join(KNOWN_PLATFORMS))
        )
    column_aliases = column_aliases or []

    meta_sources = []
    all_records = []
    all_issues = []
    all_file_issues = []

    for path in paths:
        try:
            detected = _detect_platform(path, platform)
            source_meta, records, issues, column_issues = import_one_file(
                path, detected, column_aliases, header_k, max_scan_lines
            )
        except InputError as exc:
            detail = str(exc)
            code = getattr(exc, "code", None) or _file_code_from_detail(detail)
            all_file_issues.append({"file": Path(path).name, "code": code, "detail": detail})
            continue
        meta_sources.append(source_meta)
        all_records.extend(records)
        all_issues.extend(issues)
        for ci in column_issues:
            all_issues.append({
                "source_file": source_meta["file"],
                "row_id": None,
                "kind": "unknown",
                "code": ci["code"],
                "column": ci["column"],
                "detail": "未登记列名：%s（该列不入规范字段，原值保留在 raw_fields）" % ci["column"],
            })

    # 排序确定性：records 按 (source_file, source_row)；issues 按 (file, row, code)
    all_records.sort(key=lambda r: (r["source_file"], r["source_row"]))
    all_issues.sort(key=lambda i: (i["source_file"], str(i["row_id"]), i["code"],
                                   i.get("column") or "", i["detail"]))

    ledger = {
        "schema_version": SCHEMA_VERSION,
        "meta": {
            "sources": meta_sources,
        },
        "records": all_records,
        "issues": all_issues,
        "file_issues": all_file_issues,
    }
    return ledger


def _file_code_from_detail(detail):
    """从异常文本反提错误码（InputError 无结构化 code 时的兜底；
    错误码清单与测试锁定的一致，新增码必须先加到这里）。
    """
    text = str(detail)
    if "编码探测失败" in text:
        return "encoding_undetermined"
    if "表头定位失败" in text:
        return "header_not_found"
    if "必填列缺失" in text:
        return "required_column_missing"
    if "空文件" in text:
        return "empty_file"
    if "不支持的格式" in text:
        return "unsupported_format"
    if "无法识别平台" in text:
        return "unknown_platform"
    if "xlsx_" in text:
        for marker in ("xlsx_shared_strings", "xlsx_cell_type", "xlsx_multi_sheet",
                       "xlsx_compression", "xlsx_unreadable", "xlsx_structure"):
            if marker in text:
                return marker
    return "file_invalid"

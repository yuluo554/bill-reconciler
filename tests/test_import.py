"""模块① ingest：三态矩阵回归（M2）。

逐样例对真值 ``expect_import``（唯一期望来源，K9）：file_status / file_issue_codes /
column_issues / 逐行三态全部对齐；另测确定性（同输入两次运行结果一致）。

行级三态语义（plan/03 §1.4）：
- ok：入库（records）；
- invalid：不入库（issues，kind=invalid）；
- unknown：入库且 issues 显式列出（kind=unknown）——"未知"是可用的行。
"""

import json
from pathlib import Path

import pytest

from bill_reconciler.datadir import require_data_dir
from bill_reconciler.ingest.importer import import_files


@pytest.fixture(scope="module")
def rules_env():
    data_dir = require_data_dir()
    aliases_doc = json.loads(
        (data_dir / "rules" / "aliases.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (data_dir / "rules" / "manifest.json").read_text(encoding="utf-8")
    )
    params = {p["id"]: p["value"] for p in manifest["params"]}
    return {
        "data_dir": data_dir,
        "aliases": aliases_doc["column_aliases"],
        "header_k": params["header_locate_k"],
        "max_scan": params["header_locate_max_scan_lines"],
        "truth": json.loads(
            (data_dir / "truth" / "truth.json").read_text(encoding="utf-8")
        ),
    }


def _import_all(rules_env):
    samples = sorted(
        str(p) for p in (rules_env["data_dir"] / "samples").iterdir() if p.is_file()
    )
    return import_files(
        samples,
        column_aliases=rules_env["aliases"],
        header_k=rules_env["header_k"],
        max_scan_lines=rules_env["max_scan"],
    )


def test_file_level_results_match_truth(rules_env):
    """文件级：ok / invalid 与 file_issue_codes 逐文件对齐 expect_import。"""
    ledger = _import_all(rules_env)
    got_by_file = {}
    for fi in ledger["file_issues"]:
        got_by_file.setdefault(fi["file"], []).append(fi["code"])
    for rel, expect in rules_env["truth"]["expect_import"].items():
        name = rel.split("/")[-1]
        got = sorted(got_by_file.get(name, []))
        assert got == sorted(expect["file_issue_codes"]), (
            "%s：文件级结果 %s ≠ 期望 %s" % (name, got, expect["file_issue_codes"])
        )


def test_row_three_state_matrix_matches_truth(rules_env):
    """行级三态：逐行对齐 expect_import.rows（真值含 4 个文件级样例 +
    7 个行级 invalid + 1 个 unknown 行 + 1 个 unknown 列的期望全集）。"""
    ledger = _import_all(rules_env)
    got_rows = {}
    for r in ledger["records"]:
        got_rows.setdefault(r["source_file"], {})[r["source_row"]] = r["row_status"]
    for issue in ledger["issues"]:
        if issue.get("row_id"):
            f, row = issue["row_id"].rsplit("#", 1)
            got_rows.setdefault(f, {})[int(row)] = issue["kind"]

    checked = 0
    for rel, expect in rules_env["truth"]["expect_import"].items():
        name = rel.split("/")[-1]
        got = got_rows.get(name, {})
        for row_id, row_expect in expect["rows"].items():
            lineno = int(row_id.rsplit("#", 1)[1])
            assert got.get(lineno) == row_expect["status"], (
                "%s：期望 %s（%s），实测 %s"
                % (row_id, row_expect["status"], row_expect.get("code"), got.get(lineno))
            )
            checked += 1
    assert checked == 77  # 真值期望行数（77 行逐条对齐；防真值/样例脱钩后此测试空转）


def test_unknown_column_issue_matches_truth(rules_env):
    """unknown 列：alipay-demo-02 的"商户编号"入 issues 不拒行（kind=unknown）。"""
    ledger = _import_all(rules_env)
    got = {}
    for issue in ledger["issues"]:
        if issue.get("column"):
            got.setdefault(issue["source_file"], set()).add(issue["column"])
    for rel, expect in rules_env["truth"]["expect_import"].items():
        name = rel.split("/")[-1]
        exp = {c["column"] for c in expect["column_issues"]}
        assert got.get(name, set()) == exp, "%s：unknown 列 %s ≠ %s" % (name, got.get(name), exp)


def test_unknown_row_stays_in_records(rules_env):
    """unknown 行入库（row_status=unknown）且 issues 显式列出——绝不静默。"""
    ledger = _import_all(rules_env)
    unknown_records = [r for r in ledger["records"] if r["row_status"] == "unknown"]
    assert len(unknown_records) == 1  # alipay-demo-02#8（收/支="其他"）
    rec = unknown_records[0]
    assert rec["id"] == "alipay-demo-02.csv#8"
    unknown_issues = [i for i in ledger["issues"]
                      if i["kind"] == "unknown" and i.get("row_id")]
    assert any(i["row_id"] == "alipay-demo-02.csv#8" for i in unknown_issues)


def test_invalid_rows_not_in_records(rules_env):
    """invalid 行绝不入库（宁可少一行，不可把错位的值当对的）。"""
    ledger = _import_all(rules_env)
    invalid_ids = {i["row_id"] for i in ledger["issues"] if i["kind"] == "invalid"}
    record_ids = {r["id"] for r in ledger["records"]}
    assert not (invalid_ids & record_ids)


def test_issue_codes_match_truth_shape(rules_env):
    """行级问题码与真值期望的 code 字段一致（amount_missing /
    amount_not_numeric / time_unparseable / column_count_mismatch /
    unmapped_direction）。"""
    ledger = _import_all(rules_env)
    got = {}
    for issue in ledger["issues"]:
        if issue.get("row_id") and issue["kind"] == "invalid":
            got[issue["row_id"]] = issue["code"]
    for rel, expect in rules_env["truth"]["expect_import"].items():
        name = rel.split("/")[-1]
        for row_id, row_expect in expect["rows"].items():
            if row_expect["status"] == "invalid":
                assert got.get(row_id) == row_expect["code"], (
                    "%s：问题码 %s ≠ %s" % (row_id, got.get(row_id), row_expect["code"])
                )


def test_import_is_deterministic(rules_env):
    """同输入两次运行：records/issues/file_issues 全量相等（输出排序固定）。"""
    first = _import_all(rules_env)
    second = _import_all(rules_env)
    assert first == second


def test_import_per_file_isolation(rules_env):
    """单文件导入与全量导入中该文件的结果一致（一个文件失败不影响其余）。"""
    ledger_all = _import_all(rules_env)
    data_dir = rules_env["data_dir"]
    one = import_files(
        [str(data_dir / "samples" / "wechat-demo-02.csv")],
        column_aliases=rules_env["aliases"],
        header_k=rules_env["header_k"],
        max_scan_lines=rules_env["max_scan"],
    )
    rows_all = sorted(
        (r["id"], r["row_status"]) for r in ledger_all["records"]
        if r["source_file"] == "wechat-demo-02.csv"
    )
    rows_one = sorted((r["id"], r["row_status"]) for r in one["records"])
    assert rows_all == rows_one


def test_records_carry_audit_fields(rules_env):
    """审计字段齐备：id 稳定口径 / raw_fields 原样 / amount 为正数字符串。"""
    ledger = _import_all(rules_env)
    for r in ledger["records"][:50]:
        assert r["id"] == "%s#%d" % (r["source_file"], r["source_row"])
        assert r["raw_fields"]  # 原始行终身保留
        if r["row_status"] == "ok":
            from decimal import Decimal

            value = Decimal(r["amount"])
            assert value > 0
            assert r["direction"] in ("expense", "income", "neutral")


def test_source_meta_audit_trail(rules_env):
    """meta.sources：sha256 / bytes / encoding / 行计数齐备（审计凭证）。"""
    ledger = _import_all(rules_env)
    import hashlib

    for s in ledger["meta"]["sources"]:
        raw = (rules_env["data_dir"] / "samples" / s["file"]).read_bytes()
        assert s["sha256"] == hashlib.sha256(raw).hexdigest()
        assert s["bytes"] == len(raw)
        assert s["encoding"]
        assert s["rows_total"] == s["rows_ok"] + s["rows_invalid"] + s["rows_unknown"]


def test_platform_prefix_detection_and_explicit_override(rules_env, tmp_path):
    """平台识别：文件名前缀；--platform 覆盖（未知平台 → 文件级失败）。"""
    data_dir = rules_env["data_dir"]
    src = data_dir / "samples" / "wechat-demo-01.csv"
    # 前缀不可识别 → 文件级 unknown_platform
    renamed = tmp_path / "mystery-bill.csv"
    renamed.write_bytes(src.read_bytes())
    ledger = import_files([str(renamed)], column_aliases=rules_env["aliases"])
    assert ledger["file_issues"][0]["code"] == "unknown_platform"
    # 显式指定 → 可导入
    ledger2 = import_files(
        [str(renamed)], platform="wechat", column_aliases=rules_env["aliases"],
        header_k=rules_env["header_k"], max_scan_lines=rules_env["max_scan"],
    )
    assert not ledger2["file_issues"]
    # 未知平台名 → 异常
    from bill_reconciler.errors import InputError

    with pytest.raises(InputError):
        import_files([str(src)], platform="paypal")


def test_wechat_xlsx_rows_match_truth(rules_env):
    """XLSX 通路：wechat-demo-03 / bank-demo-03 逐行三态与真值一致（读取器回归）。"""
    ledger = _import_all(rules_env)
    got = {}
    for r in ledger["records"]:
        got.setdefault(r["source_file"], {})[r["source_row"]] = r["row_status"]
    for name in ("wechat-demo-03.xlsx", "bank-demo-03.xlsx"):
        expect = rules_env["truth"]["expect_import"]["data/samples/%s" % name]
        for row_id, row_expect in expect["rows"].items():
            lineno = int(row_id.rsplit("#", 1)[1])
            assert got[name].get(lineno) == row_expect["status"], row_id

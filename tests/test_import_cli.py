"""import 子命令 CLI 契约（M2）：退出码 0/1/2 语义锁定 + 输出面。

- 全部干净 → 0；仅行级问题 → 1（清单打印到 stderr，全量不截断）；
- 任一文件级失败 → 2；缺文件/未知平台 → 2；
- ledger.json 落盘且可回读（IR schema 口径）。
"""

import json

from bill_reconciler.cli import main

SAMPLES = "data/samples"


def _out(tmp_path):
    return str(tmp_path / "ledger.json")


def test_import_clean_files_exit_0(tmp_path, capsys):
    out = _out(tmp_path)
    code = main(["import", "%s/wechat-demo-01.csv" % SAMPLES, "--out", out])
    assert code == 0
    ledger = json.loads(open(out, encoding="utf-8").read())
    assert ledger["schema_version"] == 1
    assert len(ledger["records"]) == 21
    assert ledger["issues"] == []
    assert ledger["file_issues"] == []
    captured = capsys.readouterr()
    assert "已导入" in captured.out


def test_import_row_issues_exit_1(tmp_path, capsys):
    out = _out(tmp_path)
    code = main(["import", "%s/wechat-demo-02.csv" % SAMPLES, "--out", out])
    captured = capsys.readouterr()  # 一次接住，再分别断言
    assert code == 1
    assert "行级问题" in captured.err  # 清单必打印（不静默）
    ledger = json.loads(open(out, encoding="utf-8").read())
    assert len(ledger["issues"]) == 3
    # 不入 records 的 invalid 行不在清单里被截断（3 条全打）
    assert captured.err.count("行级问题") == 3


def test_import_file_failure_exit_2(tmp_path, capsys):
    out = _out(tmp_path)
    code = main(["import", "%s/wechat-demo-bad-encoding.csv" % SAMPLES, "--out", out])
    captured = capsys.readouterr()
    assert code == 2
    assert "文件级失败" in captured.err
    ledger = json.loads(open(out, encoding="utf-8").read())
    assert ledger["file_issues"][0]["code"] == "encoding_undetermined"


def test_import_mixed_files_exit_2_wins(tmp_path, capsys):
    """混合输入：任一文件级失败 → 2（其余文件照常导入，失败不掩盖）。"""
    out = _out(tmp_path)
    code = main([
        "import",
        "%s/wechat-demo-01.csv" % SAMPLES,
        "%s/wechat-demo-bad-encoding.csv" % SAMPLES,
        "--out", out,
    ])
    assert code == 2
    ledger = json.loads(open(out, encoding="utf-8").read())
    assert len(ledger["records"]) == 21  # 干净文件照常入库
    assert len(ledger["file_issues"]) == 1


def test_import_missing_file_exit_2(tmp_path):
    code = main(["import", "%s/no-such-file.csv" % SAMPLES, "--out", _out(tmp_path)])
    assert code == 2


def test_import_unknown_platform_flag_exit_2(tmp_path):
    code = main([
        "import", "%s/wechat-demo-01.csv" % SAMPLES,
        "--platform", "paypal", "--out", _out(tmp_path),
    ])
    assert code == 2


def test_import_full_sample_matrix_ledger(tmp_path):
    """全 12 件冻结样例一次导入：与真值 expect_import 全对齐（CLI 通路）。"""
    from bill_reconciler.datadir import require_data_dir

    truth = json.loads(
        (require_data_dir() / "truth" / "truth.json").read_text(encoding="utf-8")
    )
    out = _out(tmp_path)
    files = ["%s/%s" % (SAMPLES, name) for name in
             sorted(p.name for p in require_data_dir().joinpath("samples").iterdir())]
    code = main(["import"] + files + ["--out", out])
    ledger = json.loads(open(out, encoding="utf-8").read())

    # 3 个文件级 invalid 样例（empty/missing-col/bad-encoding）按契约 → exit 2；
    # 其余 9 件全部可导入且与真值一致（预期内失败也是失败，不静默放行）
    assert code == 2
    assert len(ledger["file_issues"]) == 3

    got_rows = {}
    for r in ledger["records"]:
        got_rows.setdefault(r["source_file"], {})[r["source_row"]] = r["row_status"]
    for issue in ledger["issues"]:
        if issue.get("row_id"):
            f, row = issue["row_id"].rsplit("#", 1)
            got_rows.setdefault(f, {})[int(row)] = issue["kind"]
    for rel, expect in truth["expect_import"].items():
        name = rel.split("/")[-1]
        got = got_rows.get(name, {})
        for row_id, row_expect in expect["rows"].items():
            lineno = int(row_id.rsplit("#", 1)[1])
            assert got.get(lineno) == row_expect["status"], row_id

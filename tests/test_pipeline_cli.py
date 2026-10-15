"""M3 编排与 CLI 契约（pipeline + run/normalize/dedup/classify 子命令）。

退出码契约与 import 同语义（plan/02 §4.5）：文件级 2 / 行级 1 / 干净 0；
分段单命令与 run 共用同一实现（pipeline.py），不做两份口径。
"""

import json
from pathlib import Path

import pytest

from bill_reconciler.cli import main
from bill_reconciler.datadir import require_data_dir
from bill_reconciler.params import load_rules_package
from bill_reconciler.pipeline import run_pipeline


@pytest.fixture(scope="module")
def package():
    return load_rules_package(require_data_dir())


def _sample(name):
    return str(require_data_dir() / "samples" / name)


CLEAN_FILES = [
    "wechat-demo-01.csv", "alipay-demo-01.csv", "bank-demo-01.csv",
    "wechat-demo-03.xlsx", "bank-demo-03.xlsx",
]


def test_pipeline_clean_run(package):
    ledger, kind = run_pipeline([_sample(n) for n in CLEAN_FILES])
    assert kind == "issues"  # bank-demo-01 含 4 个行级 invalid
    assert ledger["meta"]["params_digest"]
    assert ledger["meta"]["ruleset_version"] == package.ruleset_version
    assert ledger["meta"]["pipeline"]["stages"] == [
        "import", "normalize", "dedup", "classify"]
    # 每条 record 三段标记齐备（只增不改：原字段仍在）
    for record in ledger["records"]:
        assert "normalized_counterparty" in record
        assert "dedup_cluster" in record or record.get("direction") is None \
            or record.get("amount") is None or "dedup_verdict" not in record
        assert "semantic_label" in record
    # 真值锚点（M2 已对齐的簇与标签在分段测试里锁，这里只锁段间衔接）
    assert ledger["dedup"]["clusters"]
    assert ledger["classify"]["distribution"]


def test_pipeline_deterministic(package):
    files = [_sample(n) for n in CLEAN_FILES]
    a, _ = run_pipeline(files)
    b, _ = run_pipeline(files)
    assert json.dumps(a, sort_keys=True, ensure_ascii=False) == \
        json.dumps(b, sort_keys=True, ensure_ascii=False)


def test_pipeline_writes_out_and_exit_kind(tmp_path):
    out = tmp_path / "ledger-full.json"
    _, kind = run_pipeline([_sample("wechat-demo-bad-encoding.csv")], out_path=out)
    assert kind == "usage"
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["file_issues"]


def test_run_cli_exit_codes(run_cli, tmp_path):
    out = tmp_path / "lf.json"
    clean = run_cli("run", _sample("wechat-demo-01.csv"),
                    "--out", str(out))
    assert clean.returncode == 0
    assert "语义分布" in clean.stdout
    bad = run_cli("run", _sample("wechat-demo-bad-encoding.csv"),
                  "--out", str(tmp_path / "lf2.json"))
    assert bad.returncode == 2
    row_level = run_cli("run", _sample("bank-demo-01.csv"),
                        "--out", str(tmp_path / "lf3.json"))
    assert row_level.returncode == 1


def test_run_cli_window_override_recorded(run_cli, tmp_path):
    out = tmp_path / "lf.json"
    result = run_cli("run", _sample("wechat-demo-01.csv"), "--out", str(out))
    assert result.returncode == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["dedup"]["params"]["window_seconds"] == 120
    out2 = tmp_path / "lf-w0.json"
    result2 = run_cli("run", _sample("wechat-demo-01.csv"),
                      "--window-seconds", "0", "--out", str(out2))
    assert result2.returncode == 0
    payload2 = json.loads(out2.read_text(encoding="utf-8"))
    assert payload2["dedup"]["params"]["window_seconds"] == 0


def test_stage_commands_chain(tmp_path, package):
    """normalize → dedup → classify 三段单命令链（与 run 同一实现）。"""
    out_n = tmp_path / "n.json"
    assert main(["normalize", "--from-files", _sample("wechat-demo-01.csv"),
                 "--out", str(out_n)]) == 0
    out_d = tmp_path / "d.json"
    assert main(["dedup", "--ledger", str(out_n), "--out", str(out_d)]) == 0
    out_c = tmp_path / "c.json"
    assert main(["classify", "--ledger", str(out_d), "--out", str(out_c)]) == 0
    payload = json.loads(out_c.read_text(encoding="utf-8"))
    assert "classify" in payload and "dedup" in payload and "normalize" in payload


def test_normalize_command_reports_journal(run_cli, tmp_path):
    out = tmp_path / "n.json"
    result = run_cli("normalize", "--from-files", _sample("wechat-demo-01.csv"),
                     "--out", str(out))
    assert result.returncode == 0
    assert "归一化" in result.stdout
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert "normalize" in payload


def test_missing_ledger_file_is_usage_error(run_cli, tmp_path):
    result = run_cli("dedup", "--ledger", str(tmp_path / "nope.json"))
    assert result.returncode == 2


def test_negative_window_is_usage_error(run_cli, tmp_path):
    result = run_cli("run", _sample("wechat-demo-01.csv"),
                     "--window-seconds", "-5", "--out", str(tmp_path / "x.json"))
    assert result.returncode == 2

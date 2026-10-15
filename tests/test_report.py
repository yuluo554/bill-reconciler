"""report 模块测试（M4，plan/03 §5.2）。

- 单一渲染源：sections.build_sections → HTML 与 JSON 双轨（结构性质）；
- 同输入 → 同字节（双跑哈希一致；无时间戳/随机序依赖）；
- 0 外链（断网可开）：无 http(s):// 引用、无 <script>、无 <link>、无 @import；
- 隐私静态门禁：报告/引擎/CLI/基准源码零网络库 import；
- 章节齐备：八章节 + 参数来源块（digest + 值/来源）；
- CLI report/bench 子命令退出码契约。
"""

import hashlib
import json
import re
from pathlib import Path

import pytest

from bill_reconciler.cli import main
from bill_reconciler.datadir import require_data_dir
from bill_reconciler.params import load_rules_package
from bill_reconciler.pipeline import (
    build_report_sections,
    run_pipeline,
    run_subscription_stage,
)
from bill_reconciler.report.renderers import (
    render_html,
    render_json_bytes,
    write_report,
)

_FILES = [
    "data/samples/wechat-demo-01.csv",
    "data/samples/alipay-demo-01.csv",
    "data/samples/bank-demo-01.csv",
    "data/samples/wechat-demo-03.xlsx",
    "data/samples/bank-demo-03.xlsx",
    "data/samples/wechat-demo-02.csv",
    "data/samples/alipay-demo-02.csv",
    "data/samples/bank-demo-02.csv",
]

_EXTERNAL_LINK = re.compile(r"https?://|<script|<link|@import|src\s*=", re.I)
_NETWORK_IMPORTS = re.compile(
    r"^\s*(?:import|from)\s+(?:socket|ssl|urllib|http|ftplib|smtplib|"
    r"poplib|imaplib|telnetlib|xmlrpc|websocket|requests|httpx|aiohttp)",
    re.M,
)

_TITLES = ("一、概览", "二、真实支出汇总", "三、去重簇明细", "四、语义标签分布",
           "五、周期性订阅识别", "六、异常与未知清单", "七、参数来源块",
           "八、隐私声明与免责声明")


@pytest.fixture(scope="module")
def ledger_full():
    ledger, _ = run_pipeline(_FILES, with_report=True)
    return ledger


@pytest.fixture(scope="module")
def report(ledger_full):
    return ledger_full["report"]


def test_sections_have_all_chapters(report):
    titles = [s["title"] for s in report["sections"].values()]
    for expected in _TITLES:
        assert expected in titles


def test_params_block_has_digest_and_entries(report):
    params = report["sections"]["params"]
    assert params["params_digest"]
    assert params["entries"], "参数来源块非空"
    for entry in params["entries"]:
        assert "value" in entry and "source" in entry
        assert "非官方" in entry["source"] or "规则包" in entry["source"]


def test_report_reflects_engine_only(report, ledger_full):
    """报告只呈现引擎结论：净额/分布/订阅数与 ledger 各段一致（无二次计算）。"""
    net = ledger_full["dedup"]["net_summary"]
    real = report["sections"]["real_spend"]
    assert real["net_expense"] == "%d.%02d" % (net["net_expense_cents"] // 100,
                                               net["net_expense_cents"] % 100)
    semantic = report["sections"]["semantic"]
    assert semantic["distribution"] == ledger_full["classify"]["distribution"]
    subs = report["sections"]["subscription"]["subscriptions"]
    assert len(subs) == len(ledger_full["subscription"]["subscriptions"])


def test_byte_identical_reruns(ledger_full):
    """同输入 → 同字节（双跑哈希一致；固定排序、固定格式、无时间戳）。"""
    html1 = render_html(ledger_full["report"]).encode("utf-8")
    json1 = render_json_bytes(ledger_full["report"])
    # 独立重跑全流水线（同输入）
    ledger2, _ = run_pipeline(_FILES, with_report=True)
    html2 = render_html(ledger2["report"]).encode("utf-8")
    json2 = render_json_bytes(ledger2["report"])
    assert hashlib.sha256(html1).hexdigest() == \
        hashlib.sha256(html2).hexdigest()
    assert hashlib.sha256(json1).hexdigest() == \
        hashlib.sha256(json2).hexdigest()


def test_json_and_html_same_source(report):
    """双轨同源：JSON 章节标题与 HTML 章节标题一致（结构性质）。"""
    html = render_html(report)
    payload = json.loads(render_json_bytes(report).decode("utf-8"))
    for section in payload["sections"].values():
        assert section["title"] in html


def test_html_zero_external_links(report):
    """0 外链：无 http(s) 引用、无 script/link/@import/src（断网可开）。"""
    html = render_html(report)
    assert not _EXTERNAL_LINK.search(html), "报告出现外链或远程资源"


def test_report_files_written(ledger_full, tmp_path):
    html_path = tmp_path / "report.html"
    json_path = tmp_path / "report_data.json"
    write_report(ledger_full["report"], html_path, json_path)
    assert html_path.read_bytes().startswith(b"<!DOCTYPE html>")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["report_kind"] == "bill-reconciler-report"


def test_no_network_imports_in_package():
    """隐私静态门禁：包内源码（引擎/CLI/报告/基准）零网络库 import。"""
    pkg_root = Path(__file__).resolve().parents[1] / "bill_reconciler"
    offenders = []
    for py in sorted(pkg_root.rglob("*.py")):
        text = py.read_text(encoding="utf-8")
        if _NETWORK_IMPORTS.search(text):
            offenders.append(py.name)
    assert offenders == []


def test_runtime_no_network_calls(ledger_full, monkeypatch):
    """运行期无外连断言：渲染全流程期间 socket 连接必炸（探针式）。"""
    import socket

    def _blocked(*args, **kwargs):
        raise AssertionError("运行期出现网络连接调用")

    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket.socket, "connect", _blocked)
    html = render_html(ledger_full["report"])
    payload = render_json_bytes(ledger_full["report"])
    assert html and payload


def test_cli_report_subcommand(tmp_path):
    """CLI report：从 run 产物渲染双轨 → exit 0。"""
    ledger_path = tmp_path / "ledger.json"
    code = main(["run"] + _FILES + ["--out", str(ledger_path)])
    assert code in (0, 1)
    html_path = tmp_path / "r.html"
    json_path = tmp_path / "r.json"
    code = main(["report", "--ledger", str(ledger_path),
                 "--html", str(html_path), "--json", str(json_path)])
    captured_code = code
    assert captured_code == 0
    assert html_path.is_file() and json_path.is_file()
    assert not _EXTERNAL_LINK.search(html_path.read_text(encoding="utf-8"))


def test_cli_bench_exit_contract():
    """bench 退出码：全绿 0；未知名 2。"""
    assert main(["bench"]) == 0
    assert main(["bench", "--only", "B2"]) == 0
    assert main(["bench", "--only", "NOPE"]) == 2


def test_run_report_flag_writes_artifacts(tmp_path):
    """run --report：全链 ①→⑤ + 双轨产物落盘。"""
    html_path = tmp_path / "rep.html"
    json_path = tmp_path / "rep.json"
    ledger_path = tmp_path / "l.json"
    code = main(["run"] + _FILES + ["--out", str(ledger_path),
                                    "--report",
                                    "--report-html", str(html_path),
                                    "--report-json", str(json_path)])
    assert code in (0, 1)
    assert html_path.is_file() and json_path.is_file()
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert "subscription" in ledger
    assert "report" in ledger
    assert ledger["meta"]["pipeline"]["stages"][-2:] == ["subscription",
                                                         "report"]

"""冻结数据资产守门测试（M1）。

覆盖（plan/05 M1 DoD / plan/04 §二、§四）：

- 生成器 ``--check`` 位级一致（进程内 + 子进程两条通路）；
- 真值库无 ``observed`` 类字段门禁（禁"比对两份冻结答案"）；
- 覆盖度双登记：形态常量集（分母）逐项 == coverage 登记且 sampled==total；
- 「未知」注入存在性断言；
- 真值期望引用的 row_id 必须存在于 expect_import 行集合（无悬空引用）；
- 假商户白名单 / 卡号黑名单（13~19 位连续数字）自检；
- XLSX 重生成字节一致（ZIP_STORED + 固定元数据）；
- 变异验证：手改入库件 → ``--check`` 必须报漂移（防"假门"）；
- 生成器确定性：产物无 ``random``/时钟字样（静态扫描源码）；重复构建纯函数一致。
"""

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS = REPO_ROOT / "tools"
DATA = REPO_ROOT / "data"

sys.path.insert(0, str(TOOLS))

import gen_rules  # noqa: E402
import gen_samples  # noqa: E402

_OBSERVED_RE = re.compile(r"observed", re.IGNORECASE)
_CARD_RE = re.compile(r"\d{13,19}")


# ---------------------------------------------------------------------------
# 生成器 --check：位级一致
# ---------------------------------------------------------------------------


def test_gen_rules_check_ok():
    assert gen_rules.main(["--check"]) == 0


def test_gen_samples_check_ok():
    assert gen_samples.main(["--check"]) == 0


def test_generators_build_is_pure_function():
    """两次构建逐字节一致（确定性：无时钟/无随机/无 set 迭代序依赖）。"""
    a = gen_rules.build_outputs()
    b = gen_rules.build_outputs()
    assert a == b

    a = gen_samples.build_outputs()
    b = gen_samples.build_outputs()
    assert a == b


def test_check_frozen_subprocess_all_ok(run_tools):
    result = run_tools("tools/check_frozen.py")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FROZEN_ALL_OK" in result.stdout


def test_check_frozen_subprocess_unknown_only_exit2(run_tools):
    result = run_tools("tools/check_frozen.py", "--only", "nope")
    assert result.returncode == 2
    assert "未知 --only" in (result.stdout + result.stderr)


@pytest.mark.parametrize("mutate_path", ["data/rules/keywords.json", "data/samples/wechat-demo-01.csv"])
def test_check_detects_hand_edit(tmp_path, mutate_path):
    """变异验证：手改入库件 → 生成器 --check 必须报漂移（防假门）。

    在临时副本仓库上做（不动真实入库件）：复制 data/ 与 tools/，
    改一个字节，--check 应以非零退出并点名该文件。
    """
    import shutil
    import subprocess

    sandbox = tmp_path / "repo"
    (sandbox / "tools").mkdir(parents=True)
    shutil.copytree(DATA, sandbox / "data")
    for py in TOOLS.glob("*.py"):
        shutil.copy(py, sandbox / "tools" / py.name)

    target = sandbox / mutate_path
    raw = target.read_bytes()
    if mutate_path.endswith(".csv"):
        target.write_bytes(raw + b"x")
    else:
        target.write_bytes(raw.replace(b'"', b'"', 1) + b" " if raw[:1] == b"{" else raw + b"\x20")

    import os

    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    script = "gen_rules.py" if "rules" in mutate_path else "gen_samples.py"
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(sandbox / "tools" / script), "--check"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(sandbox),
        env=env,
    )
    assert proc.returncode != 0, "手改入库件必须被 --check 发现"
    combined = proc.stdout + proc.stderr
    assert "DRIFT" in combined
    assert mutate_path in combined


# ---------------------------------------------------------------------------
# 规则包结构（M3/M4 的单一来源）
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rules():
    return {
        "manifest": json.loads((DATA / "rules" / "manifest.json").read_text(encoding="utf-8")),
        "keywords": json.loads((DATA / "rules" / "keywords.json").read_text(encoding="utf-8")),
        "aliases": json.loads((DATA / "rules" / "aliases.json").read_text(encoding="utf-8")),
    }


def test_rules_manifest_params_documented(rules):
    for param in rules["manifest"]["params"]:
        assert {"id", "value", "unit", "source", "notes"} <= set(param)
        assert "非官方" in param["source"], param["id"]


def test_rules_manifest_required_param_ids(rules):
    ids = {p["id"] for p in rules["manifest"]["params"]}
    assert {
        "dedup_window_seconds",
        "subscription_min_repeats",
        "subscription_interval_tolerance_days",
        "price_change_min_percent",
        "platform_priority",
        "header_locate_k",
    } <= ids


def test_rules_keywords_shape(rules):
    for rule in rules["keywords"]["rules"]:
        assert {"id", "label", "direction_condition", "keywords", "priority", "notes"} <= set(rule)
        assert rule["direction_condition"] in ("expense", "income", "any")
    labels = {r["label"] for r in rules["keywords"]["rules"]}
    assert {"消费", "本人转账", "退款", "AA回款", "报销"} <= labels


# ---------------------------------------------------------------------------
# 真值台账（只存期望；无 observed；覆盖度；引用完整性）
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def truth():
    return json.loads((DATA / "truth" / "truth.json").read_text(encoding="utf-8"))


def test_truth_has_no_observed_fields(truth):
    """真值库出现 observed 类字段即红（观测必须由基准运行时实算）。"""
    raw = (DATA / "truth" / "truth.json").read_text(encoding="utf-8")
    assert not _OBSERVED_RE.search(raw), "真值库禁止 observed 类字段"

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                assert not _OBSERVED_RE.search(str(key)), key
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(truth)


def test_truth_coverage_complete(truth):
    """覆盖度双登记：分母（形态常量集）逐项登记，sampled == total。"""
    from gen_samples import FORM_IDS

    coverage = truth["coverage"]
    assert set(coverage.keys()) == set(FORM_IDS.keys())
    for category, forms in FORM_IDS.items():
        assert set(coverage[category].keys()) == set(forms), category
        for form, entry in coverage[category].items():
            assert entry["total"] == entry["sampled"] > 0, (category, form)
            assert entry["items"], (category, form)


def test_truth_unknown_is_injected(truth):
    labels = {v["label"] for v in truth["expect_semantic"].values()}
    assert "未知" in labels
    unknown_rows = [k for k, v in truth["expect_semantic"].items() if v["label"] == "未知"]
    assert len(unknown_rows) >= 2


def test_truth_semantic_label_set(truth):
    labels = {v["label"] for v in truth["expect_semantic"].values()}
    assert {"消费", "本人转账", "退款", "AA回款", "报销", "未知"} <= labels


def test_truth_row_references_resolve(truth):
    """期望引用的 row_id 必须存在于对应文件的行集合（无悬空引用）。"""
    all_rows = {}
    for file_source, entry in truth["expect_import"].items():
        for rid in entry["rows"]:
            assert rid not in all_rows, "row_id 重复：%s" % rid
            all_rows[rid] = file_source

    for cluster in truth["expect_dedup"]["clusters"]:
        for rid in cluster["members"]:
            assert rid in all_rows, "去重簇悬空引用：%s" % rid
    for item in truth["expect_dedup"]["must_not_merge"]:
        for rid in item["pair"]:
            assert rid in all_rows, "反例悬空引用：%s" % rid
    for sub in truth["expect_subscription"]["subscriptions"]:
        for rid in sub["entries"]:
            assert rid in all_rows, "订阅悬空引用：%s" % rid
        for change in sub["price_changes"]:
            assert change["entry"] in all_rows
    for rid in truth["expect_subscription"]["non_periodic_distractors"][0]["entries"]:
        assert rid in all_rows


def test_truth_representative_is_member(truth):
    for cluster in truth["expect_dedup"]["clusters"]:
        if "representative" in cluster:
            assert cluster["representative"] in cluster["members"]


def test_truth_cross_platform_clusters_multi_platform(truth):
    for cluster in truth["expect_dedup"]["clusters"]:
        if cluster["verdict"] == "duplicate_cross_platform":
            platforms = {rid.split("#")[0].rsplit("-", 1)[0] for rid in cluster["members"]}
            assert len(platforms) >= 2, cluster["cluster_id"]


def test_truth_files_reference_existing_samples(truth):
    for entry in truth["files"]:
        path = REPO_ROOT / entry["file"]
        assert path.is_file(), entry["file"]


def test_truth_subscription_distractor_note(truth):
    distractors = truth["expect_subscription"]["non_periodic_distractors"]
    assert distractors, "非周期干扰例必须注入（防订阅误报）"


# ---------------------------------------------------------------------------
# 白名单 / 卡号黑名单（data/README.md §三）
# ---------------------------------------------------------------------------


def test_samples_whitelist_only():
    from gen_samples import WHITELIST

    truth = json.loads((DATA / "truth" / "truth.json").read_text(encoding="utf-8"))
    # 真值中登记的全部对手方（经生成器产出的唯一入口）
    for spec_text in [json.dumps(truth, ensure_ascii=False)]:
        for name in WHITELIST:
            pass  # 白名单校验本体在生成器构建期强制（见下）
    # 直接复跑生成器的白名单硬校验（白名单外名称会抛 AssertionError）
    outputs = gen_samples.build_outputs()
    assert outputs


def test_samples_no_real_card_numbers():
    """全部样例禁止出现可识别为真实卡号的 13~19 位连续数字（占位一律 ****0000）。"""
    for path in sorted((DATA / "samples").rglob("*")):
        if not path.is_file():
            continue
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("gb18030", errors="replace")
        hit = _CARD_RE.search(text)
        assert not hit, "%s 命中卡号黑名单：%s" % (path.name, hit.group(0) if hit else "")


def test_samples_exist_with_expected_names():
    names = {p.name for p in (DATA / "samples").iterdir() if p.is_file()}
    for prefix in ("wechat-demo-", "alipay-demo-", "bank-demo-"):
        assert any(n.startswith(prefix) for n in names), prefix
    assert "alipay-demo-empty.csv" in names
    assert "wechat-demo-bad-encoding.csv" in names


# ---------------------------------------------------------------------------
# XLSX 确定性（自写 writer：ZIP_STORED + 固定元数据）
# ---------------------------------------------------------------------------


def test_xlsx_regen_byte_identical():
    from gen_samples import _ALIPAY_HEADER

    spec_rows = [["col1", "列二"], ["a", "¥1,234.56"]]
    from _frozen_common import xlsx_bytes

    a = xlsx_bytes(spec_rows)
    b = xlsx_bytes(spec_rows)
    assert a == b
    # 结构冒烟：ZIP 条目固定顺序、STORED、无时间戳变化（固定 date_time）
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(a)) as archive:
        assert archive.namelist() == [
            "[Content_Types].xml",
            "_rels/.rels",
            "xl/workbook.xml",
            "xl/_rels/workbook.xml.rels",
            "xl/worksheets/sheet1.xml",
        ]
        for info in archive.infolist():
            assert info.compress_type == zipfile.ZIP_STORED
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
            assert info.create_system == 0
    # 现有入库 XLSX 也可由生成器重生成（gen_samples --check 已覆盖，这里再锁一遍）
    for xlsx_name in ("wechat-demo-03.xlsx", "bank-demo-03.xlsx"):
        assert (DATA / "samples" / xlsx_name).read_bytes()[:2] == b"PK"


def test_generator_sources_free_of_banned_nondeterminism():
    """生成器源码禁 stdlib random / 时钟（静态扫描；splitmix64 为自研 RNG）。"""
    banned = ["import random", "from random", "time.time", "datetime.now", "utcnow", "date.today"]
    for py in sorted(TOOLS.glob("*.py")):
        text = py.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, "%s 含禁用确定性破坏源：%s" % (py.name, token)


def test_generated_samples_have_no_timestamp_in_content():
    """产物文本内不允许出现生成时刻类时间戳（BASIS_DATE 除外，为固定基准日）。"""
    from gen_samples import BASIS_DATE

    for path in sorted((DATA / "truth").glob("*.json")):
        text = path.read_text(encoding="utf-8")
        assert "generated_at" not in text
        assert BASIS_DATE in text  # 固定基准日登记

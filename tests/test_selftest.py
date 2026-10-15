"""selftest 契约：骨架阶段 PASS + PENDING 诚实清单；坏环境 FAIL。"""

from bill_reconciler.cli import main


def test_selftest_in_process_passes(capsys):
    code = main(["selftest"])
    captured = capsys.readouterr()  # 只能消费一次
    assert code == 0
    assert "[PASS]" in captured.out
    assert "结论：" in captured.out


def test_selftest_subprocess_exit0(run_cli):
    result = run_cli("selftest")
    assert result.returncode == 0
    assert "bill-reconciler selftest" in result.stdout


def test_selftest_reports_pending_m1_assets(run_cli):
    # M0 骨架期：数据资产（规则包 / 合成样例）尚未生成，必须显式 PENDING、不得冒充通过。
    # M1 完成后此期望翻转为断言 [PASS]（见 plan/05 里程碑 M1 DoD —— 刻意的"期望变更"）。
    result = run_cli("selftest")
    assert result.returncode == 0
    assert "[PENDING]" in result.stdout
    assert "计划 M1 生成" in result.stdout


def test_selftest_flags_invalid_data_dir(run_cli, tmp_path):
    bogus = tmp_path / "not-a-data-dir"
    result = run_cli("selftest", env={"BILL_RECONCILER_DATA": str(bogus)})
    # 显式环境变量指向无效目录 → 数据目录检查 FAIL → 退出码 1（完成但检出问题）
    assert result.returncode == 1
    assert "BILL_RECONCILER_DATA" in (result.stdout + result.stderr)

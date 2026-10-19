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
    # 期望变更（M1，plan/05 里程碑 M1 DoD）：M0 骨架期数据资产尚未生成，本测试曾断言
    # "[PENDING]" 与 "计划 M1 生成"；M1 已生成规则包 + 合成样例并配 --check 位级守门，
    # 按既定口径（HANDOFF-M1 §三 K2）翻转期望：数据资产必须 [PASS]、无 PENDING 残留。
    # 期望变更（M3）：新增"参数字面量门禁"检查项（plan/05 里程碑 M3 DoD）。
    result = run_cli("selftest")
    assert result.returncode == 0
    assert "[PENDING]" not in result.stdout
    assert "[PASS] 规则包" in result.stdout
    assert "[PASS] 合成样例" in result.stdout
    assert "[PASS] 参数字面量门禁" in result.stdout


def test_selftest_flags_invalid_data_dir(run_cli, tmp_path):
    bogus = tmp_path / "not-a-data-dir"
    result = run_cli("selftest", env={"BILL_RECONCILER_DATA": str(bogus)})
    # 期望变更（DEC2=A，退出码口径自洽）：数据目录不可用属"环境不可用"（3），
    # 与 bench 及 README 退出码表一致；此前报 1（"检出需人工处理的问题"）是口径错位。
    assert result.returncode == 3
    assert "BILL_RECONCILER_DATA" in (result.stdout + result.stderr)

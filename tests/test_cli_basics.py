"""CLI 基础行为：--help / --version / 用法错误（退出码契约，plan/02 §4.5）。"""

from bill_reconciler import __version__

# CLI 最终态的全部子命令（M0 起帮助里就应可见，便于骨架期审阅命令面）
SUBCOMMANDS = ["import", "normalize", "dedup", "classify", "report", "run", "bench", "selftest"]


def test_help_lists_all_subcommands(run_cli):
    result = run_cli("--help")
    assert result.returncode == 0
    for name in SUBCOMMANDS:
        assert name in result.stdout


def test_version_flag(run_cli):
    result = run_cli("--version")
    assert result.returncode == 0
    assert result.stdout.strip() == "bill-reconciler %s" % __version__


def test_no_args_is_usage_error(run_cli):
    result = run_cli()
    assert result.returncode == 2
    assert "usage" in (result.stderr + result.stdout).lower()


def test_unknown_subcommand_is_usage_error(run_cli):
    result = run_cli("definitely-not-a-command")
    assert result.returncode == 2


def test_subcommand_help_works(run_cli):
    result = run_cli("import", "--help")
    assert result.returncode == 0
    assert "import" in result.stdout

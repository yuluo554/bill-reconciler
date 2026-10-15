"""data/ 目录解析契约（plan/02 §4.3）。"""

from pathlib import Path

import pytest

from bill_reconciler.datadir import ENV_VAR, find_data_dir, require_data_dir
from bill_reconciler.errors import EnvError

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_finds_repo_data_dir():
    data_dir = find_data_dir(start=REPO_ROOT)
    assert data_dir is not None
    assert data_dir.name == "data"
    assert (data_dir / "README.md").is_file()


def test_env_override_wins(tmp_path):
    fake = tmp_path / "mydata"
    fake.mkdir()
    (fake / "README.md").write_text("x", encoding="utf-8")
    data_dir = find_data_dir(env={ENV_VAR: str(fake)})
    assert data_dir == fake


def test_env_bogus_raises_env_error(tmp_path):
    with pytest.raises(EnvError) as excinfo:
        find_data_dir(env={ENV_VAR: str(tmp_path / "nope")})
    assert excinfo.value.exit_code == 3


def test_require_data_dir_returns_or_raises():
    assert require_data_dir(start=REPO_ROOT).name == "data"


def test_missing_data_dir_raises_env_error(tmp_path, monkeypatch):
    # 隔离场景：CWD 挪到一个没有 data/ 的独立目录树里，
    # 断言找不到时抛 EnvError（退出码 3），而不是静默回落。
    isolated = tmp_path / "isolated"
    isolated.mkdir()
    monkeypatch.chdir(isolated)
    with pytest.raises(EnvError):
        require_data_dir(env={})


def test_repo_subdirectory_still_finds_repo_data_dir():
    # 仓库子目录（如 plan/、scratch/）内运行：CWD 向上探查应命中仓库根 data/
    subdir = REPO_ROOT / "plan"
    data_dir = find_data_dir(start=subdir, env={})
    assert data_dir is not None
    assert data_dir.resolve() == (REPO_ROOT / "data").resolve()

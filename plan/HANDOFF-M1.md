# plan/HANDOFF-M1.md — M0 → M1 交接快照

> 用法：新对话以绝对路径读取本文件（启动命令由用户侧拼接，本文件内一律相对路径）。
> 写入时间：2026-10-15（M0 收尾）。**M1 开工后本文件仅作历史快照**。

## 一、当前进度 + 证据

**M0「计划先行 + 可运行骨架」已完成**（2026-10-15，单对话完成 plan/02–06 撰写 + 骨架实现 + 全量验证）。

| 交付物 | 证据 |
|---|---|
| plan/02–06 五份计划文档落盘 | `plan/02-架构与技术选型.md` 等 5 份（v1，2026-10-15） |
| plan/00 回写（索引 v2 / 决策 9 条新增 / M0 状态 ✅） | `plan/00-README总览.md` |
| 可运行骨架 | `bill_reconciler/`（cli/errors/datadir/selftest/__main__）；`--help`/`--version`/`selftest` 可用；7 个功能子命令占位 |
| 测试 | `tests/` 6 个文件 27 项；**双解释器 + 干净 venv 三通道全绿（27 passed 各通道）** |
| 干净 venv 按 README 逐条验证 | `.clean-venv`（3.12）editable 安装 → pytest 27 全绿（metadata 2 项 skip 翻转为实跑）→ `brc`/`bill-reconciler` 双名冒烟 → 任意目录 `python -m bill_reconciler --version` OK |
| 编码守卫回归 | `tests/test_encoding_guard.py`：cp1252 环境字节级断言合法 UTF-8 |
| CI 工作流 | `.github/workflows/ci.yml`（py3.8/3.12 × ubuntu/windows 四矩阵 + 双形态 CLI 冒烟）。**本地等价校验（未接远端，CI 待首推验证）** |
| 工程配套 | `pyproject.toml`（零运行时依赖 + dev extras + 双 console script）、`.gitattributes`（冻结资产 `-text` 预置）、LICENSE(MIT)、`tools/README.md`、README 四声明 |

**M0 实测勘误（已回写 plan/02 §4.3）**：数据目录解析原设计含"包位置向上探查"支，实跑在仓库子目录会经包位置**误命中**仓库根（隔离测试暴露）→ 删除该支，只留"CWD 向上探查"；行为验证：仓库内子目录可命中、TEMP 隔离目录 exit 3、环境变量显式指向恢复 exit 0。

## 二、下一棒待办（M1 数据先行，细节见 plan/05 与 plan/04）

1. `tools/gen_rules.py`：产出 `data/rules/{manifest,keywords,aliases}.json` 冻结规则包（参数含：去重时间窗口 / 最小重复次数 / 间隔容差 / 涨价阈值 / 平台优先级 / 表头定位 K；全部标注"经验默认（非官方）"；基准门槛也在 manifest）；
2. `tools/gen_samples.py`：三平台合成账单（`data/samples/`，形态矩阵 plan/04 §三全注入，含"未知"与全部干扰例）+ 真值台账（`data/truth/`，同源同一次运行）；
3. `tools/check_frozen.py`：全量 `--check` 守门入口；
4. 生成器纪律：自研 splitmix64（禁 stdlib random / set 迭代序 / 时钟）；XLSX writer `ZIP_STORED`+`create_system=0`+固定 `date_time`；产物无时间戳；`.gitattributes -text` 已预置；
5. 测试：`--check` 位级一致（双解释器）、覆盖度双登记、真值库无 `observed` 字段门禁、假商户白名单/卡号黑名单自检；
6. `selftest` 数据资产两 PENDING 项翻转为 PASS（**同步翻转 tests/test_selftest.py 的期望并注明"期望变更"**）；
7. M1 收尾：DoD 验证 → plan/00·05·06 回写 → HANDOFF-M2 → commit。

## 三、既定口径清单（动了会打挂测试/基准；K 编号沿用 M1+）

- **K1 退出码契约 0/1/2/3**（plan/02 §4.5）：0 完成无未决 / 1 完成但有需人工处理问题 / 2 用法与输入不可用（**占位命令"尚未实现"也是 2**）/ 3 环境不可用。锁在 `tests/test_cli_basics.py`、`test_cli_stubs.py`、`test_selftest.py`。命令实装后**期望按最终语义翻转并注明**，不得静默放宽。
- **K2 selftest 三态**：PASS/FAIL/PENDING；任一 FAIL → exit 1；PENDING 不冒充通过（`tests/test_selftest.py::test_selftest_reports_pending_m1_assets` 锁"M0 期必须 PENDING"——M1 生成数据后翻转此期望）。
- **K3 数据目录解析**：环境变量（无效不回落）→ CWD 向上；**刻意无"包位置"支**（plan/02 §4.3 实测勘误）。`tests/test_datadir.py` 锁定含"仓库子目录可命中"。
- **K4 编码守卫**：入口 `cli.main` 与每个 `tools/` 脚本先 `_ensure_utf8_stdio()`；cp936 系/UTF-8 家族保持不动，其余（cp1252 等）reconfigure 为 UTF-8；字节级回归在 `tests/test_encoding_guard.py`。
- **K5 冻结产物 `-text`**：`data/{samples,truth,rules}/**` 与 `*.xlsx` 已在 `.gitattributes` 标 `-text`——sha256 台账据此比对，勿动。
- **K6 元数据测试双态**：`tests/test_package_metadata.py` 在未安装通道 skip、安装通道实跑（干净 venv 验证 = 27 全绿、源码态 = 27 passed 2 skipped 是**同一套件**的合法两态，不是回归）。
- **K7 决策记录唯一台账 = plan/00 §二**；plan/06 §五是待拍板区（P1–P6 已给默认并按默认执行骨架），用户拍板后结案回写 00。

## 四、本机环境坑（只写实测过的）

- **`py` 不用 `python`**；跑脚本一律 `py -X utf8`（本机双通道：3.8.8 与 3.12.10，`py -0p` 可见）。
- **pip 无代理直连失败（DNS getaddrinfo failed）**：干净 venv 装包用默认系统代理配置即可成功（不要 `NO_PROXY="*"`）；源走清华镜像 `-i https://pypi.tuna.tsinghua.edu.cn/simple`。
- **Git Bash `rm -rf` 目录被占用**（CWD 停在该目录内时）：换到目录外再删。
- **venv 可执行文件用相对形式** `./.clean-venv/Scripts/<name>.exe`（Git Bash）。
- 测试约定：`PYTHONDONTWRITEBYTECODE=1` 全程（含 pip install）；子进程测试显式 `encoding="utf-8"`（conftest 已封装 `run_cli` 夹具）。
- `.clean-venv/` 已在 .gitignore（隔离验证用，不入库）。

## 五、DoD 逐项 checklist（M0，已验证）

- [x] plan/02–06 落盘；plan/00 索引/决策/里程碑回写
- [x] `--help` / `--version` / `selftest` 可用；未知子命令 exit 2；占位命令打印"尚未实现（计划于 Mx）"并 exit 2
- [x] 测试双解释器全量绿（3.8：27 passed 2 skipped；3.12：同）
- [x] 干净 venv 按 README 逐条跑通（editable + console script 双形态冒烟；安装通道 27 全绿）
- [x] 编码守卫回归（cp1252 环境中文输出不崩，字节级断言）
- [x] `plan/HANDOFF-M1.md` 落盘（本文件）
- [x] commit（工作树干净）
- [x] CI：工作流文件已落盘；**本地等价校验（未接远端，CI 待首推验证）**

## 六、关键命令速查

```bash
cd <仓库根>
py -0p                                   # 摸清解释器通道
PYTHONDONTWRITEBYTECODE=1 py -3.8 -X utf8 -m pytest -q    # 3.8 全量
PYTHONDONTWRITEBYTECODE=1 py -3.12 -X utf8 -m pytest -q   # 3.12 全量
python -m bill_reconciler --help / selftest               # 免安装通路
python -m pip install -e ".[dev]" && brc --version        # 安装通路冒烟
# 干净 venv（3.12 通道 + 清华镜像；不要加 NO_PROXY）
py -3.12 -m venv .clean-venv
PYTHONDONTWRITEBYTECODE=1 ./.clean-venv/Scripts/python.exe -m pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple
PYTHONDONTWRITEBYTECODE=1 ./.clean-venv/Scripts/python.exe -m pytest -q
```

# plan/HANDOFF-M3.md — M2 → M3 交接快照

> 用法：新对话以绝对路径读取本文件（启动命令由用户侧拼接，本文件内一律相对路径）。
> 写入时间：2026-10-15（M2 收尾）。**M3 开工后本文件仅作历史快照**。

## 一、当前进度 + 证据

**M2「解析层」已完成**（2026-10-15，单对话完成 ingest 五子模块 + import 子命令 + 三态矩阵测试 + B1 候选基准 + 收尾验证）。

| 交付物 | 证据 |
|---|---|
| ingest 包 | `bill_reconciler/ingest/` 五件：`detect.py`（BOM→UTF-8 严格→GB18030→失败报错，顺序写死）、`locate.py`（表头定位 K=2/上限 20 行 + 列映射：精确→去空白→别名表；**已登记非语义列**（交易单号等）既不进 field_map 也不报 unknown）、`parsers.py`（三平台行解析：金额去千分位/货币符号白名单含 U+00A5+U+FFE5、收支类型列与收支分列两形态、三态判定）、`xlsx_reader.py`（自写最小读取器，仅支持本项目 writer 形态，超纲特征显式错误码）、`importer.py`（编排 + IR ledger + file_code_from_detail） |
| import 子命令 | `cli.py::_cmd_import`：`brc import <文件...> --out ledger.json`；平台识别 = 显式 `--platform` 优先、缺省按文件名前缀（不猜测）；参数（K/扫描上限/别名表）只读规则包；退出码 0/1/2 |
| 三态矩阵测试 | `tests/test_import.py` 11 项：真值 77 行逐条对齐（file_status/file_issue_codes/column_issues/row 三态全对齐）、invalid 绝不入库、unknown 入库且 issues 显式、两次运行全量相等、单文件与全量导入结果一致、审计字段齐备 |
| 失败路径测试 | `tests/test_ingest_paths.py` 20 项：编码探测正/反向样例、表头定位（含扫描上限）、列映射变体、金额/时间单元、XLSX 覆盖度（sharedStrings/压缩/多 sheet/坏 zip → 显式错误码，注入式测试）、文件级失败全谱 |
| CLI 契约测试 | `tests/test_import_cli.py` 7 项：干净 0 / 行级 1（清单全打印到 stderr）/ 文件级 2（混合输入 2 胜出、其余文件照常导入）/ 全 12 件矩阵对账 |
| B1 候选基准 | `bill_reconciler/bench_runner.py`：`run_b1()`（真值 vs 解析对账，**门槛读规则包** `bench_thresholds`，缺失即 InputError）+ `run_suite_live_probe('B1')` 探活；`tests/test_bench_b1.py` 5 项（真引擎 F1=1.0、门槛是数据、探活可证伪） |
| 变异验证 ×6 | 金额强制 0→B1 红 / unknown 静默→test_import 红 / 编码顺序反转→test_ingest_paths 红 / 表头 K 失效→test_import 红 / XLSX 压缩门失效→红 / CLI 退出码门失效→红；每处恢复后 95 passed |
| 测试 | 双解释器全量 **95 passed**（3.8.8 / 3.12.10）；干净 venv（3.12 editable）95 passed + `brc import` 三退出码冒烟 |

**M2 开工勘误（数据侧，K8 流程已走完）**：M1 产物 3 处形态注入未落盘（bank 渲染器忽略 `amount_cell`、EXTRA 字段注入因 `add_row` 复制 dict 失效 ×2）→ `gen_samples.py` **v2** 重生成；`gen_rules.py` **v2** 新增列名别名表 `column_aliases`（5 条）。真值期望不变、磁盘字节变化；`data/README.md §六` 台账全量回填（truth.json = `35ee581c…`）；`check_frozen.py` 全绿；52 项 M1 测试无翻转全过。勘误已回写 plan/04 §二。

## 二、下一棒待办（M3 归一化+去重+语义，细节见 plan/05 M3 节与 plan/03 §二/三/四）

1. `bill_reconciler/normalize.py`：归并动作序列写死（去空白→全半角→后缀剥离→别名表）；逐条依据 `{rule, detail, evidence}`；未命中原样保留（依据为空）——"归并了"与"没归并"可区分；纯函数；
2. `bill_reconciler/dedup.py`：三元组（金额 Decimal 精确相等 + |Δt|≤W 闭区间 + 归一对手方）+ 同方向聚类；链式相邻聚类按固定排序；**跨平台前提**（≥2 平台才 `duplicate_cross_platform`；同平台 → `candidate_same_platform` 显式不合并）；代表笔规则（时间最早→平台优先级→行号）；`--window-seconds` 覆盖经 params 单点；
3. `bill_reconciler/classify.py`：keywords.json 规则按 priority 升序评估、方向条件不符跳过；全部命中条目记录；**未命中 → `未知` 一等结论，绝不 fallthrough 为消费**；干扰例（退款词在支出方向、张三转账）不误判；
4. `run` 子命令编排接入 normalize→dedup→classify（M2 起"逐步接入"口径，M3 接前三段）；
5. 边界测试（规则驱动，不读真值库）：窗口 Δt=W 恰好命中 / W+1s 不命中 / 金额差 1 分 / 超窗同额 / 窗内不同额——真值已有 5 对 must_not_merge 反例 + 4 个簇可直接用；
6. 参数单点 `params.py` 首次落地（manifest 唯一访问点）；零参数字面量门禁的生成器侧准备（token 集从 manifest 数值生成）可同步铺；
7. M3 收尾：DoD 验证 → plan/00·05·06 回写 → HANDOFF-M4 → commit。

## 三、既定口径清单（动了会打挂测试/基准；K 编号沿用）

- **K1 退出码契约 0/1/2/3**（plan/02 §4.5）：`import` 已按最终语义锁定（0 干净 / 1 行级问题 / 2 文件级失败与用法，`tests/test_import_cli.py`）；其余占位命令仍 exit 2（`tests/test_cli_stubs.py`，M3 实装 normalize/dedup/classify 后照此翻转期望并注明）。
- **K2 selftest 三态**：5 PASS / 0 PENDING / 0 FAIL；新增资产检查项时保持"PENDING 不冒充通过"纪律。
- **K3 数据目录解析**：环境变量（无效不回落）→ CWD 向上；不要在测试里 chdir 后直调 `main()`。
- **K4 编码守卫**：入口 `cli.main` 与每个 `tools/` 脚本先 `_ensure_utf8_stdio()`；新模块沿用（ingest 无 print，无需守卫；M3 若加 CLI 输出沿用 cli 入口现有守卫）。
- **K5 冻结产物 `-text`**：`data/{samples,truth,rules}/**` 禁动；sha256 台账在 `data/README.md §六`（truth.json = `35ee581c…`，v2 现值），`check_frozen.py --ledger` 可复核。
- **K6 元数据测试双态**：未安装通道 skip / 安装通道实跑，是同一套件合法两态。
- **K7 决策记录唯一台账 = plan/00 §二**；P1–P5 拍板项仍待用户结案。
- **K8 生成器确定性**：splitmix64（seed 20261015）、禁 stdlib random / set 迭代序 / 时钟；**生成器现为 v2**（samples v2 + rules v2）；改生成逻辑 = 版本号++ + 整目录重生成 + `--check` 全绿 + 台账回填一并提交。**新教训（M2）**：形态注入后必须读回磁盘件断言形态在场（防"真值台账与内存态一致但磁盘丢了形态"）。
- **K9 真值只存期望**：`expect_import / expect_semantic / expect_dedup / expect_subscription` 四段；观测字段门禁在 `tests/test_frozen_assets.py`；**expect_import 现已被 ingest 全量消费**（改任何一行期望都要先过 `tests/test_import.py` 的 77 行对齐）。
- **K10 形态常量集 = 覆盖度分母**：`tools/gen_samples.py::FORM_IDS`（导入 27 / 语义 8 / 去重 8 / 订阅 6）。
- **K11（M2 新增）unknown 列 vs 登记非语义列**：`locate.PLATFORM_EXPECTED_COLUMNS` 是"已登记列名全集"（含交易单号/支付方式等非语义列）——表头定位锚用 `PLATFORM_HEADER_ANCHORS`（核心列），unknown_column 只报**登记全集之外**的列（如商户编号）；新增平台列先扩登记全集。
- **K12（M2 新增）行级问题码清单**：`amount_missing / amount_not_numeric / time_unparseable / column_count_mismatch / amount_ambiguous / unmapped_direction` + 文件级 `encoding_undetermined / header_not_found / required_column_missing / empty_file / unsupported_format / unknown_platform / xlsx_*`；真值 code 字段与测试双重锁定，新码先改 `_file_code_from_detail` + 真值。
- **K13（M2 新增）B1 候选口径**：行级三态一致率（77 行 status+code 全对齐）；字段级 P/R 拆分与 B2–B4 在 M4；门槛 `bench_b1_row_f1_min=0.95` 是数据（规则包 `bench_thresholds`），缺失即 InputError。

## 四、本机环境坑（只写实测过的）

- **`py` 不用 `python`**：本机 `python` 是商店占位符（exit 49 无输出）；跑脚本一律 `py -X utf8`（3.8.8 与 3.12.10 双通道，`py -0p` 可见）。
- **pip 无代理直连失败（DNS getaddrinfo failed）**：用默认系统代理 + 清华镜像 `-i https://pypi.tuna.tsinghua.edu.cn/simple`（不要 `NO_PROXY="*"`）。
- **venv 可执行文件用相对形式** `./.clean-venv/Scripts/<name>.exe`（Git Bash）。
- **测试约定**：`PYTHONDONTWRITEBYTECODE=1` 全程（含 pip install）；子进程测试显式 `encoding="utf-8"`（conftest 已封装）；子进程环境必须**继承父环境**（纯手工 env dict 在 3.8 触发崩溃）。
- **stdin heredoc 传中文给 `py` 会炸（M2 实测）**：`py - <<'EOF'` 内含中文字面量报 `SyntaxError: Non-UTF-8 code`——heredoc 内容按 locale 编码进管道。绕法：① `PYTHONUTF8=1 py - <<'EOF'`；② 中文内容放临时文件再执行；③ 用 Edit/Write 工具直接改文件（推荐）。
- **变异验证时未跟踪文件没有 git 恢复通道（M2 实测）**：`git checkout --` 只救已跟踪文件；ingest/ 这类新目录变异后用**精确备份恢复**（`cp x x.bak` → 变异 → `cp x.bak x` → **立即删 bak 并跑全量确认恢复**）。M2 曾因恢复错备份把 parsers 内容复制进 importer，靠 Write 工具整文件重写恢复——变异验证一律"单文件备份、变异、恢复、当场跑全量"一气呵成。
- **pytest 8.x capsys 字段名是 `.out/.err`**（不是 `.stdout/.stderr`，M2 实测 3.12 通道 pytest 8.4.2）。
- Git Bash `rm -rf` 目录被占用（CWD 停在该目录内时）：换到目录外再删。

## 五、DoD 逐项 checklist（M2，已验证）

- [x] `ingest/` 五子模块落盘；`import` 子命令实装（ledger.json + 行级/文件级问题清单）
- [x] 三平台 × CSV/XLSX 样例（含形态矩阵全集）导入可复跑：真值 77 行三态逐条对齐（4 文件级 invalid + 7 行级 invalid + 1 unknown 行 + 1 unknown 列全命中）
- [x] 三态矩阵落测试；invalid 绝不入库 / unknown 入库且 issues 显式（变异验证过"unknown 静默会红"）
- [x] 编码探测顺序（BOM→UTF-8→GB18030→失败报错）有正/反向样例（UTF-8 中文在 GB18030 下"能解"的反向样例锁定顺序；顺序反转变异会红）
- [x] XLSX 读取器覆盖度声明（sharedStrings/压缩/多 sheet/坏 zip/非 inlineStr → 显式错误码；压缩门变异会红）
- [x] B1 导入基准**候选实现**接 bench 骨架：真引擎 F1=1.0 ≥ 门槛 0.95（门槛读规则包）；探活可证伪（坏引擎注入必报未达标）
- [x] 退出码契约：`import` 0/1/2 锁进测试；占位期望翻转注明期望变更（test_cli_stubs）
- [x] 变异验证 ×6 全部变红、恢复后全绿
- [x] `check_frozen.py` 全绿（v2 资产）；`selftest` 5 PASS / 0 PENDING / 0 FAIL
- [x] 双解释器 95 passed ×2；干净 venv 重建 95 passed + `brc import` 三退出码冒烟
- [x] plan/00·04·05·06 回写；`plan/HANDOFF-M3.md` 落盘（本文件）
- [x] commit（工作树干净）；CI 同 M0：本地等价校验（未接远端，CI 待首推验证）

## 六、关键命令速查

```bash
cd <仓库根>
py -0p                                   # 摸清解释器通道
PYTHONDONTWRITEBYTECODE=1 py -3.8 -X utf8 -m pytest -q    # 3.8 全量（95 passed）
PYTHONDONTWRITEBYTECODE=1 py -3.12 -X utf8 -m pytest -q   # 3.12 全量（95 passed）
py -X utf8 tools/check_frozen.py                          # 冻结资产全量守门（全绿）
py -X utf8 tools/check_frozen.py --ledger                 # sha256 台账（对 data/README §六）
py -X utf8 -m bill_reconciler selftest                    # 5 PASS / 0 PENDING / 0 FAIL
# 可演示（M2）
py -X utf8 -m bill_reconciler import data/samples/wechat-demo-01.csv --out ledger.json   # exit 0
py -X utf8 -m bill_reconciler import data/samples/wechat-demo-02.csv --out ledger.json   # exit 1 + 行级清单
py -X utf8 -m bill_reconciler import data/samples/wechat-demo-bad-encoding.csv --out ledger.json  # exit 2
# 干净 venv（3.12 通道 + 清华镜像；不要加 NO_PROXY）
py -3.12 -m venv .clean-venv
PYTHONDONTWRITEBYTECODE=1 ./.clean-venv/Scripts/python.exe -m pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple
PYTHONDONTWRITEBYTECODE=1 ./.clean-venv/Scripts/python.exe -m pytest -q
./.clean-venv/Scripts/brc.exe import data/samples/wechat-demo-01.csv --out ledger.json
```

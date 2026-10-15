# plan/HANDOFF-M4.md — M3 → M4 交接快照

> 用法：新对话以绝对路径读取本文件（启动命令由用户侧拼接，本文件内一律相对路径）。
> 写入时间：2026-10-15（M3 收尾）。**M4 开工后本文件仅作历史快照**。

## 一、当前进度 + 证据

**M3「归一化 + 去重 + 语义识别」已完成**（2026-10-15，单对话完成 params 单点 + 三模块 + 零参数字面量门禁 + run 编排 + 收尾验证）。

| 交付物 | 证据 |
|---|---|
| `params.py` | 规则包唯一访问点：`load_rules_package()`（manifest/aliases/keywords 三件加载 + 结构校验，缺字段/类型不符 → InputError）；`Params.get()`（缺失即 InputError，绝不内联默认值）；`RulesPackage.digest`（三件 sha256 聚合，进产物 `meta.params_digest` 与 run 摘要）；`param_tokens()`（门禁 token 集运行时生成，一位数豁免） |
| `normalize.py` | `AliasIndex.normalize()`：动作序列写死（去空白[含内部]→全半角映射表→后缀剥离[剥离后非空才生效]→别名表命中）；**variants 先过同一归一管线再入索引**；逐条依据 `{rule,detail,evidence}`；未命中 `actions==[]`；纯函数（同输入同输出测试锁定）；`normalize_ledger()` 追加 `normalized_counterparty`/`normalize_actions` + 台账段 |
| `dedup.py` | 三元组（金额字符串精确相等 + |Δt|≤W 闭区间 + 归一对手方）+ 同方向分组；链式相邻聚类（A-B 近 B-C 近 A-C 远 → 同簇，span 落依据）；**跨平台前提**（≥2 平台 `duplicate_cross_platform`；同平台 `candidate_same_platform` 显式不合并、成员照常计净额）；代表笔（时间最早→平台优先级→行号，三键各有测试）；`--window-seconds` 覆盖进产物参数块；方向缺失（unknown 行）不参与聚类 |
| `classify.py` | priority 升序（同优先级 id 升序）+ 方向条件（不符即跳过）+ 全部命中条目记录（`all_hits`）+ **未知一等**（`no_match` 依据、绝不 fallthrough 为消费）；干扰例（支出方向"退款"词、张三转账）不误判有专测 |
| `lint_params.py` | 零参数字面量门禁：token 集运行时从规则包生成（扫描器零词面）；整词命中（长数字串不误报）；注释行仅"例/如/默认"举例语气豁免；params.py 豁免自身；`selftest` 常驻检查项（6 PASS）；阳性对照 = tmp 注入式测试（注入 token 必红） |
| `pipeline.py` + CLI | `run_pipeline()`（import→normalize→dedup→classify 内存编排，`meta.params_digest`/`ruleset_version`/`pipeline.stages` 落产物）；CLI `normalize/dedup/classify/run` 四子命令实装（分段命令与 run 共用同一实现）；退出码 0/1/2 与 import 同语义 |
| 真值对齐 | expect_dedup **5 簇全对齐**（C1–C4 cross + S1 same_platform，代表笔逐簇对）+ **5 对 must_not_merge 全不合并**；expect_semantic **67 行全对齐**；B1 基准 v3 规则包下 F1=1.0 + 探活可证伪（复跑确认） |
| 测试 | `tests/test_normalize.py` 11 / `test_dedup.py` 13（含窗口 Δt=W 命中 / W+1s 不命中 / 差 1 分 / 窗内不同额 / 链式 / 代表笔三键 / 确定性）/ `test_classify.py` 9 / `test_pipeline_cli.py` 9（run 退出码 + window 覆盖 + 三段链）/ `test_no_param_literals.py` 4；双解释器全量 **136 passed**（3.8.8 / 3.12.10）|
| 变异验证 ×8 | 窗口闭→开区间红 / 未知 fallthrough→消费红 / 方向条件失效红 / 后缀空串守门失效红 / 去空白禁用红 / 门禁 token 集置空红 / 跨平台前提失效红 / run 退出码门失效红；每处恢复后 136 passed |
| 规则包 v3（K8 勘误） | M1 产物 keywords **漏登记订阅类商户**（真值 18 个 SUB-* 消费行无规则可命中）→ `gen_rules.py` v3：新增 R53（健身月卡/视频会员/音乐会员/云盘会员，priority 50）、R30 notes 补"报销款"口径；ruleset_version 2→3；`check_frozen.py` 全绿；52 项 M1/M2 测试无翻转全过；**data/README §六 sha256 台账需 M4 开工核对回填**（v3 后 rules 三件字节已变） |
| selftest | 6 PASS / 0 PENDING / 0 FAIL（新增"参数字面量门禁"项） |

## 二、下一棒待办（M4 基准 + 报告，细节见 plan/05 M4 节与 plan/03 §五/§九）

1. `bench/`（或 `bench_runner.py` 扩展）：B2 去重 / B3 语义 / B4 订阅三套件接入（B1 已在）；**门槛全部读规则包**（`bench_thresholds`：`bench_b2_cluster_accuracy_min=0.95` / `bench_b2_false_positive_max=0` / `bench_b3_label_accuracy_min=0.98` / `bench_b4_f1_min=0.9`——值随包下发，勿在代码复制）；每套件**探活可证伪**（注入缺陷必报未达标）；`--only` 未知名 exit 2；
2. 样本驱动/规则驱动**分层**：M3 的规则驱动边界测试在 tests；M4 的 B2 双向对账（窗口边界推导端点 vs 粗扫+细扫穷举恢复）接进 bench；
3. `report/`：单一渲染源（`sections.py` 结构化章节）→ 单文件 HTML + `report_data.json` 同源双轨；章节按 plan/03 §5.2（含参数来源块：digest + 每参数值/来源/覆盖状态）；**同输入同字节**（无时间戳、固定排序、固定数值格式）配位级守门；0 外链断言；隐私门禁（无网络库 import）+ 运行期无外连断言；
4. `run` 编排补 report（①→⑤ 全链）+ `bench` 子命令实装（stubs 测试再翻转，注明期望变更）；
5. 订阅识别（模块⑤）：`subscription_min_repeats` / `period_table`（monthly 30±2 / quarterly 91±3 / yearly 365±5）/ `price_change_min_percent` 参数均已在包内；真值 `expect_subscription` 段已备（6 形态：月付/涨价/季付/年付/中断/非周期干扰）；
6. M4 收尾：DoD 验证 → plan/00·05·06 回写 → HANDOFF-M5 → commit。

## 三、既定口径清单（动了会打挂测试/基准；K 编号沿用，新增 K14–K16）

- **K1 退出码契约 0/1/2/3**：import/run/normalize/dedup/classify 均已按最终语义锁定（0 干净 / 1 行级问题 / 2 文件级失败与用法，`tests/test_import_cli.py` + `tests/test_pipeline_cli.py`）；占位余 report/bench（exit 2，M4 实装后照此翻转并注明）。
- **K2 selftest 三态**：6 PASS / 0 PENDING / 0 FAIL（M3 新增门禁项后计数 5→6）；新检查项保持"PENDING 不冒充通过"。
- **K3 数据目录解析**：环境变量（无效不回落）→ CWD 向上；不在测试里 chdir 后直调 `main()`。
- **K4 编码守卫**：入口 `cli.main` 与每个 `tools/` 脚本先 `_ensure_utf8_stdio()`；M3 新增 CLI 输出沿用 cli 入口现有守卫（normalize/dedup/classify/run 有中文 stdout，勿绕过 main）。
- **K5 冻结产物 `-text`**：`data/{samples,truth,rules}/**` 禁动；**rules 三件现为 v3 字节**，`data/README.md §六` 台账 sha256 待 M4 开工核对回填（`tools/check_frozen.py --ledger` 若红即台账滞后）。
- **K6 元数据测试双态**：未安装通道 skip / 安装通道实跑，是同一套件合法两态。
- **K7 决策记录唯一台账 = plan/00 §二**；P1–P6 拍板项仍待用户结案。
- **K8 生成器确定性**：splitmix64（seed 20261015）、禁 stdlib random / set 迭代序 / 时钟；**生成器现为 v3**（rules v3 + samples v2）；改生成逻辑 = 版本号++ + 整目录重生成 + `--check` 全绿 + 台账回填一并提交。
- **K9 真值只存期望**：expect_import / expect_semantic / expect_dedup / expect_subscription 四段；无 observed 字段门禁在位；expect_import（77 行）、expect_dedup（5 簇+5 反例）、expect_semantic（67 行）现已被 M2/M3 引擎全量消费——**改任何期望都要先过对应对齐测试**。
- **K10 形态常量集 = 覆盖度分母**：`tools/gen_samples.py::FORM_IDS`（导入 27 / 语义 8 / 去重 8 / 订阅 6）。
- **K11 unknown 列 vs 登记非语义列**：`locate.PLATFORM_EXPECTED_COLUMNS` 是登记全集；unknown_column 只报全集之外。
- **K12 行级问题码清单**：`amount_missing / amount_not_numeric / time_unparseable / column_count_mismatch / amount_ambiguous / unmapped_direction` + 文件级码族；新码先改 `_file_code_from_detail` + 真值。
- **K13 B1 候选口径**：行级三态一致率（77 行 status+code 全对齐）；门槛 `bench_b1_row_f1_min=0.95` 是数据。
- **K14（M3 新增）参数单点 = params.py**：任何引擎/报告/基准需要参数值一律 `load_rules_package()` 或 `Params.get()`；**禁止内联默认值**（缺失即 InputError 是特性不是缺陷——规则包缺参数 = 配置错误 exit 2）；`import_files` 的 header_k/max_scan_lines 现已缺省走规则包（M2 的默认值 2/20 已删）。
- **K15（M3 新增）零参数字面量门禁扫描面**：`bill_reconciler/` 包内 .py（含 docstring/注释）；**新增模块若需引用参数值只能经 params.py**；豁免口径：params.py 自身 + 一位数 + 注释行举例语气（"例/如/默认"）；**报告/基准模块落包内后自动入扫描面**（写代码时别把阈值/窗口值硬写进去，selftest 会红）。
- **K16（M3 新增）分段命令与 run 同一实现**：normalize/dedup/classify 子命令与 run_pipeline 共用 pipeline 层函数；M4 的 report 接入同样走 pipeline（新增 stage），别做第二份编排。

## 四、本机环境坑（只写实测过的；沿用 M2 清单 + M3 新增两条）

- **`py` 不用 `python`**：跑脚本一律 `py -X utf8`（3.8.8 与 3.12.10 双通道）；pip 走系统代理 + 清华镜像（不要 `NO_PROXY="*"`）。
- **venv 可执行文件用相对形式** `./.clean-venv/Scripts/<name>.exe`（Git Bash）。
- **测试约定**：`PYTHONDONTWRITEBYTECODE=1` 全程；子进程测试显式 `encoding="utf-8"`（conftest 已封装）；pytest 8.x capsys 字段名是 `.out/.err`。
- **stdin heredoc 传中文给 `py` 会炸**：`py - <<'EOF'` 内含中文字面量报 `Non-UTF-8 code`——绕法：① `PYTHONUTF8=1 py - <<'EOF'`（M3 实测有效）；② 中文内容放临时文件；③ 用 Edit/Write 工具直接改文件（推荐）。
- **M3 新增：py -X utf8 heredoc 内的 `\n` 转义**：`-c` 一行式里含 `\n` 字面量的中文替换容易锚不中——变异验证改用"按行号定位 + `split('\n')` 替换"（见 M3 变异脚本写法），比正则稳。
- **M3 新增：变异验证恢复后必须跑全量**（136 passed 确认）；单文件备份放 `/tmp`、恢复后立即删 bak（M2 教训仍有效）。
- Git Bash `rm -rf` 目录被占用（CWD 停在该目录内时）：换到目录外再删。
- pytest 汇总行在 Git Bash 管道尾部偶尔丢——先 `> file` 落盘再 `cat`（M3 实测）。

## 五、DoD 逐项 checklist（M3，已验证）

- [x] `params.py` 唯一访问点落盘（加载校验/Params/digest/token 集）；引擎零内联参数值（import_files 默认值已删，缺省走规则包）
- [x] `normalize.py`：动作序列写死 + 逐条依据 + 未命中依据为空 + 纯函数（11 项测试）
- [x] `dedup.py`：三元组 + 链式相邻聚类 + 跨平台前提 + 同平台候选显式不合并 + 代表笔三键（13 项测试；真值 5 簇 + 5 反例全对齐）
- [x] `classify.py`：priority/方向条件/全命中记录/未知一等（9 项测试；真值 67 行全对齐）
- [x] 规则驱动边界测试（窗口 ±1s / 金额 1 分 / 链式聚类；不读真值库）
- [x] 零参数字面量门禁：0 违规 + 阳性对照注入必红 + selftest 常驻项（6 PASS）
- [x] `run` 编排前三段 + 分段子命令同一实现；退出码 0/1/2 锁测试（9 项）
- [x] 规则包 v3 勘误（R53 订阅商户）走 K8 全流程；`check_frozen.py` 全绿
- [x] 变异验证 ×8 全部变红、恢复后全绿
- [x] 双解释器 136 passed ×2（3.8.8 / 3.12.10）；干净 venv（3.12 editable）136 passed + `brc run`/`brc selftest` 双形态冒烟
- [x] plan/00·03·05·06 回写；`plan/HANDOFF-M4.md` 落盘（本文件）
- [x] commit（工作树干净）；CI 同 M0：本地等价校验（未接远端，CI 待首推验证）
- [ ] **M4 开工第一件事**：`py -X utf8 tools/check_frozen.py --ledger` 对 `data/README.md §六`——rules v3 后台账若滞后即回填（K5）

## 六、关键命令速查

```bash
cd <仓库根>
py -0p                                   # 摸清解释器通道
PYTHONDONTWRITEBYTECODE=1 py -3.8 -X utf8 -m pytest -q    # 3.8 全量（136 passed）
PYTHONDONTWRITEBYTECODE=1 py -3.12 -X utf8 -m pytest -q   # 3.12 全量（136 passed）
py -X utf8 tools/check_frozen.py                          # 冻结资产全量守门（全绿）
py -X utf8 tools/check_frozen.py --ledger                 # sha256 台账（对 data/README §六）
py -X utf8 -m bill_reconciler selftest                    # 6 PASS / 0 PENDING / 0 FAIL
# 可演示（M3）
py -X utf8 -m bill_reconciler run data/samples/wechat-demo-01.csv data/samples/alipay-demo-01.csv data/samples/bank-demo-01.csv data/samples/wechat-demo-03.xlsx data/samples/bank-demo-03.xlsx --out ledger-full.json   # exit 0（净流水+语义分布+未知区间+参数 digest）
py -X utf8 -m bill_reconciler run data/samples/bank-demo-01.csv --out ledger-full.json    # exit 1（行级问题清单）
py -X utf8 -m bill_reconciler run data/samples/wechat-demo-bad-encoding.csv --out ledger-full.json  # exit 2
py -X utf8 -m bill_reconciler dedup --ledger ledger-full.json --window-seconds 0 --out l.json  # 窗口覆盖
# 干净 venv（3.12 通道 + 清华镜像；不要加 NO_PROXY）
py -3.12 -m venv .clean-venv
PYTHONDONTWRITEBYTECODE=1 ./.clean-venv/Scripts/python.exe -m pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple
PYTHONDONTWRITEBYTECODE=1 ./.clean-venv/Scripts/python.exe -m pytest -q
./.clean-venv/Scripts/brc.exe run data/samples/wechat-demo-01.csv --out ledger-full.json
```

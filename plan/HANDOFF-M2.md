# plan/HANDOFF-M2.md — M1 → M2 交接快照

> 用法：新对话以绝对路径读取本文件（启动命令由用户侧拼接，本文件内一律相对路径）。
> 写入时间：2026-10-15（M1 收尾）。**M2 开工后本文件仅作历史快照**。

## 一、当前进度 + 证据

**M1「数据先行」已完成**（2026-10-15，单对话完成三生成器 + 冻结资产 + 守门测试 + 回写）。

| 交付物 | 证据 |
|---|---|
| 冻结规则包 | `data/rules/{manifest,keywords,aliases}.json`（gen_rules.py v1；参数 8 项 + 基准门槛 5 项 + 关键词规则 7 条 + 别名表/后缀白名单/全半角映射，全部标注"经验默认（非官方）"） |
| 合成样例 + 真值台账 | `data/samples/` 12 件（微信 CSV×2+XLSX+坏编码、支付宝 CSV×2+空+仅表头、银行 CSV×2+XLSX+缺列）+ `data/truth/truth.json`（gen_samples.py v1，seed 20261015，同源同运行） |
| 守门入口 | `tools/check_frozen.py`（全量 `--check` → `FROZEN_ALL_OK`；`--only` 未知名 exit 2；`--ledger` 打印 sha256 台账） |
| 公共件 | `tools/_frozen_common.py`（编码守卫 / splitmix64 / 规范化 JSON / 确定性 XLSX writer：`ZIP_STORED`+`create_system=0`+`date_time=(1980,1,1,...)`） |
| 守门测试 | `tests/test_frozen_assets.py` 22 项：双通路 `--check` 位级一致、**变异验证**（沙箱手改入库件必报 DRIFT）、无 `observed` 字段门禁、覆盖度分子=分母、期望引用完整性（无悬空 row_id）、白名单/卡号黑名单（13~19 位数字禁）、XLSX 结构断言、生成器源码静态扫描（禁 random/时钟） |
| selftest 翻转 | 数据资产两 PENDING → PASS（`tests/test_selftest.py` 期望翻转并注明"期望变更"）；实测 `py -X utf8 -m bill_reconciler selftest` → 5 PASS / 0 PENDING / 0 FAIL |
| 台账回填 | `data/README.md §六`（16 件 sha256 + 生成器 + seed + 复核方式）；plan/00·04·05·06 回写完成 |
| 测试 | 双解释器全量 **52 passed**（3.8.8 / 3.12.10）；干净 venv 重建（3.12 + editable）后 52 passed |

**M1 实测勘误（已回写 plan/04 §二）**：货币符号按样例编码通道取值（GBK 无法编码 U+00A5 → 用 U+FFE5），形态语义不变。

## 二、下一棒待办（M2 解析层，细节见 plan/05 M2 节与 plan/03 §一）

1. `bill_reconciler/ingest/`：编码探测（BOM→UTF-8 严格→GB18030→失败报错，顺序写死）+ 表头定位（K=2、上限 20 行，来自 manifest）+ 列名别名映射（keywords/aliases 同源规则包）+ 三平台解析器 + 自写 XLSX 读取器；
2. `import` 子命令实装：`brc import <文件...> --out ledger.json`，产出 IR（plan/03 §〇）+ 行级/文件级问题清单；
3. 退出码契约落测试：文件级失败（坏编码/表头未定位/缺必填列/空文件）exit 2；行级问题（金额非数值/空/时间不可解析/列数不匹配）清单化且 exit 1 语义在 run 编排后再锁（M2 先锁 import 的 2/0/3）；`unknown` 列（如 alipay-demo-02 的"商户编号"）入 issues 不拒行；
4. 三态矩阵测试：`tests/` 逐样例回归（真值 `expect_import` 是唯一期望来源——含 4 个文件级 invalid 样例 + 7 个行级 invalid + 1 个 unknown 行 + 1 个 unknown 列）；
5. B1 导入基准**候选实现**接 bench 骨架（正式达标与探活在 M4）；
6. 编码守卫扩展到 ingest 模块；XLSX 读取器覆盖度声明（不支持特性 → 显式错误码，不猜测）；
7. M2 收尾：DoD 验证 → plan/00·05·06 回写 → HANDOFF-M3 → commit。

## 三、既定口径清单（动了会打挂测试/基准；K 编号沿用）

- **K1 退出码契约 0/1/2/3**（plan/02 §4.5）：占位命令仍 exit 2（`tests/test_cli_stubs.py`）；M2 实装 import 后按最终语义翻转期望并注明。
- **K2 selftest 三态**：M1 起数据资产 PASS（`tests/test_selftest.py` 已翻转并注明）；新增资产检查项时保持"PENDING 不冒充通过"纪律。
- **K3 数据目录解析**：环境变量（无效不回落）→ CWD 向上；无"包位置"支。注意：进程内 selftest 测试依赖 CWD=仓库根（子进程夹具已固定），不要在测试里 chdir 后直调 `main()`。
- **K4 编码守卫**：入口 `cli.main` 与每个 `tools/` 脚本先 `_ensure_utf8_stdio()`；新模块沿用。
- **K5 冻结产物 `-text`**：`data/{samples,truth,rules}/**` 与 `*.xlsx` 禁动；sha256 台账在 `data/README.md §六`（truth.json = `35ee581c…`，M2 勘误 v2 重生成后的现值），`check_frozen.py --ledger` 可复核。
- **K6 元数据测试双态**：未安装通道 skip / 安装通道实跑，是同一套件合法两态。
- **K7 决策记录唯一台账 = plan/00 §二**；P1–P5 拍板项仍待用户结案。
- **K8（M1 新增）生成器确定性**：splitmix64（seed 20261015）、禁 stdlib random / set 迭代序 / 时钟（静态扫描测试锁）；XLSX writer 固定元数据；改生成逻辑 = 版本号++ + 整目录重生成 + `--check` 全绿一并提交。
- **K9（M1 新增）真值只存期望**：`expect_import / expect_semantic / expect_dedup / expect_subscription` 四段；观测字段门禁在 `tests/test_frozen_assets.py::test_truth_has_no_observed_fields`（含 json 键与自由文本两层扫描）。
- **K10（M1 新增）形态常量集 = 覆盖度分母**：`tools/gen_samples.py::FORM_IDS`（导入 27 / 语义 8 / 去重 8 / 订阅 6）；增形态先改这里，生成器缺失注入会在构建期抛错。

## 四、本机环境坑（只写实测过的）

- **`py` 不用 `python`**：本机 `python` 是商店占位符（exit 49 无输出）；跑脚本一律 `py -X utf8`（3.8.8 与 3.12.10 双通道，`py -0p` 可见）。
- **pip 无代理直连失败（DNS getaddrinfo failed）**：用默认系统代理 + 清华镜像 `-i https://pypi.tuna.tsinghua.edu.cn/simple`（不要 `NO_PROXY="*"`）。
- **Git Bash `rm -rf` 目录被占用**（CWD 停在该目录内时）：换到目录外再删。
- **venv 可执行文件用相对形式** `./.clean-venv/Scripts/<name>.exe`（Git Bash）。
- **测试约定**：`PYTHONDONTWRITEBYTECODE=1` 全程（含 pip install）；子进程测试显式 `encoding="utf-8"`（conftest 已封装 `run_cli`/`run_tools` 夹具）；子进程环境必须**继承父环境**（M1 踩坑：纯手工 env dict 在 3.8 触发 `_Py_HashRandomization_Init` 崩溃）。
- `.clean-venv/` 已在 .gitignore（隔离验证用，不入库）。
- **GBK 样例的坑**：GBK 通道编码不了 U+00A5，生成器按 `encoding` 通道选货币符号（plan/04 §二勘误）；解析器侧需把 U+00A5 与 U+FFE5 都列入货币符号白名单。

## 五、DoD 逐项 checklist（M1，已验证）

- [x] 三生成器落盘；`data/rules` 3 件 + `data/samples` 12 件 + `data/truth` 1 件全部程序化产出
- [x] `check_frozen.py` 全绿（FROZEN_RULES_OK / FROZEN_SAMPLES_OK / FROZEN_ALL_OK）；`--only` 未知名 exit 2；`--ledger` 与 data/README §六台账一致
- [x] 两次运行位级一致（进程内 build 纯函数 + 子进程 `--check` 双通路；XLSX 结构断言）
- [x] 形态矩阵全注入（27/8/8/6，分子=分母）；"未知"注入存在性断言
- [x] 真值无 observed 字段门禁；期望引用完整性（去重簇/反例对/订阅条目 row_id 全部可解析；代表笔 ∈ 簇成员；跨平台簇 ≥2 平台）
- [x] 白名单/卡号黑名单自检（生成器构建期 + 测试双层）
- [x] 变异验证：沙箱手改 keywords.json / wechat-demo-01.csv → `--check` 非 0 且点名文件
- [x] `selftest` 数据资产 PASS（测试翻转注明期望变更）
- [x] 双解释器 52 passed ×2；干净 venv 重建 52 passed；`brc selftest` 安装通道冒烟
- [x] `plan/HANDOFF-M2.md` 落盘（本文件）
- [x] commit（工作树干净）；CI 同 M0：本地等价校验（未接远端，CI 待首推验证）

## 六、关键命令速查

```bash
cd <仓库根>
py -0p                                   # 摸清解释器通道
PYTHONDONTWRITEBYTECODE=1 py -3.8 -X utf8 -m pytest -q    # 3.8 全量（52 passed）
PYTHONDONTWRITEBYTECODE=1 py -3.12 -X utf8 -m pytest -q   # 3.12 全量（52 passed）
py -X utf8 tools/check_frozen.py                          # 冻结资产全量守门（全绿）
py -X utf8 tools/check_frozen.py --ledger                 # sha256 台账（对 data/README §六）
py -X utf8 -m bill_reconciler selftest                    # 5 PASS / 0 PENDING / 0 FAIL
# 干净 venv（3.12 通道 + 清华镜像；不要加 NO_PROXY）
py -3.12 -m venv .clean-venv
PYTHONDONTWRITEBYTECODE=1 ./.clean-venv/Scripts/python.exe -m pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple
PYTHONDONTWRITEBYTECODE=1 ./.clean-venv/Scripts/python.exe -m pytest -q
./.clean-venv/Scripts/brc.exe selftest
```

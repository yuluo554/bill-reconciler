# plan/RELEASE-M6.md — M6 发布留档（三件套之一）

> 写入时间：2026-10-15。口径：**只写实测到的**；未跑项留 ⬜ 并说明原因。
> 交接依据：`plan/HANDOFF-M6.md`；发布形态：`plan/06 §五 P6`（确定性源码 zip + sha256 台账）。

## 一、脱敏四步核查（工作树 / 历史 / 产物 / 提交元数据）

| 步骤 | 实测内容 | 结论 |
|---|---|---|
| 工作树 | `git status` 0 变更；全仓扫描无个人邮箱（qq/gmail/163/outlook 等模式）、无 `ASUS` 出现于 plan/ 之外 | ✅ 干净 |
| 历史 | `git log --all` 作者=提交者身份唯一且均为 `yuluo554 <282769740+yuluo554@users.noreply.github.com>`（GitHub noreply）；历史路径全在预期根（data/plan/tools/tests/bill_reconciler/.github + 顶层配套文件），无 private/secret/.env/key 类路径；无 >200KB 大 blob（无产物误入历史）；`git fsck` 干净、无 stash、无其他分支。**提交数不写死**：以 `git rev-list --count HEAD` 现取（首推轮 = 8） | ✅ 干净，**无需历史重写**（先三连核对后核查，核对见 §二） |
| 产物 | 磁盘上 `full38.log`/`full312.log`/`.clean-venv`/`egg-info`/`.pytest_cache` 均被 .gitignore 覆盖未入追踪面；CLI 默认输出名（`ledger*.json` / `report*.html|json`）已加入 .gitignore 精确路径；发布 zip 以 `git ls-files` 追踪面为准，未追踪文件不入包 | ✅ 干净 |
| 提交元数据 | 邮箱核查如上（noreply）；提交日期 2026-10-15 当天，与开发时间线一致 | ✅ 干净 |

## 二、历史 = 工作树三连核对（动历史前）

`git status --porcelain` = 0 条（工作树干净）。**计数口径式表述**（不写死数字，防随提交漂移）：`git log --oneline` 与 `git rev-list --count HEAD` 现取一致（首推轮两者同为 8；发布收尾轮 HEAD=`3043130` 时为 10）。工作树干净、无未推送分叉，**历史无重写需求**。

## 三、建仓首推 + CI 四矩阵首跑（逐条对账）

- 建仓：`gh repo create yuluo554/bill-reconciler --public --source=. --remote=origin --push` → 仓库创建成功（https://github.com/yuluo554/bill-reconciler）；首次 `git push` 网络瞬断（github.com:443 直连间歇失败，本机无代理在跑：注册表 ProxyEnable=0、7897 端口无监听），**第 1 次重试成功**，远端 HEAD = `55a8db0c…` 与本地一致。
- CI 首跑：**一次全绿，零失败、零诊断轮**（交接文档预警"编码/平台差异可能一次爆发"——未发生）：

| Job | 结论 | 用时 |
|---|---|---|
| py3.8 / ubuntu-latest | ✅ success | 25s |
| py3.8 / windows-latest | ✅ success | 1m04s |
| py3.12 / ubuntu-latest | ✅ success | 11s |
| py3.12 / windows-latest | ✅ success | 36s |

- 逐条对账：push 事件数 1（8 个提交随首推同批上去，非 8 次推送）= run 数 1；run head_sha `55a8db0c259db620103af0150a1e3113eb33254d` 对 `git log` HEAD 一致；conclusion = success。注解仅 Node.js 20 弃用警告（actions v4/v5 强制跑 Node 24，非本仓代码问题）与 ubuntu-latest 迁移预告，不构成失败。
- `fetch-depth` 复核：ci.yml 使用 checkout@v4 默认浅检（depth=1）。仓库无历史扫描类守门测试（测试均为资产/逻辑面），CI 步骤不依赖历史，**维持默认即可**，不改。

## 四、确定性源码 zip + sha256 台账（P6 默认形态）

- 打包器：`tools/make_release_zip.py`（M6 新增）。确定性口径：`ZIP_STORED`（不压缩，消除压缩库版本差异）+ `git ls-files` 排序条目（`core.quotepath=off` 保中文路径）+ 固定 date_time `2026-10-15 00:00:00` + 固定外部属性 0644。
- **包外件（自指排除，2026-10-16 审计修复）**：本文档 `plan/RELEASE-M6.md` 记录**发布 zip 自身的 sha256**——若把它打进 zip，则"文件内容依赖 zip 摘要、zip 摘要又依赖文件内容"构成**自指**，任何真值都无法自洽（实测：改动本文件 → 打包 sha256 必变）。故打包器**恒定排除**本文件（detached checksum 惯例：校验和是包外件）。被排除件仍在 git 树内（tag/仓库可完整复核），发布物可复核性不受影响。守门测试 `tests/test_release_zip.py`（确定性 + 排除 + 打包面=追踪面−排除项，三断言；变异验证：去掉排除项必红）。
- **两次打包逐字节一致**（G18 打包确定性子门 ✅）：由 `tests/test_release_zip.py::test_packer_deterministic_two_runs_byte_identical` 常驻锁定，sha256 现取一致。
- **台账（发布附件为本体）**：

| 文件 | 大小（B） | sha256 |
|---|---|---|
| bill-reconciler-0.1.0.zip（发布附件） | 见下节回填 | 见下节回填 |

> **sha256 自指处置说明**：发布附件的 sha256 由**打包动作本身决定**，无法在"同一份被包入 zip 的文件"里写死一个恒成立的值。因此本表**不写死一个会自指的常量**——最终 sha256 以 §五/§六 的**实测回填行**为准（打包后回填，随发布提交固化），并以 GitHub Release 附件 digest（`gh release view` 的 `digest` 字段）作为**权威外部核验点**。下载方复验：`gh release view v0.1.0 --json assets` 取 digest，与本文件 §五 实测行比对。

## 五、Release + tag

- tag `v0.1.0` 打在**最终收尾提交**（2026-10-16 审计修复后的 HEAD，见 §八 实测行；该提交 CI 四矩阵全绿）。**重打说明**：原 tag 指向 `7549949`（早于收尾提交 `3043130`，两者非祖孙关系），导致发布物本体自述"M6 未完成"——本次修复把全部回填做完后，**删旧 tag、在最终提交上重打 `v0.1.0`**（见 §八）。
- 附件：bill-reconciler-0.1.0.zip（与本地打包同基线；**sha256 实测值见 §八**，下载后对 §四/§八 核验）。
- Release：https://github.com/yuluo554/bill-reconciler/releases/tag/v0.1.0（Notes 含 sha256 与解压即用指引）。

## 六、发布物本体验证（下载 → sha256 → 中立目录解压 → selftest）

实测（2026-10-16，中立目录与本仓无路径关联；**逐条结论见 §八**）：

1. `gh release download v0.1.0` → 下载附件；`sha256sum` 与 §八 实测值一致 ✅；
2. 解压 → `py -X utf8 -m bill_reconciler selftest` → **6 PASS / 0 PENDING / 0 FAIL，exit 0**（数据目录解析到解压目录内，符合"解压即用"声明）✅；
3. 追加冒烟：`run` 三平台样例 `--report` → exit 1（既定语义：检出 invalid 问题行），HTML + JSON 产物齐 ✅；`bench` → exit 0 ✅。

## 七、gh release view 核验

`gh release view v0.1.0 --json isDraft,assets,tagName` → **draft=false + 附件在列 + 附件 `digest`（sha256）与 §八 实测值一致** ✅（实测 JSON 见 §八）。

CI 对账：每轮 push 事件 run 数与 push 数一致、conclusion=success、run head_sha 对 git log 一致（实测 run id 与 head_sha 见 §八）。

## 八、收尾固化（已执行）

- README：状态行转"**v0.1.0 已发布**（M0–M6 六个里程碑全部完成）"+ 快速开始新增发布 zip 下载指引（方式一/方式二）。
- 缓议项结案：plan/06 §五 P1–P6 全部按默认执行结案（P2 以 M6 建仓变体结案，理由见该表）；决策回写 plan/00 §二。
- plan 终态回写：plan/00（文档索引/承诺台账/里程碑表）、plan/05（M6 状态行 + DoD）、plan/06（G15/G17/G18 + §五）。
- 网络坑留档：本机无代理在跑（ProxyEnable=0），github.com 直连间歇失败（curl 与 git 同 IP 时通时断），push/tag/release 均以"失败后间隔重试"通过。

### 8.1 2026-10-16 发布后审计修复（本轮实测回填）

> 触发：独立审计发现 tag 早于收尾提交、发布物本体自述 M6 未完成、plan/06 未回填、版本戳不一致、发布留档计数漂移、门禁残余面未登记。逐条修复见下表。

| # | 缺陷 | 修复动作（文件） | 依据证据 | 验证结果 |
|---|---|---|---|---|
| 1 | tag 早于收尾提交 + 发布 zip 自述 M6 未完成 | 全部回填后重打包 + 删旧 tag + 重打 `v0.1.0` + 换 Release 附件（`.gitignore`/`plan/*`/`tools/make_release_zip.py`/`tests/*`） | `git merge-base --is-ancestor 7549949 3043130` 为假；tag 树内 plan/05 M6 行仍"⬜ 待开工"、README 仍"M5 完成" | 见 8.2 实测行 |
| 2 | plan/06 §一四行 + G12 未回填 | 按实测回填 ✅（`plan/06-交付对标.md`） | B1–B4 全绿（`bench` exit 0）+ `tests/test_report.py` no-network 双断言绿 | 双解释器 184 passed |
| 3 | 版本戳不一致（plan/00 索引标 plan/03"v2"、头部实为"v1"） | 逐份核对索引 vs 头部，plan/03 头部对齐 v2（`plan/00`·`plan/03`） | 逐份比对：仅 plan/03 不一致，其余已一致 | 见 8.3 |
| 4 | RELEASE-M6 §二/§五 计数不自洽（8 vs 第 9 个提交） | 改口径式表述，避免随提交漂移（`plan/RELEASE-M6.md`） | §二原写"log=8/rev-list=8"而 §五称 tag 在第 9 个提交 | 口径式，不再漂移 |
| 5 | 门禁残余面未登记（3 个一位数真口径参数不在 token 集） | plan/03 §七 + `params.py` docstring 显式登记 + 新增兜底测试（`plan/03`·`params.py`·`tests/test_param_caliber_fallback.py`） | `param_tokens` 只收两位及以上；实测残余面 = {min_repeats, interval_tolerance, header_locate_k} | 5 项测试绿 + 4 处变异必红 |
| 6 | plan/01 缺覆盖度锚 | §四补"覆盖度口径以 plan/04 §三与 truth.json coverage 为准"（`plan/01-题目文档.md`） | 该口径原只在 plan/04 §三与 truth.json | 文档一致 |

**附带修复（审计外发现，理由见 8.4）**：发布 zip 与发布留档**自指**（RELEASE-M6 在包内又记录包自身 sha256）→ 打包器恒定排除该文件；新增 `tests/test_release_zip.py` 三断言守门（`tools/make_release_zip.py`）。

### 8.2 发布面实测（2026-10-16）

- 双解释器全量：`py -3.8 -m pytest` / `py -3.12 -m pytest` → **184 passed ×2**（基线 176 + 新增 8：`test_param_caliber_fallback.py` 5 项 + `test_release_zip.py` 3 项）。
- `bench`：exit 0（B1–B4 全达标）；`bench --probe`：四套件探活全红（可证伪）✅。
- `tools/check_frozen.py`：`FROZEN_ALL_OK` exit 0；`selftest`：6 PASS exit 0；参数字面量门禁：0 违规。
- 确定性打包：同一工作树打包三次 sha256 **逐字节一致**（见下表）。
- tag：`v0.1.0` 指向**本留档所在提交**（`git rev-list -n1 v0.1.0` 现取指向含本文件的收尾提交；旧 tag 指向 `7549949` 已删，重打在收尾提交）。**不写死提交 hash**——本文件在 tag 所指提交内，写死自身 hash 会构成自指（同 §8.4 理由）。
- Release 附件：`bill-reconciler-0.1.0.zip`，大小 **648,022** B，sha256 `75720111305f446ed99bf5157c92f60de612623441ce2910a2672cf48b16bf57`（= `gh release view` 的 `digest`）。
- CI：每轮 push 事件数 = run 数、conclusion=success、head_sha 对 git log 一致（实测 run id / head_sha 见 8.2.1）。

| 文件 | 大小（B） | sha256 |
|---|---|---|
| bill-reconciler-0.1.0.zip（v0.1.0 发布附件，收尾提交基线） | 648,022 | `75720111305f446ed99bf5157c92f60de612623441ce2910a2672cf48b16bf57` |

#### 8.2.1 CI 逐条对账（2026-10-16）

| run id | head_sha | event | conclusion |
|---|---|---|---|
| 38877947416 | `9b8b241…`（收尾提交的 tag push 轮） | push（tag v0.1.0） | success |
| 38877674755 | `9b8b241…`（收尾提交的 main push 轮） | push（main） | success |
| 38876939651 | `72576c5…`（审计修复轮第二次推送） | push | success |
| 38876608338 | `d3300d4…`（审计修复轮首次推送） | push | success |
| 38749702074 | `3043130…`（M6 收尾） | push | success |
| 38748966833 | `7549949…`（v0.1.0 原 tag 轮） | push | success |
| 38748687709 | `7549949…`（M6 发布面） | push | success |
| 38747091247 | `55a8db0…`（M5 交付面） | push | success |

push 事件数 = run 数（含 tag push），每轮 conclusion=success，head_sha 与本地 git log 逐条一致。**本表最后一轮（`9b8b241` 的 tag push）的 run id 无法在本文档内写死**——本文档即该提交内容，写死会构成自指；该轮 run 亦为 success，以 `gh run list` 现取为准。**收敛说明**：审计修复期间每补一次留档即产生一次提交，tag 随之重打，属"文档-提交-打 tag"的正常迭代；末次打 tag 后即停（不再追加会改动留档的提交），故 tag 指向与留档内容收敛于同一提交。

#### 8.2.2 发布物本体验证（下载 → sha256 → 中立目录解压 → selftest/bench/run，2026-10-16）

实测（中立目录 `%TEMP%\m6verify`，与本仓无路径关联）：

1. `gh release download v0.1.0` → 附件 `bill-reconciler-0.1.0.zip`，`sha256sum` = `7572011…16bf57`、648,022 B，与 §8.2 台账一致 ✅；
2. `gh release view v0.1.0 --json isDraft,tagName,assets` → `isDraft=false`、`tagName=v0.1.0`、附件 `digest=sha256:7572011…16bf57`（与本地打包逐字节一致）✅；
3. 中立目录解压 → `py -X utf8 -m bill_reconciler selftest` → **6 PASS / 0 PENDING / 0 FAIL，exit 0**（数据目录解析到解压目录内，符合"解压即用"）✅；
4. 冒烟：`bench` → exit 0 ✅；`run` 三平台样例 `--report` → exit 1（既定语义：检出问题行），`v.html` + `v.json` 产物齐 ✅。
5. 包内文档为发布态：解压包内 `README.md` 状态行 = "v0.1.0 已发布（M0–M6 全部完成 + 审计修复注记）"；包内 `plan/05` M6 行 = "✅ 完成"；包外 `plan/RELEASE-M6.md`（tag 树内）§五 = 重打说明、§八 = 修复实测 ✅。

### 8.3 版本戳核对（逐份索引 vs 头部，2026-10-16）

| 文档 | plan/00 索引 | 头部 | 处置 |
|---|---|---|---|
| plan/00 | v2 | v2 | 一致 |
| plan/01 | v1 | v1（`> **题目版本**：v1`） | 一致 |
| plan/02 | v1 | v1 | 一致 |
| plan/03 | v2 | **v1 → v2** | **修正头部为 v2**（索引原已标 v2，头部漏改；M3 回写确实发生） |
| plan/04 | v1 | v1 | 一致 |
| plan/05 | v1 | v1 | 一致 |
| plan/06 | v1 | v1 | 一致 |
| data/README | v2 | 无版本号（按"基准日 + §六回填"口径） | 不适用（无头部版本号，索引标 v2 指 §六追加轮） |

结论：全库仅 plan/03 一处索引/头部不一致，已对齐；其余逐份核对一致。

### 8.4 附带修复理由（发布 zip 自指）

审计要求"重新打包 → 两次 sha256 逐字节一致 → RELEASE-M6 台账写 sha256"。但**本留档文件自身在 zip 包内**：若在包内的 RELEASE-M6.md 里写死 zip 的 sha256，则形成 `sha256(zip) = f(RELEASE-M6.md 内容) = f(sha256(zip))` 的**自指**，任何值都无法自洽（实测：改动该文件 → 打包 sha256 必变，故包内不可能存在恒等台账）。两条路：

- **A（已采用）**：打包器恒定排除 `plan/RELEASE-M6.md`（detached checksum 惯例）——校验和是包外件，不随包内容变化；留档在 git 树内完整可复核，Release 附件 digest 作为权威外部核验点。**优点**：打包确定性真正成立（同一提交两次打包必一致），复验链闭合。
- **B（未采用）**：把台账写进包内并反复"改值→重打→再改"迭代到不动点——**不可能收敛**（改一次值 zip 就变一次）。

故取 A。若审计方要求"包内必须含留档"，替代方案是把留档拆成"包内不含 sha 的正文"+"包外 `SHA256SUMS` 附件"——但那与 A 等价（校验和仍在包外），本仓选更简单的 A。

## 九、v0.1.1 发布（2026-10-20，元数据与卫生迭代）

> 触发：外部诊断（`update/00-诊断报告.md`）指出三条缺陷——license 元数据已弃用（含 setuptools
> 2027-02-18 硬期限）、非 editable 安装下 `selftest` 退出码与 README 契约冲突、CI 全部用
> `*-latest` 且 actions 版本触发 Node 20 弃用注解。本轮为**纯元数据 / 退出码 / CI 卫生**迭代，
> **不碰对账、去重、语义识别逻辑，不碰冻结数据，B1–B4 门槛未动**。

### 9.1 用户拍板的决策

| 决策 | 选项 | 内容 |
|---|---|---|
| DEC1 | **A** | 解释器 floor **保持 `>=3.8`**（CI 维持 4 组合，classifiers 五档不动） |
| DEC2 | **A** | 非 editable 安装下 `selftest` **改为 exit 3**，与 `bench` / README 退出码表一致 |
| DEC3 | **B** | 升 actions 大版本 + **Python 3.8 两腿钉到 `ubuntu-22.04`** |
| 版本策略 | **A** | `__version__` `0.1.0 → 0.1.1`，新 tag `v0.1.1` + 新 Release；**`v0.1.0` 与其附件保留不动** |
| 发布通道 | **A** | 分支 → PR → CI 四矩阵全绿 → `--merge` 进 main → 在合并后提交打 tag |

### 9.2 改动清单（受版本控制）

| 文件 | 动作 |
|---|---|
| `pyproject.toml` | `license = "MIT"` + `license-files = ["LICENSE"]`；删 MIT classifier；`setuptools>=61 → >=77` |
| `bill_reconciler/selftest.py` | 数据目录不可用 → `return EXIT_ENV`（3）；docstring 补第三态；复用 `datadir.ENV_VAR` |
| `bill_reconciler/__init__.py` | `__version__ = "0.1.1"` |
| `tests/test_selftest.py` | `test_selftest_flags_invalid_data_dir` 期望 1 → **3**（改值不删用例，附期望变更注） |
| `tests/test_release_zip.py` | zip 顶层前缀改为**现取** `__version__`，不再硬编码版本 |
| `tools/make_release_zip.py` | 新增 `_package_version()`，zip 顶层目录名跟随 `__version__` |
| `.github/workflows/ci.yml` | checkout@v4→**v7**、setup-python@v5→**v7**；加 `permissions`/`concurrency`；矩阵改显式 `include`，3.8 腿钉 `ubuntu-22.04` |
| `README.md` | 状态行转 v0.1.1；退出码 `3` 行补"`selftest` 与 `bench` 一致"；发布 zip 名改 0.1.1 |
| `CHANGELOG.md` | **新增**（v0.1.1 / v0.1.0 两节） |

删除：仓库根 `full312.log` / `full38.log`（未跟踪、已 ignore、内容是过期 `176 passed` 快照）。

### 9.3 实测台账

| 项 | v0.1.0（改前） | v0.1.1（改后） |
|---|---|---|
| 测试 | 184 passed | **184 passed**（`--collect-only` 亦 184，零增减） |
| selftest（仓库根 editable） | 6 PASS / 0 PENDING / 0 FAIL，exit 0 | **同左，exit 0** |
| bench | B1–B4 达标，exit 0 | 同左，exit 0 |
| bench --probe | 四套件探活通过（0.1039 / 0.4286 / 0.9403+violations=4 / 0.8889） | 同左，exit 0 |
| 元数据 warning（setuptools 84.0.0） | **3 条** `SetuptoolsDeprecationWarning` | **0 条**（`WARNINGS: []`） |
| METADATA license 字段 | `License: MIT` + MIT classifier | `License-Expression: MIT` + `License-File: LICENSE` |
| 非 editable `selftest`（中立 cwd） | `2 PASS / 2 PENDING / 2 FAIL`，**exit 1** | 单行 `未找到 data/ 目录…`，**exit 3** |
| 非 editable `bench`（中立 cwd） | exit 3 | exit 3（不变） |
| wheel | 73,562 B / 32 条目 / data 0 | **73,838 B / 32 条目 / data 0**（+276 B 全来自 METADATA） |
| Release 附件 sha256 | `75720111305f446ed99bf5157c92f60de612623441ce2910a2672cf48b16bf57` | 见 §9.5 |

### 9.4 一处既有行为（改前就有，本轮未改）

中立 cwd + **有效** `BILL_RECONCILER_DATA` 时，`selftest` 走到"参数字面量门禁"会报
`错误：扫描根不存在：bill_reconciler` → **exit 2**。根因：`lint_params._SCAN_ROOTS` 是相对路径，
只在仓库根可用；改前因数据目录先失败而不可达。**已用 HEAD 源码独立构建 wheel 复现同一条**，
确认与本轮改动无关。是否改为"扫描根不可用 → 3"留待后续决策。

### 9.5 v0.1.1 发布物

| 文件 | 大小（B） | sha256 |
|---|---|---|
| bill-reconciler-0.1.1.zip | 见 §9.6 回填 | 见 §9.6 回填（打包后回填；本文件在包外，故不构成自指） |

`v0.1.0` 的 tag 与附件**保持原样**（648,022 B / `7572011…16bf57`），历史复验链不受影响。

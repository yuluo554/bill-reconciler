# plan/RELEASE-M6.md — M6 发布留档（三件套之一）

> 写入时间：2026-10-15。口径：**只写实测到的**；未跑项留 ⬜ 并说明原因。
> 交接依据：`plan/HANDOFF-M6.md`；发布形态：`plan/06 §五 P6`（确定性源码 zip + sha256 台账）。

## 一、脱敏四步核查（工作树 / 历史 / 产物 / 提交元数据）

| 步骤 | 实测内容 | 结论 |
|---|---|---|
| 工作树 | `git status` 0 变更；全仓扫描无个人邮箱（qq/gmail/163/outlook 等模式）、无 `ASUS` 出现于 plan/ 之外 | ✅ 干净 |
| 历史 | `git log --all` 全 8 提交，作者=提交者身份唯一且均为 `yuluo554 <282769740+yuluo554@users.noreply.github.com>`（GitHub noreply）；历史路径全在预期根（data/plan/tools/tests/bill_reconciler/.github + 顶层配套文件），无 private/secret/.env/key 类路径；无 >200KB 大 blob（无产物误入历史）；`git fsck` 干净、无 stash、无其他分支 | ✅ 干净，**无需历史重写**（先三连核对后核查，核对见 §二） |
| 产物 | 磁盘上 `full38.log`/`full312.log`/`.clean-venv`/`egg-info`/`.pytest_cache` 均被 .gitignore 覆盖未入追踪面；发布 zip 以 `git ls-files` 追踪面为准，未追踪文件不入包 | ✅ 干净 |
| 提交元数据 | 邮箱核查如上（noreply）；提交日期 2026-10-15 当天，与开发时间线一致 | ✅ 干净 |

## 二、历史 = 工作树三连核对（动历史前）

`git status --porcelain` = 0 条；`git log --oneline` = 8；`git rev-list --count HEAD` = 8。三者一致，工作树干净、无未推送分叉，**历史无重写需求**。

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

- 打包器：`tools/make_release_zip.py`（M6 新增）。确定性口径：`ZIP_STORED`（不压缩，消除压缩库差异）+ `git ls-files` 排序条目（`core.quotepath=off` 保中文路径）+ 固定 date_time `2026-10-15 00:00:00` + 固定外部属性 0644。
- **两次打包逐字节一致**：sha256 `b3f5f51c90e5438a7551f28b5b05ca199e8fedf07649ab742e7d69faf635f4a6` 两次相同（G18 打包确定性子门 ✅）。
- 台账（发布附件为本体）：

| 文件 | 大小（B） | sha256 |
|---|---|---|
（注：§四首次实测基于 55a8db0 打包面（89 条目，sha256 `b3f5f51c…f4a6`）；**发布附件以收尾提交 7549949 的打包面为准**（91 条目，含打包器与发布留档），两次打包 sha256 逐字节一致，见下。）

| 文件 | 大小（B） | sha256 |
|---|---|---|
| bill-reconciler-0.1.0.zip（发布附件，7549949 基线） | 634,967 | `30c95fdec8d47eca966b64a38b655b7f5107b0bf9ac13137f7134ba07c96f92a` |

## 五、Release + tag

- tag `v0.1.0` 打在 CI 绿的收尾提交 `7549949`（M6 收尾提交，含打包器与发布留档；该提交 CI 四矩阵全绿）。
- 附件：bill-reconciler-0.1.0.zip（与本地打包同基线，下载后 sha256 对 §四台账核验）。
- Release：https://github.com/yuluo554/bill-reconciler/releases/tag/v0.1.0（Notes 含 sha256 与解压即用指引）。

## 六、发布物本体验证（下载 → sha256 → 中立目录解压 → selftest）

实测（2026-10-15，中立目录 `D:\ProgramData\zcodeelease-verify-m6`，与本仓无路径关联）：

1. `gh release download v0.1.0` → 下载附件；`sha256sum` = `30c95fde…f92a`，与 §四台账一致 ✅；
2. 解压 → `py -X utf8 -m bill_reconciler selftest` → **6 PASS / 0 PENDING / 0 FAIL，exit 0**（数据目录解析到解压目录内，符合"解压即用"声明）✅；
3. 追加冒烟：`run` 三平台样例 `--report` → exit 1（既定语义：检出 4 条 invalid 问题行），`v.html` + `v.json` 产物齐 ✅；`bench` → exit 0 ✅。

## 七、gh release view 核验

`gh release view v0.1.0 --json isDraft,assets,tagName` → `{"isDraft": false, "tagName": "v0.1.0", "assets": [{"name": "bill-reconciler-0.1.0.zip", "size": 634967}]}`：**draft=false + 附件在列 + 大小与本地一致** ✅。

CI 对账补充（收尾提交轮）：run 数 2、每轮 conclusion=success、head_sha 分别 55a8db0c… / 7549949e… 对 git log 全一致；tag v0.1.0 所指提交 7549949 的 CI 为全绿轮。

## 八、收尾固化（已执行）

- README：状态行转"**v0.1.0 已发布**（M0–M6 六个里程碑全部完成）"+ 快速开始新增发布 zip 下载指引（方式一/方式二）。
- 缓议项结案：plan/06 §五 P1–P6 全部按默认执行结案（P2 以 M6 建仓变体结案，理由见该表）；决策回写 plan/00 §二。
- plan 终态回写：plan/00（文档索引/承诺台账/里程碑表）、plan/05（M6 状态行 + DoD）、plan/06（G15/G17/G18 + §五）。
- 网络坑留档：本机无代理在跑（ProxyEnable=0），github.com 直连间歇失败（curl 与 git 同 IP 时通时断），push/tag/release 均以"失败后间隔重试"通过，共 3 处重试成功（首推 1 次、7549949 推送 6 次后成功、其余一次成）。

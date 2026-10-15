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
| bill-reconciler-0.1.0.zip | 待上传后回填 | `b3f5f51c90e5438a7551f28b5b05ca199e8fedf07649ab742e7d69faf635f4a6` |

## 五、Release + tag

- tag `v0.1.0` 打在 CI 绿的收尾提交（M6 收尾提交，含打包器与发布留档）。
- 附件：bill-reconciler-0.1.0.zip（与本地打包同基线，下载后 sha256 对 §四台账核验）。
- 核验：`gh release view` draft=false + 附件在列；结果见 §七。

## 六、发布物本体验证（下载 → sha256 → 中立目录解压 → selftest）

⬜ 待 Release 附件上传后执行（方法复用 plan/verify 干净环境法，但以 zip 本体为准）。

## 七、gh release view 核验

⬜ 待执行。

## 八、收尾固化

⬜ 待执行：README 状态行转正（M6 完成）、缓议项结案（P1–P6 按默认执行）、plan/00·05·06 终态回写、HANDOFF 归档说明。

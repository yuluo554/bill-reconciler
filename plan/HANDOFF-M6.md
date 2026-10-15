# plan/HANDOFF-M6.md — M5 → M6 交接快照

> 用法：新对话以绝对路径读取本文件（启动命令由用户侧拼接，本文件内一律相对路径）。
> 写入时间：2026-10-15（M5 收尾）。**M6 开工后本文件仅作历史快照**。

## 一、当前进度 + 证据

**M5「交付面」已完成**（2026-10-15，单对话完成三面交叉守门 + 干净环境逐条验证 + 性能实测 + README 定稿）。

| 交付物 | 证据 |
|---|---|
| `tests/test_readme_gate.py` | **三面交叉守门**（G13）5 项：① README 命令/旗标 → CLI 真实注册表（`build_parser()` 反射，逐行关联旗标防张冠李戴；`--help` 豁免）② CLI 子命令 → README 反向覆盖（含命令总表提及行）③ tests/ 全部 import（AST 从严收集，含函数内）→ 落点四分法（冻结名单 stdlib / dev extra / 本包 / tools 注入模块；**stdlib 名单冻结名单制，不用 `sys.stdlib_module_names`**——3.8 空集假红）④ README 安装行 extras → pyproject 声明（含"扫描面非空"自证断言）⑤ packages.find include → 真实包布局（含 report 子包在位 + data/tools 不入包） |
| 变异验证 ×5 | README 假旗标 `--quantum` 红 / 注册表伪造 `futurecmd` 红 / 测试注入 `import pandas` 红 / README extras 注入 `[dev,gui]` 红 / packages.find 改 `other_pkg*` 红；每处恢复后全绿。**面3 首版正则被引号截断 = 假门（变异后仍绿）——按"修探针不放宽断言"修复并加非空自证** |
| 干净环境逐条验证 | 新目录 clone（8271ab8）+ 全新 venv（`py -3.12 -m venv`）按 README 逐字命令 7 条全过，**逐条记录退出码语义**：selftest=0 / run（8 样例 --report）=**1（检出 4 未知行=既定语义，产物三件齐）** / bench=0 / bench --only NOPE=**2** / `brc bench`=0 / `bill-reconciler selftest`=0 / `python -m pytest`=171 passed。留档 `plan/verify/README.md` §一 |
| 性能实测 | 三平台各 12,000 行（合计 **36,000 行** ≈2.8MB，表头/广告行与冻结样例同形态，GBK 通道 U+FFE5）：全链 `run --report` **≈5.5s（3.8.8 与 3.12.10 双通道一致）**。留档 `plan/verify/README.md` §二；README 已知问题节引用 |
| README 定稿 | 状态行转 M5 + 新增**「已知问题与限制」节**（非 editable 安装限制=数据目录解析刻意取舍 / python 商店占位符 / GBK 货币符号 / 性能实测数字 / 未覆盖形态显式报错不猜测）；四声明复核无漂移 |
| 测试 | 双解释器全量 **176 passed ×2**（3.8.8 / 3.12.10；171+5）+ 干净 venv 176 passed；selftest 6 PASS / 0 PENDING / 0 FAIL；`check_frozen.py` 全绿（FROZEN_ALL_OK）；bench B1–B4 全达标（双基线复跑防回退） |

## 二、下一棒待办（M6 发布，细节见 plan/05 M6 节与 plan/06 §五 P2/P6）

1. **脱敏四步**：工作树 / 历史 / 产物 / 提交元数据（git log 邮箱核查）——扫描器 token 运行时实算、零词面；历史终验三扫全 0；
2. **历史 = 工作树三连核对**（status / log / rev-list count）后再动任何历史重写；
3. **建仓首推**：`github.com/yuluo554/bill-reconciler`（gh 已登录）；CI 四矩阵首跑（**预算多轮诊断**；首推前本地等价校验已做但真实 CI 从未实跑——编码/平台差异可能一次爆发）；`fetch-depth: 0` 需求复核（历史扫描类守门）；
4. **CI 首跑按提交逐条对账**（head_sha+conclusion 对 git log；push 数=run 数）；首次失败如实记录修复提交；
5. **确定性源码 zip + sha256 台账**（P6 默认形态）：`ZIP_STORED` + 条目排序 + 固定 date_time，两次打包逐字节一致；Release 附件上传后 `gh release view` 核验（draft=false + 附件在列）；
6. **tag 打在 CI 绿的收尾提交上**；README 下载指引；
7. **发布留档 `plan/RELEASE-M6.md`**：只写实测到的，未跑项留 ⬜ 说明原因；干净环境验证复用 plan/verify 方法但**以发布 zip 本体**为准（下载 → sha256 → 中立目录解压 → selftest）；
8. 收尾固化：README 状态行转正、缓议项清零（plan/06 §五 P1–P6 待拍板项找用户结案或显式"按默认执行"）、plan/00·05·06 终态回写。

## 三、既定口径清单（动了会打挂测试；K 编号沿用 M4 快照，新增 K20–K21）

- **K1–K19**：全部沿用 `plan/HANDOFF-M5.md` §三（退出码契约 / selftest 三态 / 数据目录 / 编码守卫 / 冻结产物 / 参数单点 / 订阅口径 / 报告确定性 / B2 探针等，均未变动）。
- **K20（M5 新增）三面交叉守门 = `tests/test_readme_gate.py`**：README 命令/旗标与 CLI 注册表双向锁死；tests import 落点四分法（**stdlib 冻结名单制**——tests 新 import 名单外的标准库要把它加进 `_STDLIB` 集合，这与 lint_params token 集同理是判定词表不是参数值）；README extras ↔ pyproject 声明双向；改 README/CLI/pyproject/tests import 任何一面都要让此文件保持绿。
- **K21（M5 新增）干净环境验证留档 = `plan/verify/README.md`**：M6 发布验证**追加**新记录到该目录，不覆盖 M5 记录（发布物本体验证是新增章节）；`run` 对 8 样例 exit 1 是既定语义（检出未知行），逐条留档时必须写"符合声明"而非"全 0"。

## 四、本机环境坑（只写实测过的；沿用 M4 清单 + M5 新增一条）

- M4 清单全部有效（`py -X utf8` / venv 相对路径 / pytest 落盘再 grep / heredoc 中文 / Git Bash `/` 参数转写 / 变异后全量复跑 / 假门三问）。
- **M5 新增：`Path.write_text(newline=)` 是 3.10+**——3.8 上用 `open(..., "w", newline="\n")` 或 `write_bytes`（本轮变异脚本实测踩中；与 crash-loop-rescue 记载一致）。
- 干净 venv 装包：`py -3.12 -m venv` 一次成；`python -m pip install -e .`（核心零依赖）秒装，`.[dev]` 走清华镜像正常。

## 五、DoD 逐项 checklist（M5，已验证）

- [x] 干净目录 clone + 全新 venv 按 README 逐条一次跑通（退出码语义逐条留档 plan/verify/README.md §一）
- [x] 三面交叉守门落地（tests/test_readme_gate.py 5 项；变异验证×5 全红、恢复全绿；含假门修复）
- [x] 双形态命令冒烟（python -m / brc / bill-reconciler）干净环境全过
- [x] 已知问题节定稿（README「已知问题与限制」；非 editable 限制如实写明）
- [x] 性能实测（36k 行 ≈5.5s 双通道；留档 + README 引用）
- [x] README 状态行转 M5；四声明复核
- [x] 双解释器 176 passed ×2 + 干净 venv 176 passed；selftest 6/0/0；check_frozen 全绿；bench 双基线复跑达标
- [x] plan/00·05·06 回写；`plan/HANDOFF-M6.md` 落盘（本文件）
- [x] commit（工作树干净）；CI 同前：本地等价校验（未接远端，CI 待首推验证）

## 六、关键命令速查

```bash
cd <仓库根>
py -0p                                   # 3.8.8 + 3.12.10 双通道
PYTHONDONTWRITEBYTECODE=1 py -3.8 -X utf8 -m pytest tests/ -p no:cacheprovider   # 176 passed
PYTHONDONTWRITEBYTECODE=1 py -3.12 -X utf8 -m pytest tests/ -p no:cacheprovider  # 176 passed
py -X utf8 tools/check_frozen.py          # FROZEN_ALL_OK
py -X utf8 -m bill_reconciler selftest    # 6 PASS / 0 PENDING / 0 FAIL
py -X utf8 -m bill_reconciler bench       # exit 0
# 干净环境复现（M5 方法，plan/verify/README.md §一）：
git clone --no-hardlinks . ../clean-m6-verify && cd ../clean-m6-verify
py -3.12 -m venv .venv && ./.venv/Scripts/python.exe -m pip install -e ".[dev]"
./.venv/Scripts/python.exe -m pytest tests/ -p no:cacheprovider    # 176 passed
# M6 首推对账：
gh run list --repo yuluo554/bill-reconciler   # push 数 = run 数，按 head_sha 配对
```

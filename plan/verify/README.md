# plan/verify/ — M5 干净环境验证与性能实测留档

> 写入时间：2026-10-15（M5 交付面收尾）。本目录只留**记录**，不留大产物
> （性能实测的合成文件与 run 产物已按方法可随时重生成，不入库）。

## 一、干净环境逐条验证（新目录 clone + 全新 venv，2026-10-15 实测）

环境：`D:\ProgramData\zcode\clean-m5-verify`（`git clone --no-hardlinks` 自 8271ab8）；
venv：`py -3.12 -X utf8 -m venv .venv`（本机 `python` 是商店占位符，用 py 启动器——README 已注明此坑）；
安装：README 逐字命令 `python -m pip install -e .`（核心零第三方依赖，秒装）+ `.[dev]`（pytest 9.1.1）。

| # | README 命令（逐字） | 退出码 | 语义判定 |
|---|---|---|---|
| 1 | `python -m bill_reconciler selftest` | 0 | 6 PASS / 0 PENDING / 0 FAIL ✅ 符合声明 |
| 2 | `python -m bill_reconciler run <8个样例> --out ledger-full.json --report --report-html report.html --report-json report_data.json` | **1** | **符合声明**：run 检出 4 个未知行 → "完成但检出需人工处理的问题（清单必打印）"（K1）；产物三件齐（ledger 158,534B / report.html 8,102B / report_data.json 22,634B） |
| 3 | `python -m bill_reconciler bench` | 0 | B1–B4 全达标（F1=1.0 / acc=1.0 / acc=1.0 / F1=1.0）✅ |
| 4 | `python -m bill_reconciler bench --only NOPE` | **2** | 用法与未知名 ✅ 符合声明 |
| 5 | `brc bench`（console script） | 0 | 与 python -m 同结果 ✅ 双形态等价 |
| 6 | `bill-reconciler selftest` | 0 | 第二个 console script 名 ✅ |
| 7 | `python -m pytest`（装 `.[dev]` 后） | 0 | **171 passed**（与开发机一致）✅ |

三面交叉守门（`tests/test_readme_gate.py`，M5 新增）确保此表不腐化：
README 命令/旗标 → CLI 注册表、CLI 子命令 → README、tests import → 安装面落点、
README extras → pyproject 声明、packages.find → 真实包布局。变异验证 ×5 全红
（含首版面 3 正则被引号截断的假门——按"修探针不放宽断言"修复，并加"扫描面非空"自证）。

## 二、性能实测（2026-10-15）

- 数据：三平台各 12,000 行（合计 **36,000 行**，约 2.8 MB；表头/广告行与冻结样例同形态，
  GBK 通道货币符号用 U+FFE5——与 data/README 台账同一坑位口径）；
- 命令：`run ... --report --report-html --report-json`（全链 ①→⑤ 含报告双轨）；
- 结果：**3.12.10 ≈ 5.5–5.8 s；3.8.8 ≈ 5.4 s**（多次取值稳定）；
- 附注：该数据商户不在白名单 → 语义分布未知=36000，走的是"归一化 miss + 未知一等"
  的重路径；去重候选簇 0（时间戳无同秒三元组）。
- 重生成方法：见本文件第二节命令（生成器脚本约 40 行，三平台表头见
  `bill_reconciler/ingest/locate.py::PLATFORM_EXPECTED_COLUMNS`）。

结论：数万行级输入在秒级完成，无性能悬崖；README「已知问题」节如实记录。

## 三、已知问题清单（README「已知问题与限制」节的底稿）

1. **非 editable 安装限制**：包数据（data/ 规则包、样例）不随包分发——本工具按
   "数据目录解析"（环境变量 → CWD 向上）定位 `data/`，因此**只支持仓库内运行或
   `pip install -e .`（editable）**；`pip install .`（非 editable）后脱离仓库目录运行
   会因找不到规则包而 exit 3。这是刻意取舍（冻结资产以仓库为唯一真源）。
2. **Windows `python` 商店占位符**：README 已注明用 `py` 替代。
3. **GBK 通道货币符号**：微信 GBK 导出中 ¥ 为 U+FFE5（全角形），解析器两种形态都认
   （U+00A5 / U+FFE5）；生成器按编码通道选形（data/README 台账）。
4. **性能**：36k 行 ≈ 5.5 s（实测见上节）；更大体量未测。
5. **CI 未接远端**：CI 工作流文件在位（四矩阵），本地等价校验（双解释器 171 passed ×2 +
   干净 venv）已做；**真实 CI 首跑待 M6 首推验证**（诚实口径，非已发生事实）。

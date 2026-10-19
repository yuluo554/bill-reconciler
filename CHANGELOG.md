# 变更记录

本文件记录对外可见的行为与元数据变更。版本号以 `bill_reconciler.__version__` 为唯一真源。

## v0.1.1 — 2026-10-20

元数据现代化 + 退出码口径自洽 + CI 卫生。**不涉及对账 / 去重 / 语义识别的任何逻辑变更**，
冻结数据（`data/rules/**`、`data/samples/**`、`data/truth/**`）逐字节未动，B1–B4 门槛未动。

### 变更

- **license 改用 SPDX 表达式**：`license = {text = "MIT"}` → `license = "MIT"`，
  并新增 `license-files = ["LICENSE"]`，删除已弃用的 `License :: OSI Approved :: MIT License`
  classifier。生成的元数据由 `License: MIT` 变为 `License-Expression: MIT` + `License-File: LICENSE`。
  构建期 `SetuptoolsDeprecationWarning` 由 **3 条降为 0 条**（原警告含 setuptools 的
  2027-02-18 硬期限）。
- **`build-system` 下限**：`setuptools>=61` → `setuptools>=77`（PEP 639 SPDX 字符串所需）。
- **`selftest` 退出码**：数据目录解析失败/不存在时返回 **3**（环境不可用），此前返回 1
  （"检出需人工处理的问题"）。与 `bench` 及 README 的退出码契约一致；此时只打印单行错误，
  不再输出整张全 FAIL 的检查清单。**仓库根正常路径仍为 6 PASS / exit 0，不变**。
- **打包器**：`tools/make_release_zip.py` 的 zip 顶层目录名改为现取 `__version__`，
  不再硬编码版本号（`tests/test_release_zip.py` 同步改为现取）。

### 工程 / CI

- CI actions：`actions/checkout@v4 → @v7`、`actions/setup-python@v5 → @v7`（消除 Node 20 弃用注解）。
- CI 新增 `permissions: contents: read` 与 `concurrency`（同 ref 并发取消）。
- CI 矩阵改为显式 `include` 四行，**Python 3.8 两腿钉到 `ubuntu-22.04`**，规避
  `ubuntu-latest` 自 2026-10-19 起迁移 Ubuntu 26 的不确定性；3.12 腿仍跑 `ubuntu-latest`。

### 兼容性

- `requires-python` **保持 `>=3.8`**，classifiers 五档不变。
- 退出码四态定义（0/1/2/3）不变；仅 `selftest` 开始正确使用既有的 `EXIT_ENV`。
- 包结构与打包声明不变（wheel 仍 32 条目、包在包内、无 package-data）。

### 已知限制（与 v0.1.0 相同）

- 规则包与样例是仓库内冻结数据，**不随 wheel 分发**。`pip install .`（非 editable）后脱离
  仓库目录运行会因找不到规则包退出：`bench` 与 `selftest` 均返回 **3**。这是刻意取舍。

## v0.1.0 — 2026-10-15

首个公开发布：M0–M6 六个里程碑完成。CLI 八个子命令（`import` / `normalize` / `dedup` /
`classify` / `report` / `run` / `bench` / `selftest`）全部实装；内置基准 B1–B4 全绿；
单文件 HTML 报告；纯本地、零上传、零第三方运行时依赖、不使用 LLM。

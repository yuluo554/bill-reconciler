# tools/ — 生成器与守门（开发/发布工具，不进用户安装面）

本目录脚本**不随包安装**：它们是仓库开发工具，一律**在仓库根目录**运行：

```bash
python tools/<name>.py     # Windows 上如 python 为商店占位符，用 py tools/<name>.py
```

规划（M1 起逐步落盘，见 plan/04-数据计划.md）：

| 脚本 | 用途 | 里程碑 |
|---|---|---|
| `gen_samples.py` | 合成账单 + 真值台账（同源生成；`--check` 位级守门） | M1 |
| `gen_rules.py` | 冻结规则包：参数包 / 语义关键词表 / 商户别名表（`--check`） | M1 |
| `check_frozen.py` | 全量 `--check` 守门入口（重跑全部生成器逐字节比对） | M1 |
| `make_release.py` | 确定性发布 zip + sha256 台账 | M6 |

纪律（写入每个脚本）：

- 仅用标准库；入口先执行编码守卫（与 `bill_reconciler.cli` 同款）；
- 确定性：禁 stdlib `random`、禁 `set` 迭代序、禁系统时钟；固定 seed；
- 库内文档一律相对路径；真实账单数据永不入库（`.gitignore` 的 `_private/`）。

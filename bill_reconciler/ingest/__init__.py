"""模块① 多平台账单导入（ingest）。

子模块分工（plan/03 §一）：

- ``detect``：编码探测（BOM → UTF-8 严格 → GB18030 → 文件级失败，顺序写死）；
- ``locate``：表头定位（前 N 行内命中预期列名数 ≥ K，参数来自冻结规则包）；
- ``columns``：列名别名映射（keywords/aliases 同源规则包；未登记列 → unknown）；
- ``parsers``：三平台行级解析器（金额归一 / 收支分列 / 三态判定）；
- ``xlsx_reader``：自写最小 XLSX 读取器（只支持本项目 writer 产出的 inlineStr 形态，
  不支持特性显式报错码，不猜测）；
- ``importer``：编排入口 ``import_files()`` → IR（ledger）+ 问题清单。

纪律：规则优先、全程确定（无启发式/模糊匹配）；行级问题清单化绝不静默；
原始行（raw_fields）入库起终身保留。
"""

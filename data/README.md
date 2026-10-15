# data/README.md — 依据查证与数据纪律

仓库 `10-16-bill-reconciler`（多平台账单"真实支出"对账器）。基准日：**2026-10-15**。

> **本文件是数据纪律的唯一来源**。所有依据、可获取性、合成数据规则在此登记；plan/01 与 plan/00 的相关表述均为引用，不得手写第二份口径。

## 一、依据查证记录（三态）

| # | 依据 | 三态 | 渠道与说明 |
|---|---|---|---|
| 1 | 跨平台账单去重空白（核心论据） | ⬜**软论据** | GitHub 检索式 `跨平台 账单 去重 in:name,description` → **0 结果**（`gh api search/repositories`，基准日 2026-10-15，检索式可回溯） |
| 2 | 转账识别相关仓库 | ⬜**软论据** | 检索式 `转账 识别 去重 账单` → **1 结果**（DNAlec/statement-bookkeeping，**0★**），基准日 2026-10-15 |
| 3 | 多平台账单统一相关仓库 | ⬜**软论据** | 检索式 `微信 支付宝 银行 账单 统一` → **4 结果**，最高 2402508251/all-wallet-manager（**4★**），基准日 2026-10-15 |
| 4 | 支付宝账单分析生态 | ⬜**软论据** | 检索式 `支付宝 账单 分析` → **52 结果**，头部 dtsola/xiaoyaoprivatebill（**107★**，2026-02）/ Hessel2333/alipay_record_analysis（**74★**）/ MickLife/KeepAccounts_v2.0（**309★**，停更 2023），基准日 2026-10-15 |
| 5 | 大项目区分（防误判竞品） | ⬜**软论据** | mayswind/ezbookkeeping（**5768★**）= 记账账本应用，非导入对账器；beancount（**6087★**）= 复式记账引擎。两者均不解决"多平台导出账单合并去重 + 转账语义识别" |
| 6 | **需求原话证据** | ✅**直连取证** | Tony-Liu217/FlowLens（2026-10-08 建仓）README 原文："同一笔消费可能同时出现在银行卡和支付平台账单中，本人转账、退款、AA 回款和报销也会影响对个人支出的理解" |
| 7 | **法律红线实证（两条 URL）** | ✅**实证** | ①`https://github.com/xaoyaoo/PyWxDump`（**9646★**）：**2025-10-20 已删库**，README 留《项目移除通知》+ 律师函截图；②`https://github.com/sjzar/chatlog`（**9183★**）：**同日**代码与提交历史全部移除，理由"收到微信官方函件，核心功能存在合规风险"。→ 微信/QQ **聊天记录导出**方向已被法律清除 |
| 8 | 微信账单导出摩擦实证 | ✅**先例实证** | `https://github.com/zxc7563598/php-wechat-bill-parser`（**9★**）**专做微信导出 ZIP 的密码破解**——证明"微信账单导出为带密码 ZIP"是普遍摩擦 |
| 9 | 格式解析先例（可验证） | ✅**先例存在** | `https://github.com/cxy0714/beancount-auto-bookkeeping`、`https://github.com/zxc7563598/php-wechat-bill-parser`、`https://github.com/DNAlec/statement-bookkeeping`——编码/表头广告行/千分位/收支分列已有开源先例可核对 |
| 10 | 中文分词（可选，非首期） | ✅可获取 | `https://github.com/wangfenjin/simple`（**870★**，SQLite FTS5 中文 tokenizer）。首期只做规则归并，**不引入该依赖** |
| 11 | 银行 PDF 账单模板 | ⬜**模板无穷** | 各家银行、各版本排版不同，**无法给出确定性覆盖承诺**。只声明覆盖度不承诺 100%，用合成/示例模板兜底；**不进首期 DoD** |
| 12 | 官方账单导出自助入口 | ✅**官方渠道** | 微信：我-服务-钱包-账单-常见问题-下载账单；支付宝：账单-开具交易流水证明。**本题只解析这两条官方自助出口的文件** |

**三态说明**：✅=已核对/已实证（附渠道）；⬜=软论据或待获取（附检索式+基准日或阻断原因）。**软论据不得与"官方原文直连核对"并列作硬锚点**，仅作辅助论据。

## 二、数据源可获取性记录

- **✅ 可获取（本题全部首期数据源）**：
  - **用户自行导出的账单文件**（微信解密后 CSV/XLSX、支付宝 CSV、银行 CSV/Excel）——由用户提供，工具只解析，**不需要任何联网获取**；
  - **合成账单数据**——由本项目生成器程序化产出，零外部依赖、零 API。
- **✅ 先例可核对**：格式解析要点（GBK/GB18030 编码、表头广告行、列名漂移、千分位、收支分列）有开源先例可验证（见第一节 #8/#9）。
- **⬜ 不可承诺**：银行 PDF 模板（无穷）；平台**未**提供官方自助导出之外的任何数据接口（**不碰**）。
- **法律红线实证（两条 URL，写进边界与非目标）**：
  - `https://github.com/xaoyaoo/PyWxDump`（9646★，2025-10-20 删库）；
  - `https://github.com/sjzar/chatlog`（9183★，同日移除）。
  → **聊天记录导出方向已被法律清除**。本题只解析**官方自助导出的账单文件**，**不触碰平台加密数据库、不做密钥提取/内存 dump**。
- **抓取/留档要求**：本项目**不联网获取数据**（纯本地是卖点）；合成数据与冻结产物入库须记录生成器版本与生成日期，文件只增不改（配 `-text` 防 EOL 改写字节），改需求走生成器整目录重生成 + `--check` 位级守门。

## 三、合成数据纪律

- **演示/样例数据一律合成**，禁止使用真实用户账单、真实商户、真实姓名/账号/卡号。
- **假商户名白名单**（样例账单/演示数据专用，白名单外新增须先在此登记）：
  - 餐饮/零售：`示例便利店甲`、`示例快餐乙`、`示例超市丙`、`示例咖啡丁`；
  - 订阅服务：`示例视频会员`、`示例音乐会员`、`示例云盘会员`、`示例健身月卡`；
  - 转账对象：`示例本人卡A`、`示例本人卡B`、`示例同事张三`、`示例房东李四`；
  - 其他：`示例打车平台`、`示例话费充值`、`示例医院门诊`。
- **假账单文件命名**：`wechat-demo-*.csv`、`alipay-demo-*.csv`、`bank-demo-*.csv`（见 `.gitignore` 豁免说明）。
- **假账号/卡号**：一律用白名单占位（如尾号 `****0000`），禁止真实账号形态（不得出现可识别为真实卡号的 16~19 位数字串）。
- **真实数据隔离**：用户真实账单**只在本机处理、不入仓**；任何演示/基准素材必须是生成器产出。

### 三之二、真值台账纪律（M1 核心）

**真值台账 = 程序化生成的"应去重 / 应识别为转账"标注**，不是手写期望值。

- 生成器在产出合成账单的**同一次运行**里，同步产出真值台账（JSON），逐条标注：
  - **哪几笔应被去重**（跨平台同一笔消费的簇成员，含簇内代表笔）；
  - **哪几笔应被识别为 `本人转账` / `退款` / `AA回款` / `报销`**；
  - **哪几笔应被识别为周期性订阅**（含周期与涨价记录）。
- 台账与账单**同源生成**（同一随机种子/同一生成逻辑），故标注与数据必然一致；`--check` 位级守门，**禁手改**。
- **真值库只存输入与期望，观测由基准在运行时实算**——把观测也冻进真值库，评测就退化成"比对两个冻结字典"，引擎坏掉也全绿。
- **覆盖度双登记**：合成账单必须**刻意注入每一类情形**（跨平台重复 / 同平台重复 / 本人转账 / 退款 / AA 回款 / 报销 / 未知 / 周期订阅 / 涨价 / 解析异常各至少若干例），否则语义矩阵在样例上不可见；分母从代码里的形态常量集反射，分子必须等于分母（防真值偏科与假覆盖）。
- **"未知"必须被注入**：样例必须包含"既不命中消费规则、也不命中转账词表"的流水，否则"未知是一等结论"这条纪律在基准上不可见。

## 四、数值口径纪律

- **数值口径只在一处定义**（参数包 `params`），识别引擎、报告、基准全部引用同一份；本文件与题面注记均为引用，**不得手写第二份口径**。
- **可参数化数值规则（首期 ≥4 类）**：跨平台去重**时间窗口**、周期订阅**最小重复次数**、周期**间隔容差**、涨价**判定阈值**——均为**用户可配置参数 + 经验默认值（注明非官方出处）**。
- **默认值标注纪律**：所有默认值均为经验示例值，**注明非官方出处**；工具不做"官方推荐值"的表述。
- **报告纪律**：HTML 报告只呈现引擎结论，不做二次计算（避免"报告里长出第二份口径"）；报告生成确定（同输入 → 同报告字节，配位级守门）。

## 五、隐私红线（本文件最重的一条）

- 账单是**极敏感数据**（含真实姓名/账号/消费地点/时间）。
- **纯本地零上传**：无网络调用、无账号、无遥测；报告与中间数据全部落本机。
- **合成样例用假商户白名单**（见 §三）；**禁止真实账单/真实商户入库**。
- **不触碰平台加密数据库、不做密钥提取/内存 dump**——这是本题与已删库方向（PyWxDump / chatlog）的本质区别，也是合规底线。

## 六、资产台账（M1 回填；M2 勘误重生成，2026-10-15）

全部资产由生成器程序化产出（`tools/` 内自研 splitmix64、固定 seed、无时钟、无 stdlib random），`tools/check_frozen.py` 全量 `--check` 位级守门（重生成与入库件逐字节比对，禁手改）。

- **生成器版本**：`gen_rules.py` v2、`gen_samples.py` v2（均登记进产物头；v2 勘误见 plan/04 §二——samples 修复 3 处形态未落盘、rules 新增列名别名表 column_aliases）；
- **seed**：`20261015`（gen_samples）；gen_rules 为纯静态构建（无 RNG）；
- **基准日**：2026-10-15（固定常量入产物，非运行时钟）；
- **复核方式**：`py tools/check_frozen.py`（全绿 = 与重生成位级一致）；`--ledger` 打印同款 sha256 台账。

| 路径 | 生成器 | sha256 |
|---|---|---|
| data/rules/manifest.json | gen_rules.py v2 | `d6a4d86f28ba3b5ce4352dee7eb835601d11aa9ddfbcb0431931e093090770a4` |
| data/rules/keywords.json | gen_rules.py v2 | `8462baf6717e63f33c4ca59c8937901b759e19066c10c3b2293a3cbce17f0e8a` |
| data/rules/aliases.json | gen_rules.py v2 | `b49f59bd7867ab63ca0b6aa9d96ff66f9de21ba5799eaa7dba9fdb6c53f2dc30` |
| data/truth/truth.json | gen_samples.py v2 (seed 20261015) | `35ee581cac0f9f56ac00f398f984c7bdbaffb9abda1999a05f76346cbfcbd28b` |
| data/samples/wechat-demo-01.csv | gen_samples.py v2 | `cdb10aaacfb2541b4d306de13897fe11cca956845abf80fc8edf6bc66dfb2fd2` |
| data/samples/wechat-demo-02.csv | gen_samples.py v2 | `9e8ddb6dacb62fec387d69881ebf1368bff99f46cea717b226272739d3a9b862` |
| data/samples/wechat-demo-03.xlsx | gen_samples.py v2 | `7603ffd8679e03cba400d4d361cb7c8a865da286b5550ca6f53e7c595b257e80` |
| data/samples/wechat-demo-bad-encoding.csv | gen_samples.py v2 | `81549fe047117ec6ae351359503f78205218512169853259a2d5ca4725254bd8` |
| data/samples/alipay-demo-01.csv | gen_samples.py v2 | `ebbeadef7d24808266b889dc84cdd43e15fe3c32ffa1a1874dbe00d4c614009d` |
| data/samples/alipay-demo-02.csv | gen_samples.py v2 | `00373de3e149a6b86c1dce05a604a24a2078d8088d5cb53d88e0ca5901b69b73` |
| data/samples/alipay-demo-empty.csv | gen_samples.py v2 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| data/samples/alipay-demo-header-only.csv | gen_samples.py v2 | `686ad999e3ad0cefbe1bbf4706a9ef578c5a0bc82aae915d9d99d48f881f5f44` |
| data/samples/bank-demo-01.csv | gen_samples.py v2 | `7a0ba26360f503b709406aaaab1e0810efb086fa7db4deaf783c3bbca0929dd8` |
| data/samples/bank-demo-02.csv | gen_samples.py v2 | `c5a01a88af2ce817fd8d9670bfdfce683549de87d693b44643a68f423886f5c7` |
| data/samples/bank-demo-03.xlsx | gen_samples.py v2 | `dd1dfdc03290d84281c43e8ccba722c27fffa554f026fa4c700681671ca299c3` |
| data/samples/bank-demo-missing-col.csv | gen_samples.py v2 | `f1596c9d1e8ce8935f5b82d5e4c8f53e0c127fc3fb4d5badca71b57e807d95e0` |

**形态覆盖（plan/04 §三，双登记进 `truth.json` 的 coverage 段）**：导入 27 形态 / 语义 8 形态（含"未知"与全部干扰例）/ 去重 8 形态（含窗口边界与 4 类防误报反例）/ 订阅 6 形态（含涨价、周期中断、非周期干扰）——全部注入、`sampled == total`，分子=分母由测试锁定（`tests/test_frozen_assets.py`）。

**冻结与编码**：以上文件在 `.gitattributes` 均为 `-text`（字节精确，防 EOL 改写）；克隆后 sha256 应与本表一致（`git status` 干净 + `py tools/check_frozen.py` 全绿即复核通过）。

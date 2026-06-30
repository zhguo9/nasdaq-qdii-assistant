# Nasdaq QDII Assistant

一个面向中国内地居民的纳指 QDII 决策助手 MVP。

它只做三件事：

- 用 `^NDX` 判断纳斯达克 100 指数趋势，失败时自动 fallback 到 `QQQ`
- 用 `161130` 作为默认实际交易基金，检查场内价格、净值、折溢价和成交额
- 给出买入、卖出或持有建议，并将每日信号保存到 CSV，方便之后复盘

它不会连接券商，不会自动下单，也不会绕过任何资金或监管限制。最终交易需要你在广发等合规渠道里手动确认。

## 适合的使用方式

你可以把它当成一个每天早上运行一次的小工具：

1. 美股收盘后获取 `^NDX` 行情
2. 如果 `^NDX` 数据源失败，自动改用 `QQQ`
3. 根据趋势、均线、回撤和波动率生成指数仓位建议
4. 检查 `161130` 的场内价格、最新净值、折溢价和成交额
5. 对照广发里的基金状态，确认是否暂停申购、限购或溢价过高
6. 自己手动确认是否下单

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m qdii_assistant --capital 60000 --cash 60000 --holding-value 0
```

如果本地暂时无法访问行情，可以用内置样例先试跑：

```powershell
python -m qdii_assistant --sample --capital 60000 --cash 60000 --holding-value 0
```

## 常用参数

```powershell
python -m qdii_assistant `
  --signal-symbol ^NDX `
  --fallback-symbol QQQ `
  --fund-code 161130 `
  --fund-name "易方达纳斯达克100ETF联接(QDII-LOF)A(人民币)" `
  --capital 60000 `
  --cash 45000 `
  --holding-value 15000 `
  --risk-profile balanced `
  --record
```

参数说明：

- `--signal-symbol`：默认 `^NDX`，作为纳斯达克 100 指数主信号
- `--fallback-symbol`：默认 `QQQ`，主信号失败时使用
- `--fund-code`：默认 `161130`，作为实际准备手动交易的基金
- `--fund-market`：东方财富市场编号，`0` 是深市，`1` 是沪市
- `--skip-fund-check`：跳过实际基金过滤，只输出指数趋势建议
- `--capital`：初始本金或计划投入总资金，单位人民币
- `--cash`：当前现金，单位人民币
- `--holding-value`：当前持仓市值，单位人民币
- `--risk-profile`：`conservative`、`balanced`、`aggressive`
- `--max-allocation`：最高仓位，默认由风险档位决定
- `--record`：把本次信号写入 `data/signals.csv`
- `--json`：输出机器可读 JSON
- `--sample`：使用内置样例行情和样例基金数据，不联网

## 策略逻辑

MVP 使用可解释的日线规则，不做黑箱预测。

指数趋势层：

- 收盘价高于 60 日/120 日均线，加分
- 20 日均线高于 60 日均线，加分
- 20 日动量为正，加分
- 最大回撤过大时降低仓位上限
- 年化波动率过高时降低仓位上限
- 单次交易金额受限，避免一次性满仓或清仓

实际基金过滤层：

- 如果 `161130` 相对最新净值溢价超过 5%，买入建议会被过滤为持有
- 如果溢价超过 2%，会保留买入建议但提示谨慎
- 如果成交额低于 200 万元，会提示流动性偏弱
- 如果净值过旧，会提示 QDII 净值可能滞后
- 程序无法判断暂停申购、限购和 QDII 额度，仍需在广发页面手动确认

默认风险档位：

- `conservative`：最高 60% 仓位
- `balanced`：最高 80% 仓位
- `aggressive`：最高 95% 仓位

## 运行测试

```powershell
python -m unittest discover -s tests
```

## 重要提醒

这个项目不是投资建议，也不是自动交易系统。QDII/ETF 交易前还需要你手动确认：

- 基金是否暂停申购或限制申购
- 场内 ETF/LOF 是否有明显折溢价
- 交易量和买卖价差是否合理
- 汇率、跟踪误差和费用是否可接受
- 当前资金路径是否合规


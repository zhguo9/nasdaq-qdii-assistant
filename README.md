# Nasdaq QDII Assistant

一个面向中国内地居民的纳指 QDII 决策助手 MVP。

它只做三件事：

- 根据 Nasdaq/QQQ 的日线趋势生成买入、卖出或持有建议
- 给出目标仓位、本次建议金额、理由和风险提醒
- 将每日信号保存到 CSV，方便之后复盘

它不会连接券商，不会自动下单，也不会绕过任何资金或监管限制。最终交易需要你在广发等合规渠道里手动确认。

## 适合的使用方式

你可以把它当成一个每天早上运行一次的小工具：

1. 美股收盘后获取 QQQ 行情
2. 根据趋势、均线、回撤和波动率生成建议
3. 对照广发里可买的纳指 QDII/ETF
4. 检查基金是否暂停申购、是否高溢价、是否适合当天交易
5. 自己手动确认是否下单

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m qdii_assistant --capital 60000 --cash 60000 --holding-value 0 --record
```

如果本地暂时无法访问 Yahoo 行情，可以用内置样例先试跑：

```powershell
python -m qdii_assistant --sample --capital 60000 --cash 60000 --holding-value 0
```

## 常用参数

```powershell
python -m qdii_assistant `
  --symbol QQQ `
  --fund-name "纳斯达克100 QDII" `
  --capital 60000 `
  --cash 45000 `
  --holding-value 15000 `
  --risk-profile balanced `
  --record
```

参数说明：

- `--symbol`：默认 `QQQ`，作为纳指 100 的代理行情
- `--fund-name`：你实际准备手动交易的基金名称
- `--capital`：初始本金或计划投入总资金，单位人民币
- `--cash`：当前现金，单位人民币
- `--holding-value`：当前持仓市值，单位人民币
- `--risk-profile`：`conservative`、`balanced`、`aggressive`
- `--max-allocation`：最高仓位，默认由风险档位决定
- `--record`：把本次信号写入 `data/signals.csv`
- `--json`：输出机器可读 JSON
- `--sample`：使用内置样例行情，不联网

## 策略逻辑

MVP 使用可解释的日线规则，不做黑箱预测：

- 收盘价高于 60 日/120 日均线，加分
- 20 日均线高于 60 日均线，加分
- 20 日动量为正，加分
- 最大回撤过大时降低仓位上限
- 年化波动率过高时降低仓位上限
- 单次交易金额受限，避免一次性满仓或清仓

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
- 场内 ETF 是否有明显折溢价
- 交易量和买卖价差是否合理
- 汇率、跟踪误差和费用是否可接受
- 当前资金路径是否合规


# ETF 数据服务（GitHub 静态数据 + MCP）

把《ETF所有数据汇总.xlsx》发布成网上可取的 JSON 数据，零服务器、零成本。

## 目录结构

```
etf-data-service/
├── scripts/excel_to_json.py   # Excel → JSON 转换器（唯一需要运行的脚本）
├── mcp_server.py              # MCP server（FastMCP，读 GitHub raw 上的 JSON）
├── data/                      # 生成的数据文件（push 到 GitHub 的就是这个目录）
│   ├── index.json             # 数据包清单与口径说明
│   ├── overview.json          # 收益波动与资金流向概览（24 条分类）
│   ├── detail_all.json        # 1695 只 ETF 明细画像（88 字段，5.2MB）
│   ├── detail/*.json          # 明细按看板一级分类拆分：行业/宽基/策略/QDII/债券/商品（按需取用更快）
│   ├── flows_*.json           # 资金流向日频累计净流入（长表格式）
│   ├── scale_monthly.json     # 基金规模月度变化（2020 至今）
│   └── category/*.json        # 13 个行业/主题分类名单
└── README.md
```

## 一次性部署

```bash
# 1. 生成数据（每次拿到新 Excel 都跑这一步）
python scripts/excel_to_json.py "path/to/ETF所有数据汇总.xlsx"

# 2. 建 GitHub 公开仓库并推送（假设仓库叫 etf-data）
cd etf-data-service
git init && git add data README.md && git commit -m "etf data 20261009"
git remote add origin https://github.com/kao-chang/etf-data.git
git push -u origin main
```

推送后数据立刻可通过 raw URL 访问，例如：

```
https://raw.githubusercontent.com/kao-chang/etf-data/main/data/detail_all.json
https://raw.githubusercontent.com/kao-chang/etf-data/main/data/index.json
```

任何人（任何程序、任何 AI）直接 HTTP GET 就能取数，不需要账号。

## 日常更新数据

```bash
python scripts/excel_to_json.py "新的Excel.xlsx"   # 重新生成 data/
git add data && git commit -m "update 20261022" && git push
```

就这两步。想要自动化，可以在 GitHub Actions 里挂一个 workflow，
把新 Excel 传进仓库（或用 GitHub API 上传）后自动跑转换脚本。

## MCP 接入（可选）

如果取用方是 AI 客户端（Claude Desktop / Kimi 等），让它配这个 MCP server：

```bash
pip install fastmcp requests
python mcp_server.py
```

客户端配置示例（Claude Desktop 的 claude_desktop_config.json）：

```json
{
  "mcpServers": {
    "etf-data": {
      "command": "python",
      "args": ["<本目录绝对路径>/mcp_server.py"],
      "env": {
        "ETF_DATA_BASE": "https://raw.githubusercontent.com/kao-chang/etf-data/main/data"
      }
    }
  }
}
```

提供的工具：`list_datasets`、`get_overview`、`get_etf_detail(code, group)`、
`screen_etfs(field, op, value, limit, group)`、`get_category(name)`、
`get_fund_flows(group)`、`get_flow_series(group, series, last_n)`。
其中 `group` 可选：行业/宽基/策略/QDII/债券/商品，指定后只下载对应分类文件。

> 注意：`mcp_server.py` 里的 DEFAULT_BASE 占位符要换成你自己的仓库地址。

## 数据口径

- 净流入额、规模：亿元；收益率/波动率/估值分位：%；日均成交额：元
- 时间序列为累计值，日期为交易日（月频表为月末）
- 数据生成时间见 `index.json` 的 `generated_at`

# -*- coding: utf-8 -*-
"""
ETF 数据 MCP Server（方案一：GitHub 静态数据 + 只读查询工具）

数据源是 GitHub 仓库里的静态 JSON（raw URL），无需数据库、无需自己维护服务器。
别人在自己的 AI 客户端里配置这个 MCP server，即可用自然语言查询 ETF 数据。

运行：
    pip install fastmcp requests
    python mcp_server.py            # stdio 模式（Claude/Kimi 等本地客户端配置）

环境变量：
    ETF_DATA_BASE   数据根 URL，默认指向下面的 DEFAULT_BASE，换成你自己的仓库即可
"""
import os
import functools

import requests

try:
    from fastmcp import FastMCP
    mcp = FastMCP("etf-data", instructions="中国 ETF 市场数据：收益波动概览、ETF 明细画像、分类名单、资金流向时间序列。")
except ImportError:
    # 没装 fastmcp 时：查询函数仍可直接 import 复用（测试/本地脚本）
    mcp = None

    class _NoOpMCP:
        def tool(self, fn):
            return fn

    mcp = _NoOpMCP()

DEFAULT_BASE = "https://raw.githubusercontent.com/kao-chang/etf-data/main/data"
BASE = os.environ.get("ETF_DATA_BASE", DEFAULT_BASE).rstrip("/")


@functools.lru_cache(maxsize=32)
def _load(path: str) -> dict:
    """拉取并缓存一个 JSON 文件。"""
    r = requests.get(f"{BASE}/{path}", timeout=30)
    r.raise_for_status()
    return r.json()


@mcp.tool
def list_datasets() -> dict:
    """列出数据包里所有可用数据集、记录数、生成时间和字段口径说明。"""
    return _load("index.json")


@mcp.tool
def get_overview() -> dict:
    """收益波动与资金流向概览：按一级/二级分类给出收益均值、规模、3年波动率、近1周/2周/1月/3月/今年净流入。"""
    return _load("overview.json")


DETAIL_GROUPS = ["行业", "宽基", "策略", "QDII", "债券", "商品"]


def _quote(name: str) -> str:
    import urllib.parse
    return urllib.parse.quote(name)


def _detail_records(group: str | None = None) -> list:
    """取明细记录：指定 group 时只拉该分类文件（小），否则拉全量 detail_all。"""
    if group:
        if group not in DETAIL_GROUPS:
            return []
        return _load(f"detail/{_quote(group)}.json")["records"]
    return _load("detail_all.json")["records"]


@mcp.tool
def get_etf_detail(code: str, group: str = "") -> dict:
    """按代码查询单只 ETF 的完整画像（88 个字段：基本信息、标签、成分结构、业绩、基本面、市场、产品）。

    参数 code 形如 "510050.SH"。可选 group（行业/宽基/策略/QDII/债券/商品）
    用于只下载对应分类文件，更快；不传则查全量。找不到时返回相近代码列表。
    """
    code = code.strip().upper()
    recs = _detail_records(group or None)
    if not recs:
        return {"error": f"group 必须是 {DETAIL_GROUPS} 之一"}
    for r in recs:
        if str(r.get("代码", "")).upper() == code:
            return r
    if group:  # 指定分类没找到，回退全量再找一次
        for r in _detail_records():
            if str(r.get("代码", "")).upper() == code:
                return r
    near = [r.get("代码") for r in recs if code.split(".")[0] in str(r.get("代码", ""))][:10]
    return {"error": f"未找到 {code}", "相近代码": near}


@mcp.tool
def screen_etfs(field: str, op: str, value: float, limit: int = 20, group: str = "") -> dict:
    """按数值字段筛选 ETF。例：field='规模（亿元）', op='>', value=100。

    op 支持 > >= < <= == !=。可选 group（行业/宽基/策略/QDII/债券/商品）
    限定在单个分类内筛选（只下载该分类文件）；不传则全量筛选。
    返回按该字段降序的前 limit 条。
    """
    recs = _detail_records(group or None)
    if not recs:
        return {"error": f"group 必须是 {DETAIL_GROUPS} 之一"}
    ops = {
        ">": lambda a, b: a > b, ">=": lambda a, b: a >= b,
        "<": lambda a, b: a < b, "<=": lambda a, b: a <= b,
        "==": lambda a, b: a == b, "!=": lambda a, b: a != b,
    }
    if op not in ops:
        return {"error": f"op 必须是 {list(ops)}"}
    fn = ops[op]
    hits = [r for r in recs
            if isinstance(r.get(field), (int, float)) and fn(r[field], value)]
    hits.sort(key=lambda r: r[field], reverse=True)
    return {"count": len(hits), "records": hits[:limit]}


@mcp.tool
def get_category(name: str) -> dict:
    """获取某个分类的全部 ETF 名单及画像。name 可选：科技/红利/消费/医药/大制造/QDII/AI/机器人/新能源/稳定币/卫星商业航天/商品/港股。"""
    import urllib.parse
    return _load("category/" + urllib.parse.quote(name) + ".json")


@mcp.tool
def get_fund_flows(group: str = "broad") -> dict:
    """资金流向累计净流入时间序列（日频，亿元）。
    group: broad=宽基, sector=行业+红利, bond=债基, scale=基金规模月度变化。
    """
    files = {"broad": "flows_broad.json", "sector": "flows_sector.json",
             "bond": "flows_bond.json", "scale": "scale_monthly.json"}
    if group not in files:
        return {"error": f"group 必须是 {list(files)}"}
    return _load(files[group])


@mcp.tool
def get_flow_series(group: str, series: str, last_n: int = 60) -> dict:
    """取某一条资金流向序列的最近 N 个点。例：group='broad', series='沪深300', last_n=20。"""
    data = get_fund_flows(group)
    if "series" not in data or series not in data["series"]:
        return {"error": "序列不存在", "可选": list(data.get("series", {}))}
    points = data["series"][series][-last_n:]
    return {"series": series, "unit": "亿元", "count": len(points), "points": points}


if __name__ == "__main__":
    mcp.run()

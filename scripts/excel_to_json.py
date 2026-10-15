# -*- coding: utf-8 -*-
"""
把《ETF所有数据汇总.xlsx》转换成对外发布的 JSON 数据包。

输出目录结构（data/）：
  index.json                数据包元信息 + 各文件清单
  overview.json             收益波动与资金流向概览表（截面）
  detail_all.json           明细汇总表（1697 只 ETF 全字段截面）
  category/<sheet>.json     各行业分类表（科技/红利/消费/医药/大制造/QDII/AI/机器人）
  flows_broad.json          资金流向-宽基累计流入（长表：date, series, value）
  flows_sector.json         资金流向-行业＋红利累计流入
  flows_bond.json           资金流向-债基累计流入
  scale_monthly.json        资金流向-基金规模变化（月频）

用法：python excel_to_json.py <xlsx路径> [输出目录]
"""
import json
import sys
import math
import datetime
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent  # 项目根目录（scripts 的上一级）
OUT_DEFAULT = ROOT / "data"

# sheet 名 -> 输出文件名
FLOW_SHEETS = {
    "资金流向-宽基累计流入": "flows_broad.json",
    "资金流向-行业＋红利累计流入": "flows_sector.json",
    "资金流向-债基累计流入": "flows_bond.json",
    "资金流向-基金规模变化": "scale_monthly.json",
}
OVERVIEW_SHEET = "收益波动与资金流向概览表"
DETAIL_SHEET = "明细汇总表"
# 其余 sheet 一律作为分类截面表处理


def clean(v):
    """把单元格值转成 JSON 安全类型；无效值转 None。"""
    if v is None:
        return None
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return round(v, 6)
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, str):
        v = v.strip()
        return v if v else None
    return v


def sheet_rows(ws):
    return [[clean(c) for c in row] for row in ws.iter_rows(values_only=True)]


def is_blank_row(row):
    return all(c is None for c in row)


def convert_cross_section(rows, header_row_idx, name):
    """行式截面表：header_row_idx 是字段名所在行，其后每行是一条记录。"""
    header = rows[header_row_idx]
    fields, keep = [], []
    for j, h in enumerate(header):
        if h is not None:
            h = str(h).replace("\n", "").strip()
        fields.append(h)
        keep.append(h is not None)
    records = []
    for row in rows[header_row_idx + 1:]:
        if is_blank_row(row):
            continue
        rec = {}
        for j in range(len(fields)):
            if keep[j] and j < len(row):
                rec[fields[j]] = row[j]
        if any(v is not None for v in rec.values()):
            records.append(rec)
    return {"table": name, "fields": [f for f in fields if f], "count": len(records), "records": records}


def convert_timeseries(rows, name):
    """宽表时间序列：第一行是日期（首格为空），第一列是序列名。转成长表。"""
    dates = [c for c in rows[0][1:] if c]
    series = {}
    for row in rows[1:]:
        if not row or row[0] is None:
            continue
        name_ = str(row[0])
        vals = [row[i + 1] if i + 1 < len(row) else None for i in range(len(dates))]
        series[name_] = [{"date": d, "value": v} for d, v in zip(dates, vals) if v is not None]
    return {"table": name, "dates": [d for d in dates], "series": series}


def main():
    xlsx = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else OUT_DEFAULT
    (out / "category").mkdir(parents=True, exist_ok=True)
    (out / "detail").mkdir(parents=True, exist_ok=True)

    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    manifest = {
        "name": "ETF所有数据汇总",
        "source_file": xlsx.name,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "unit_notes": {
            "净流入额": "亿元", "规模": "亿元", "收益率/波动率/估值分位": "%",
            "日均成交额": "元",
        },
        "files": {},
    }
    detail_data = None

    for ws in wb.worksheets:
        rows = sheet_rows(ws)
        title = ws.title
        if not rows or is_blank_row(rows[0]):
            continue
        if title in FLOW_SHEETS:
            data = convert_timeseries(rows, title)
            fname = FLOW_SHEETS[title]
        elif title == OVERVIEW_SHEET:
            data = convert_cross_section(rows, 0, title)
            fname = "overview.json"
        else:
            # 明细汇总表与各行业分类表：第 1 行是分组名，第 2 行才是字段名
            data = convert_cross_section(rows, 1, title)
            if title == DETAIL_SHEET:
                fname = "detail_all.json"
            else:
                fname = f"category/{title}.json"
        p = out / fname
        p.write_text(json.dumps(data, ensure_ascii=False, indent=None), encoding="utf-8")
        n = data.get("count", len(data.get("series", {})))
        manifest["files"][fname] = {"table": title, "records_or_series": n}
        print(f"{title} -> {fname}  ({n})")
        if title == DETAIL_SHEET:
            detail_data = data

    # 明细汇总表按「看板一级分类」拆成小文件，取用方可只下载某一类
    if detail_data:
        groups = {}
        for r in detail_data["records"]:
            groups.setdefault(str(r.get("看板一级分类") or "未分类"), []).append(r)
        for gname, grecs in sorted(groups.items()):
            gdata = {"table": f"明细汇总-{gname}", "fields": detail_data["fields"],
                     "count": len(grecs), "records": grecs}
            fname = f"detail/{gname}.json"
            (out / fname).write_text(
                json.dumps(gdata, ensure_ascii=False, indent=None), encoding="utf-8")
            manifest["files"][fname] = {"table": f"明细汇总-{gname}", "records_or_series": len(grecs)}
            print(f"  拆分: {fname}  ({len(grecs)})")

    (out / "index.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDone -> {out}")


if __name__ == "__main__":
    main()

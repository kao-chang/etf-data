# -*- coding: utf-8 -*-
r"""
一键更新 ETF 数据到 GitHub。

用法：
    python update.py                          # 自动找微信收件目录里最新的「ETF所有数据汇总*.xlsx」
    python update.py "D:\path\to\新表.xlsx"    # 手动指定文件

做的事：
  1. 找到新 Excel，和 last_update.txt 里记录的源文件比对，没变就跳过
  2. 跑 excel_to_json.py 重新生成 data/
  3. git add + commit + push（commit 信息带源文件名日期）
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WECHAT_DIR = Path(r"D:\xwechat_files\nemo0027_6859\msg\file")
STATE_FILE = ROOT / "last_update.txt"
PATTERN = re.compile(r"ETF所有数据汇总[-_]?(\d{8})?")


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print("+", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, cwd=ROOT, check=True, **kw)


def find_latest_xlsx() -> Path | None:
    candidates = []
    for p in WECHAT_DIR.rglob("ETF所有数据汇总*.xlsx"):
        m = PATTERN.search(p.name)
        date = m.group(1) or "00000000"
        candidates.append((date, p.stat().st_mtime, p))
    if not candidates:
        return None
    candidates.sort()
    return candidates[-1][2]


def main() -> int:
    xlsx = Path(sys.argv[1]) if len(sys.argv) > 1 else find_latest_xlsx()
    if not xlsx or not xlsx.exists():
        print("未找到新的 ETF所有数据汇总*.xlsx（可把文件路径作为参数传入）")
        return 1

    marker = f"{xlsx.name}|{xlsx.stat().st_size}"
    if STATE_FILE.exists() and STATE_FILE.read_text(encoding="utf-8").strip() == marker:
        print(f"源文件未变化（{xlsx.name}），跳过更新")
        return 0

    print(f"新源文件: {xlsx}")
    run([sys.executable, str(ROOT / "scripts" / "excel_to_json.py"), str(xlsx)])

    date_m = PATTERN.search(xlsx.name)
    date_tag = date_m.group(1) or "update"
    run(["git", "add", "data"])
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT)
    if diff.returncode == 0:
        print("data/ 无变化，跳过提交")
    else:
        run(["git", "commit", "-m", f"数据更新 {date_tag}（源文件 {xlsx.name}）"])
        run(["git", "push"])

    STATE_FILE.write_text(marker, encoding="utf-8")
    print(f"\n完成 ✅ 数据已更新到 GitHub（{date_tag}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

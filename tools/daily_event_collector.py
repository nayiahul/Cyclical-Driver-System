"""每日事件采集器 — 财报真空期的信息流层 (X, 只采集不决策)。

流程 (Rule: 采集自动, 影响人工评估):
  1. 读取研究池 Top50 + Shadow 观察池
  2. akshare: 个股公告 + 个股新闻 (公司事件 X1)
  3. AnySearch: 行业/政策关键词检索 (X3 政策 — FCC 类盲区)
  4. 财联社快讯: 行业关键词过滤
  5. 写入 data/events/{date}_events.jsonl (分类/方向/风险标记)
  6. 输出 Book 的 Market Intelligence Brief 摘要

输出:
  data/events/YYYYMMDD_events.jsonl   全量事件
  output/events_brief_{date}.md        人工阅读摘要

用法:
  python tools/daily_event_collector.py                # 默认: Top50 研究池
  python tools/daily_event_collector.py --pool <csv>   # 指定池
  python tools/daily_event_collector.py --top 20        # 只扫前 20
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd

warnings.filterwarnings("ignore")

EVENT_DIR = "data/events"
INDUSTRY_KEYWORDS = {
    "通信/电子": ["FCC", "光模块", "800G", "1.6T", "出口管制", "云厂商", "AI算力", "硅光",
                 "NVIDIA", "HBM", "制裁", "实体清单"],
    "有色/周期": ["碳酸锂", "铜价", "铝价", "稀土", "产能", "关税", "库存"],
    "医药": ["集采", "FDA", "医保", "创新药", "临床试验", "BD"],
    "通用": ["回购", "增持", "减持", "业绩预告", "预增", "预减", "中标", "重大合同",
            "立案", "问询函", "重组"],
}

# 行业代码前缀 → 关键词组
CODE_PREFIX_KEYWORDS = {
    ("300", "301", "688"): ["通信/电子", "通用"],
    ("002", "000", "600", "601", "603", "605"): ["通用"],
}


def get_keywords_for(code: str) -> list[str]:
    kws = []
    for prefix, groups in CODE_PREFIX_KEYWORDS.items():
        if code.startswith(prefix):
            for g in groups:
                kws += INDUSTRY_KEYWORDS.get(g, [])
    # 全量通用
    return list(dict.fromkeys(kws + INDUSTRY_KEYWORDS["通用"]))


def scan_announcements(codes: list[str], days: int = 10) -> list[dict]:
    import akshare as ak
    out = []
    today = datetime.now().strftime("%Y%m%d")
    try:
        df = ak.stock_notice_report(symbol="全部", date=today)
    except Exception:
        return out
    if df is None or df.empty or "代码" not in df.columns:
        return out
    code_set = {str(c).zfill(6) for c in codes}
    sub = df[df["代码"].astype(str).str.zfill(6).isin(code_set)].copy()
    for _, r in sub.iterrows():
        title = str(r["公告标题"])
        risk = any(k in title for k in ["FCC", "禁令", "制裁", "立案", "处罚", "减持",
                                        "退市", "问询函", "诉讼", "出口管制"])
        out.append({
            "date": str(r["公告日期"])[:10], "code": str(r["代码"]).zfill(6),
            "name": str(r["名称"]), "type": "公告", "title": title[:150],
            "risk": risk,
        })
    return out


def scan_flash(keywords: list[str]) -> list[dict]:
    import akshare as ak
    out = []
    try:
        df = ak.stock_info_global_cls(symbol="全部")
    except Exception:
        return out
    if df is None or df.empty:
        return out
    for _, r in df.head(30).iterrows():
        text = str(r.get("标题", "")) + str(r.get("内容", ""))
        hit = [kw for kw in keywords if kw in text]
        if hit:
            out.append({
                "date": str(r.get("发布时间", ""))[:16], "code": "",
                "type": "快讯", "title": text[:150],
                "risk": any(k in text for k in ["FCC", "禁令", "制裁", "出口管制"]),
                "hit_kw": hit[:3],
            })
    return out


def main():
    ap = argparse.ArgumentParser(description="每日事件采集器 (X 层)")
    ap.add_argument("--pool", default="output/research_pool_v3_20260901.csv")
    ap.add_argument("--top", type=int, default=50, help="扫描池前 N 只 (按优先级)")
    ap.add_argument("--shadow", action="store_true", help="包含 Shadow 观察池")
    args = ap.parse_args()

    os.makedirs(EVENT_DIR, exist_ok=True)
    # 1. 读取池
    if os.path.exists(args.pool):
        pool = pd.read_csv(args.pool)
        pool["code"] = pool["code"].astype(str).str.zfill(6)
        pool = pool.sort_values("research_priority", na_position="last")
        codes = pool["code"].head(args.top).tolist()
    else:
        codes = []
    # Shadow 池
    if args.shadow:
        for code in ["300308", "300502", "002281", "300394", "300620",
                     "688048", "300548", "603083"]:
            if code not in codes:
                codes.append(code)
    print(f"扫描池: {len(codes)} 只")

    # 2. 采集
    events = scan_announcements(codes)
    flash_kws = sum(INDUSTRY_KEYWORDS.values(), [])
    events += scan_flash(flash_kws)
    print(f"公告+快讯: {len(events)} 条")

    # 3. 保存
    today = datetime.now().strftime("%Y%m%d")
    path = f"{EVENT_DIR}/{today}_events.jsonl"
    with open(path, "w") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    # 4. 简报
    brief_path = f"output/events_brief_{today}.md"
    lines = [f"# Market Intelligence Brief — {today}", "",
             f"**扫描池**: {len(codes)} 只 | **事件**: {len(events)} 条",
             f"**高风险**: {sum(1 for e in events if e.get('risk'))} 条 ⚠️", "",
             "| 日期 | 代码 | 类型 | 风险 | 标题 |", "|---|---|---|---|---|"]
    for e in sorted(events, key=lambda x: x["date"], reverse=True)[:40]:
        risk = "⚠️" if e.get("risk") else ""
        lines.append(f"| {e['date']} | {e.get('code','')} | {e['type']} | {risk} | "
                     f"{e['title'][:70].replace('|','/')} |")
    with open(brief_path, "w") as f:
        f.write("\n".join(lines))
    print(f"已保存: {path}")
    print(f"简报: {brief_path} ({sum(1 for e in events if e.get('risk'))} 高风险)")


if __name__ == "__main__":
    main()

"""事件扫描工具 — 影响股价的重大信息聚合 (Research Layer, 非评分层)。

背景: FCC 禁令事件暴露系统盲区 — 政策/事件无法从财务数据发现。
设计原则 (防噪声):
  1. 事件信息 = 研究输入, 不进入自动评分/状态机
  2. 工具聚合 + 分类 + 风险提示, 影响判断由人工完成
  3. 任何 DEEP_RESEARCH 标的研究前必须跑事件扫描

数据源:
  - A股公告 (akshare, 全量+个股)
  - 个股新闻 (东财)
  - 财联社快讯 (宏观/行业)

输出: md 时间线 + 事件分类 + 风险关键词提示
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import warnings

warnings.filterwarnings("ignore")

# E1-E18 事件分类 taxonomy (04 Alpha v3 体系, 2026-09-03 升级)
EVENT_CATEGORIES = {
    "E1订单/客户": ["订单", "大客户", "合同", "框架协议", "采购", "中标", "供应商认证", "定点", "客户"],
    "E2产品/技术": ["新产品", "量产", "发布", "技术突破", "认证", "1.6T", "800G", "硅光", "CPO", "平台"],
    "E3产能/CapEx": ["扩产", "新厂", "新产线", "设备采购", "投产", "产能", "资本开支"],
    "E4财务数据": ["业绩预告", "年报", "半年报", "季报", "净利润", "营业收入", "预增", "预减", "扭亏", "快报", "财报"],
    "E5毛利/价格": ["降价", "涨价", "ASP", "价格战", "毛利率", "成本上升", "成本下降", "提价"],
    "E6供应链": ["原材料", "供应商", "缺货", "断供", "产能限制", "库存", "交付", "物流"],
    "E7竞争格局": ["市占率", "竞争者", "竞争对手", "替代", "新进入者", "份额", "退出市场"],
    "E8并购/资产": ["收购", "出售", "并购", "重组", "剥离", "分拆", "私有化", "定增"],
    "E9管理层/治理": ["CEO", "CFO", "高管", "回购", "增持", "减持", "股权激励", "员工持股", "辞职", "离职"],
    "E10政策/监管": ["FCC", "禁令", "制裁", "出口管制", "实体清单", "关税", "商务部", "国防部",
                    "限制进口", "审查", "反垄断", "监管", "FDA", "医保", "集采"],
    "E11宏观利率": ["美联储", "FOMC", "降息", "加息", "国债收益率", "利率", "联邦基金"],
    "E12资金/市场": ["ETF", "指数纳入", "指数剔除", "基金", "融资", "大宗交易", "北向", "被动资金"],
    "E13产业周期": ["库存周期", "景气", "需求拐点", "去库存", "补库存", "周期"],
    "E14客户CapEx": ["资本开支指引", "云厂商", "CapEx", "capex", "算力投资", "数据中心建设"],
    "E15技术替代": ["硅光", "CPO", "铜连接", "LPO", "新技术路线", "替代技术"],
    "E16地缘政治": ["台湾", "战争", "贸易冲突", "地缘", "霍尔木兹", "制裁升级"],
    "E17法律/ESG": ["诉讼", "立案", "处罚", "调查", "做空", "环保", "合规", "问询函"],
    "E18市场情绪": ["恐慌", "泡沫", "风格切换", "暴跌", "避险", "抛售"],
    "公司事件": ["澄清", "回应", "辟谣", "说明公告"],   # 保留兜底
}

# 高风险关键词 (需人工确认, 触发 ⚠️)
HIGH_RISK_KEYWORDS = ["FCC", "禁令", "制裁", "出口管制", "实体清单", "立案", "处罚",
                      "退市", "减持", "诉讼", "限制进口", "关税", "重大诉讼", "问询函"]


def classify_event(text: str) -> str:
    """E1-E18 taxonomy 分类 (首个命中; 未命中 '其他'——按影响链补查)。"""
    for cat, kws in EVENT_CATEGORIES.items():
        if any(kw in text for kw in kws):
            return cat
    return "其他"


def has_high_risk(text: str) -> bool:
    return any(kw in text for kw in HIGH_RISK_KEYWORDS)


def scan_announcements(code: str, days: int = 60) -> list[dict]:
    """近 days 天个股公告。"""
    import akshare as ak
    start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    try:
        df = ak.stock_notice_report(symbol="全部", date=datetime.now().strftime("%Y%m%d"))
    except Exception:
        return []
    if df is None or df.empty or "代码" not in df.columns:
        return []
    code6 = str(code).zfill(6)
    sub = df[df["代码"].astype(str).str.zfill(6) == code6].copy()
    sub = sub[sub["公告日期"].astype(str) >= start]
    out = []
    for _, r in sub.iterrows():
        title = str(r["公告标题"])
        out.append({
            "date": str(r["公告日期"])[:10], "type": "公告",
            "category": classify_event(title), "title": title[:120],
            "risk": has_high_risk(title),
            "directness": "A",  # 公告=直接影响(公司事实)
        })
    return out


def scan_news(code: str, days: int = 60) -> list[dict]:
    """近 N 条个股新闻。"""
    import akshare as ak
    try:
        df = ak.stock_news_em(symbol=str(code).zfill(6))
    except Exception:
        return []
    if df is None or df.empty:
        return []
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    out = []
    for _, r in df.iterrows():
        ts = str(r.get("发布时间", ""))[:10]
        if ts < cutoff:
            continue
        text = f"{r.get('新闻标题', '')} {r.get('新闻内容', '')}"[:300]
        out.append({
            "date": ts, "type": "新闻",
            "category": classify_event(text), "title": str(r.get("新闻标题", ""))[:120],
            "risk": has_high_risk(text),
            "source": str(r.get("文章来源", "")), "url": str(r.get("新闻链接", "")),
        })
    return out


def scan_flash(keywords: list[str], days: int = 14) -> list[dict]:
    """财联社快讯 (行业/宏观, 近 days 天 — 接口返回最新 20 条左右)。"""
    import akshare as ak
    try:
        df = ak.stock_info_global_cls(symbol="全部")
    except Exception:
        return []
    if df is None or df.empty:
        return []
    out = []
    for _, r in df.iterrows():
        text = str(r.get("标题", "")) + " " + str(r.get("内容", ""))
        if any(kw in text for kw in keywords):
            out.append({
                "date": str(r.get("发布时间", ""))[:16], "type": "快讯",
                "category": classify_event(text), "title": text[:150],
                "risk": has_high_risk(text),
            })
    return out


def scan_web_events(code: str, name: str, industry_kws: list[str]) -> list[dict]:
    """政策/行业事件 Web 检索 (AnySearch CLI, 第二数据源)。

    akshare 个股新闻不覆盖外媒政策事件 (如 FCC 禁令经 Reuters 首发),
    必须用 Web 检索补充 — 这是 FCC 事件漏检的直接教训。
    """
    import subprocess
    cli = "/Users/nayiahlu/.pi/agent/skills/anysearch/scripts/anysearch_cli.py"
    if not os.path.exists(cli):
        return []
    queries = [f"{name} {code} 政策 禁令 制裁 出口管制",
               f"{name} 光模块 近60天 重大消息"] +               [f"{kw} 2026 政策 事件" for kw in industry_kws[:2]]
    out = []
    for q in queries:
        try:
            r = subprocess.run(
                ["python3", cli, "search", q, "--max_results", "3"],
                capture_output=True, text=True, timeout=60,
                cwd="/Users/nayiahlu/.pi/agent/skills/anysearch")
            text = r.stdout
            # 解析标题行 (粗解析: 取 ## 标题与描述)
            for line in text.split("\n"):
                line = line.strip()
                if line.startswith("###"):
                    out.append({"date": "", "type": "政策/行业(Web)",
                                "category": classify_event(line),
                                "title": line.replace("### ", "")[:120],
                                "risk": has_high_risk(line),
                                "source": "AnySearch"})
        except Exception:
            continue
    return out


def render_timeline(events: list[dict], code: str, name: str) -> str:
    lines = [
        f"# 事件扫描: {code} {name} (近60天)",
        "",
        f"**共 {len(events)} 条事件** | 高风险 {sum(1 for e in events if e['risk'])} 条 ⚠️",
        "",
        "| 日期 | 类型 | 分类 | 风险 | 标题 |",
        "|---|---|---|---|---|",
    ]
    for e in sorted(events, key=lambda x: x["date"], reverse=True):
        risk = "⚠️" if e["risk"] else ""
        lines.append(f"| {e['date']} | {e['type']} | {e['category']} | {risk} | "
                     f"{e['title'][:80].replace('|', '/')} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="事件扫描 (研究层)")
    ap.add_argument("--code", required=True, help="6位股票代码")
    ap.add_argument("--name", default="", help="股票名称")
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--keywords", default="", help="快讯检索关键词, 逗号分隔")
    ap.add_argument("--out", default=None, help="输出 md 路径 (默认 output/events_{code}.md)")
    args = ap.parse_args()

    code = str(args.code).zfill(6)
    events = []
    events += scan_announcements(code, args.days)
    events += scan_news(code, args.days)
    if args.keywords:
        events += scan_flash([k.strip() for k in args.keywords.split(",")], min(args.days, 14))
    # 第二源: 政策/行业 Web 检索 (防 akshare 盲区 — FCC 教训)
    if args.keywords:
        events += scan_web_events(code, args.name, [k.strip() for k in args.keywords.split(",")])

    # 分类统计 + 去重 (同标题只留最新)
    seen = set()
    dedup = []
    for e in sorted(events, key=lambda x: x["date"], reverse=True):
        key = e["title"][:50]
        if key not in seen:
            seen.add(key)
            dedup.append(e)

    md = render_timeline(dedup, code, args.name)
    out_path = args.out or f"output/events_{code}.md"
    os.makedirs("output", exist_ok=True)
    with open(out_path, "w") as f:
        f.write(md)

    # 控制台摘要
    print(f"=== 事件扫描: {code} {args.name} ===")
    print(f"共 {len(dedup)} 条 | 高风险 {sum(1 for e in dedup if e['risk'])} 条")
    cats = {}
    for e in dedup:
        cats[e["category"]] = cats.get(e["category"], 0) + 1
    print(f"分类: {cats}")
    for e in dedup:
        if e["risk"]:
            print(f"  ⚠️ {e['date']} [{e['category']}] {e['title'][:90]}")
    print(f"\n已保存: {out_path}")


if __name__ == "__main__":
    main()

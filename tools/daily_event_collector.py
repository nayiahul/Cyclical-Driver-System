"""每日事件采集器 — 财报真空期的信息流层 (X, 只采集不决策)。

流程 (Rule: 采集自动, 影响人工评估):
  1. 读取研究池 Top50 + Shadow 观察池 → 池内公告 (X1)
  2. 全市场公告 → 池外高价值白名单过滤 (立案/订单/业绩预告类) ← v1.1 新增盲区修复
  3. 财联社快讯全量 (去 head30 截断) + 当日热词 Top10      ← v1.1 新增
  4. E1-E18 分类接线 (event_scan.classify_event)           ← v1.1 新增
  5. source/source_rank 溯源字段 (A=交易所 B=聚合快讯)      ← v1.1 新增
  6. 写入 data/events/{date}_events.jsonl (分类/方向/风险标记)
  7. 输出 Book 的 Market Intelligence Brief 摘要 (分区: 池内/池外/快讯/热词)

用法:
  python tools/daily_event_collector.py                # 默认: Top50 研究池
  python tools/daily_event_collector.py --pool <csv>   # 指定池
  python tools/daily_event_collector.py --top 20        # 只扫前 20
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import warnings
from collections import Counter
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd

warnings.filterwarnings("ignore")

try:
    from event_scan import classify_event
except Exception:
    def classify_event(text: str) -> str:
        return "未分类"

EVENT_DIR = "data/events"
INDUSTRY_KEYWORDS = {
    "通信/电子": ["FCC", "光模块", "800G", "1.6T", "出口管制", "云厂商", "AI算力", "硅光",
                 "NVIDIA", "HBM", "制裁", "实体清单"],
    "有色/周期": ["碳酸锂", "铜价", "铝价", "稀土", "产能", "关税", "库存"],
    "医药": ["集采", "FDA", "医保", "创新药", "临床试验", "BD"],
    "通用": ["回购", "增持", "减持", "业绩预告", "预增", "预减", "中标", "重大合同",
            "立案", "问询函", "重组"],
}

# 池外高价值公告白名单 (v1.2: 盲区修复——研究池是过去结果, 机会诞生时常在池外。
# 只放高信号词; 减持/异动风险提示类例行高频词已实测排除 (v1.1→v1.2 迭代: 46 条中
# 减持类占 ~15 条纯噪声; 减持监控留给 thesis x_monitors 未来接线, 不属于池外发现)。
POOL_OUT_WHITELIST = [
    "立案", "处罚", "诉讼", "问询函", "退市",
    "业绩预告", "预增", "预减", "扭亏",
    "中标", "重大合同", "框架协议", "订单",
    "收购", "重组", "增持", "解禁",
    "停产", "事故", "涨价", "提价", "降价",
    "定点", "认证", "战略合作", "专利",
]

# 池外例行公告排除词 (命中白名单但属例行/模板公告 → 噪声):
POOL_OUT_STOP = ["最近五年不存在", "权益分派", "转债", "可转债", "回售", "适当性", "质押"]

# 高风险词表 (v1.1: 去掉"减持"——减持计划/结果属常规, 不标⚠️ 防假阳性):
RISK_KEYWORDS = ["FCC", "禁令", "制裁", "立案", "处罚", "诉讼", "问询函",
                 "退市", "出口管制", "停产", "事故"]


def has_risk(text: str) -> bool:
    return any(k in text for k in RISK_KEYWORDS)

# 行业代码前缀 → 关键词组
FLASH_SOURCE = {"source": "CLS", "source_rank": "B"}      # 财联社 (聚合快讯)
ANNOUNCE_SOURCE = {"source": "CNINFO", "source_rank": "A"}  # 交易所公告 (巨潮)


def normalize_title(title: str) -> str:
    """标题归一化: 去空格/标点/常见前后缀 → 供 dedup 硬键。"""
    t = title
    for w in ["提示性公告", "进展公告", "的公告", "公告", "关于", "公司",
              "股份", "有限公司", "提示", "说明"]:
        t = t.replace(w, "")
    return re.sub(r"[\s，。、：:；;（）()【】\[\]·—-]+", "", t).lower()[:40]


def dedup_events(events: list[dict]) -> list[dict]:
    """v1.3 软去重: 同 (code, date, 归一化标题) → 合并 source 列表 + dedup_candidate 标记。

    只做同源同事件合并 (公告同文件多发的实证痛点); 跨源语义合并不做 ——
    宁重复看一次, 不错误合并两个不同事件 (投资系统原则)。
    """
    merged: dict[tuple, dict] = {}
    for e in events:
        code = str(e.get("code", "") or "")
        date = str(e.get("date", ""))[:10]
        key = (code, date, normalize_title(e.get("title", "")))
        if key not in merged:
            e["source_list"] = [e.get("source", "")]
            e["first_seen"] = date
            e["dedup_candidate"] = False
            merged[key] = e
        else:
            prev = merged[key]
            prev["source_list"] = sorted(set(prev.get("source_list", []) + [e.get("source", "")]))
            if e.get("date", "") > prev.get("last_seen", prev["date"]):
                prev["last_seen"] = e["date"]
            prev["dedup_candidate"] = True  # 软标记: 人工确认是否同一事件, 不自动删
    return list(merged.values())
    kws = []
    for prefix, groups in CODE_PREFIX_KEYWORDS.items():
        if code.startswith(prefix):
            for g in groups:
                kws += INDUSTRY_KEYWORDS.get(g, [])
    # 全量通用
    return list(dict.fromkeys(kws + INDUSTRY_KEYWORDS["通用"]))


def scan_announcements(codes: list[str], days: int = 10) -> tuple[list[dict], list[dict]]:
    """全市场公告一次拉取 → 分两路: (池内公告, 池外白名单高价值公告)。

    v1.1: 原逻辑只返回池内 (研究池是过去结果 → 池外盲区); 现在池外标题命中
    POOL_OUT_WHITELIST 的也进入 (排除例行公告噪声)。
    """
    import akshare as ak
    in_pool, out_pool = [], []
    today = datetime.now().strftime("%Y%m%d")
    try:
        df = ak.stock_notice_report(symbol="全部", date=today)
    except Exception:
        return in_pool, out_pool
    if df is None or df.empty or "代码" not in df.columns:
        return in_pool, out_pool
    code_set = {str(c).zfill(6) for c in codes}
    for _, r in df.iterrows():
        code = str(r["代码"]).zfill(6)
        title = str(r["公告标题"])
        risk = has_risk(title)
        base = {
            "date": str(r["公告日期"])[:10], "code": code,
            "name": str(r["名称"]), "type": "公告", "title": title[:150],
            "risk": risk, "e_category": classify_event(title),
            **ANNOUNCE_SOURCE,
        }
        if code in code_set:
            in_pool.append(base)
        elif any(kw in title for kw in POOL_OUT_WHITELIST) and \
                not any(s in title for s in POOL_OUT_STOP):
            out_pool.append(base)
    return in_pool, out_pool


def _hit_risk(text: str) -> bool:
    return has_risk(text)


def scan_flash(keywords: list[str]) -> tuple[list[dict], list[tuple]]:
    """快讯采集 v1.1: 双源覆盖。

    实测 (2026-09-04): CLS (财联社) 接口滚动窗口仅 ~20 条 (09:31-09:54) ——
    原 head(30) 截断的真凶是接口本身窗口小; EM (东财) 返回 ~200 条带链接。
    策略: EM 为主源 (窗口大+可溯源), CLS 为辅源 (实时滚动), 标题相似去重。

    返回 (命中事件列表, 当日热词 Top10)。
    """
    import akshare as ak
    all_kw = sorted({kw for grp in INDUSTRY_KEYWORDS.values() for kw in grp})
    cnt: Counter = Counter()
    em_events, cls_events = [], []

    try:
        df_em = ak.stock_info_global_em()
    except Exception:
        df_em = None
    if df_em is not None and not df_em.empty:
        for _, r in df_em.head(200).iterrows():
            text = str(r.get("标题", "")) + str(r.get("摘要", ""))
            hit = [kw for kw in keywords if kw in text]
            if hit:
                em_events.append({
                    "date": str(r.get("发布时间", ""))[:16], "code": "",
                    "type": "快讯", "title": text[:150],
                    "risk": _hit_risk(text),
                    "hit_kw": hit[:3], "e_category": classify_event(text),
                    "source": "EM", "source_rank": "B",
                    "source_url": str(r.get("链接", ""))[:200],
                })
            for kw in all_kw:
                if kw in text:
                    cnt[kw] += 1

    try:
        df_cls = ak.stock_info_global_cls(symbol="全部")
    except Exception:
        df_cls = None
    if df_cls is not None and not df_cls.empty:
        for _, r in df_cls.iterrows():
            text = str(r.get("标题", "")) + str(r.get("内容", ""))
            hit = [kw for kw in keywords if kw in text]
            if hit:
                cls_events.append({
                    "date": str(r.get("发布时间", ""))[:16], "code": "",
                    "type": "快讯", "title": text[:150],
                    "risk": _hit_risk(text),
                    "hit_kw": hit[:3], "e_category": classify_event(text),
                    **FLASH_SOURCE,
                })
            for kw in all_kw:
                if kw in text:
                    cnt[kw] += 1

    # 去重: CLS 标题与任一 EM 标题互相包含 → 弃 CLS (EM 带链接优先)
    em_keys = [e["title"][:60] for e in em_events]
    for e in cls_events:
        k = e["title"][:60]
        if not any(k in t or t in k for t in em_keys):
            em_events.append(e)
    return em_events, cnt.most_common(10)


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

    # 2. 采集 (一次公告接口分两路 + 快讯全量 + 热词)
    in_ann, out_ann = scan_announcements(codes)
    flash_kws = sum(INDUSTRY_KEYWORDS.values(), [])
    flash, top_kw = scan_flash(flash_kws)
    events = dedup_events(in_ann + out_ann + flash)
    n_dup = sum(1 for e in events if e.get("dedup_candidate"))
    print(f"事件: 池内公告 {len(in_ann)} + 池外白名单 {len(out_ann)} + 快讯 {len(flash)} "
          f"→ 去重后 {len(events)} 条 (软标记 {n_dup} 候选重复) | 热词 {len(top_kw)}")

    # 3. 保存
    today = datetime.now().strftime("%Y%m%d")
    path = f"{EVENT_DIR}/{today}_events.jsonl"
    with open(path, "w") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    # 4. 简报 (分区: 池内/池外/快讯/热词)
    brief_path = f"output/events_brief_{today}.md"
    lines = [f"# Market Intelligence Brief — {today}", "",
             f"**扫描池**: {len(codes)} 只 | **事件**: {len(events)} 条 "
             f"(池内 {len(in_ann)} / 池外高价值 {len(out_ann)} / 快讯 {len(flash)})",
             f"**高风险**: {sum(1 for e in events if e.get('risk'))} 条 ⚠️", ""]

    def _rows(evs, limit=25):
        out = []
        for e in sorted(evs, key=lambda x: str(x["date"]), reverse=True)[:limit]:
            risk = "⚠️" if e.get("risk") else ""
            hit = f" [{','.join(e.get('hit_kw', []))}]" if e.get("hit_kw") else ""
            out.append(f"| {e['date']} | {e.get('code','')} | {e.get('e_category','')} "
                       f"| {risk} | {e['title'][:70].replace('|','/')}{hit} |")
        return out

    lines += ["## 池内公告 (研究池)", "| 时间 | 代码 | E类 | 风险 | 标题 |", "|---|---|---|---|---|"]
    lines += _rows(in_ann) or ["(无)"]
    lines += ["", "## 池外高价值公告 (白名单, 非研究池)", "| 时间 | 代码 | E类 | 风险 | 标题 |", "|---|---|---|---|---|"]
    lines += _rows(out_ann) or ["(无)"]
    lines += ["", "## 快讯 (财联社全量过滤)", "| 时间 | E类 | 风险 | 标题 |", "|---|---|---|---|"]
    lines += _rows(flash) or ["(无)"]
    lines += ["", "## 当日热词 Top10 (快讯全量词频)", ""]
    if top_kw:
        lines += [f"{i+1}. **{kw}** ({n})" for i, (kw, n) in enumerate(top_kw)]
    else:
        lines += ["(无)"]
    lines.append("")
    with open(brief_path, "w") as f:
        f.write("\n".join(lines))
    print(f"已保存: {path}")
    print(f"简报: {brief_path} ({sum(1 for e in events if e.get('risk'))} 高风险)")


if __name__ == "__main__":
    main()

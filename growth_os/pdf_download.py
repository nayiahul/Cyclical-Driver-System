"""财报PDF下载 — 巨潮资讯网 (cninfo.com.cn)。

下载A股公司年报/半年报PDF，按 code/报告类型/ 组织存储。
"""
import os, re, time, requests
from pathlib import Path
from typing import Optional
from loguru import logger

PDF_ROOT = Path("data/financial_reports")
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "http://www.cninfo.com.cn/",
}
DOWNLOAD_DELAY = 0.5


def _get_orgid(code: str) -> tuple[str, str, str]:
    """从CNINFO获取真实orgId（股票代码≠orgId，需要查询映射）。"""
    try:
        url = "https://www.cninfo.com.cn/new/data/szse_stock.json"
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=15)
        if resp.status_code == 200:
            for s in resp.json().get("stockList", []):
                if s.get("code") == code:
                    return s["code"], s["orgId"], s.get("zwjc", code)
    except Exception:
        pass
    if code.startswith("6"):
        return code, f"gssh{code}", code
    return code, f"gssz{code}", code


def query_reports(code: str, years: list[int] = None,
                  report_types: list[str] = None) -> list[dict]:
    """查询巨潮资讯网，获取某只股票的报告列表。"""
    if years is None:
        import datetime
        current_year = datetime.date.today().year
        years = list(range(current_year - 2, current_year + 1))
    if report_types is None:
        report_types = ["半年度报告", "年度报告"]  # 半年度必须在年度之前，避免子串匹配

    _, org_id, name = _get_orgid(code)
    all_reports = []

    for year in years:
        try:
            url = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
            page = 1
            while True:
                params = {
                    "pageNum": page, "pageSize": 30,
                    "column": "szse" if code.startswith(("0", "2", "3")) else "sse",
                    "tabName": "fulltext",
                    "stock": f"{code},{org_id}",
                    "category": "category_ndbg_szsh;category_bndbg_szsh",
                    "seDate": f"{year}-01-01~{year}-12-31",
                    "sortName": "announcementTime", "sortType": "asc",
                    "isHLtitle": "true",
                }
                resp = requests.post(url, headers=REQUEST_HEADERS, data=params, timeout=30)
                if resp.status_code != 200:
                    break
                data = resp.json()
                anns = data.get("announcements") or []
                if not anns:
                    break

                for item in anns:
                    title = item.get("announcementTitle", "")
                    matched_type = None
                    for rt in report_types:
                        if rt in title:
                            matched_type = rt
                            break
                    skip = any(kw in title for kw in ["修订", "摘要", "英文", "更正", "补充"])
                    adjunct_url = item.get("adjunctUrl", "")
                    if not matched_type:
                        continue
                    if skip:
                        continue
                    if not adjunct_url:
                        continue

                    at = item.get("announcementTime", "")
                    disc_date = str(at)[:10] if at else ""
                    report_year = year
                    ym = re.search(r"(\d{4})", title)
                    if ym:
                        report_year = int(ym.group(1))
                    dl_url = f"https://static.cninfo.com.cn/{adjunct_url.lstrip('/')}"

                    all_reports.append({
                        "title": title,
                        "download_url": dl_url,
                        "disclosure_date": disc_date,
                        "report_year": report_year,
                        "report_type": matched_type,
                        "file_type": "pdf",
                        "category": "annual" if matched_type == "年度报告" else "semi_annual",
                    })
                page += 1
        except Exception as e:
            logger.debug(f"查询 {code} {year}年 失败: {e}")
            continue

    # 去重
    seen = set()
    unique = []
    for r in all_reports:
        key = (r["title"], r["disclosure_date"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    unique.sort(key=lambda r: r["disclosure_date"])
    return unique


def download_report(code: str, report: dict, force: bool = False) -> Optional[Path]:
    """下载单份PDF报告。"""
    if not report.get("download_url"):
        return None
    sub_dir = PDF_ROOT / code / report.get("category", "annual")
    sub_dir.mkdir(parents=True, exist_ok=True)
    year = report.get("report_year", 0)
    rtype = report.get("report_type", "年报").replace("/", "_")
    fpath = sub_dir / f"{code}_{year}年_{rtype}.pdf"

    if fpath.exists() and not force:
        return fpath
    try:
        resp = requests.get(report["download_url"], headers=REQUEST_HEADERS,
                            timeout=60, stream=True)
        if resp.status_code != 200:
            return None
        with open(fpath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.info(f"下载完成: {fpath.name}")
        return fpath
    except Exception as e:
        logger.warning(f"下载异常: {e}")
        return None


def download_reports_batch(code: str, years: list[int] = None,
                           force: bool = False) -> list[Path]:
    """批量下载某只股票的所有年报/半年报PDF。"""
    reports = query_reports(code, years)
    if not reports:
        logger.info(f"{code}: 未找到任何报告")
        return []
    downloaded = []
    for r in reports:
        fpath = download_report(code, r, force=force)
        if fpath:
            downloaded.append(fpath)
        time.sleep(DOWNLOAD_DELAY)
    return downloaded


def get_latest_report_path(code: str, report_type: str = "annual") -> Optional[Path]:
    """获取某只股票最新的已下载报告路径。"""
    sub_dir = PDF_ROOT / code / report_type
    if not sub_dir.exists():
        return None
    pdfs = sorted(sub_dir.glob("*.pdf"))
    return pdfs[-1] if pdfs else None


if __name__ == "__main__":
    import sys
    code = sys.argv[1] if len(sys.argv) > 1 else "600519"
    print(f"查询 {code} 报告...")
    reports = query_reports(code)
    for r in reports:
        print(f"  [{r['category']}] {r['report_year']}年 {r['title'][:50]}...")
    print(f"共 {len(reports)} 份")

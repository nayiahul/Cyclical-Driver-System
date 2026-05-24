"""财报PDF下载 — 巨潮资讯网 (cninfo.com.cn)。

下载A股公司年报/半年报PDF，按 code/报告类型/ 组织存储。
"""
import os, re, time, requests
from pathlib import Path
from typing import Optional
from loguru import logger

# 配置
PDF_ROOT = Path("data/financial_reports")
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "http://www.cninfo.com.cn/",
}
DOWNLOAD_DELAY = 0.5  # 下载间隔(秒)，避免被封


def _resolve_code(code: str) -> tuple[str, str]:
    """将6位代码转为CNINFO格式 (orgId, 市场代码)。"""
    if code.startswith("6") or code.startswith("5"):
        return code, "sh"
    elif code.startswith("0") or code.startswith("1"):
        return code, "sz"
    elif code.startswith("3"):
        return code, "sz"
    elif code.startswith("8") or code.startswith("4"):
        return code, "bj"
    return code, "sz"


def query_reports(code: str, years: list[int] = None,
                  report_types: list[str] = None) -> list[dict]:
    """查询巨潮资讯网，获取某只股票的报告列表。

    Args:
        code: 6位股票代码
        years: 年份列表，默认最近3年
        report_types: 报告类型，默认 ["年度报告", "半年度报告"]

    Returns:
        [{title, download_url, disclosure_date, report_year, report_type, file_type, category}]
    """
    if years is None:
        import datetime
        current_year = datetime.date.today().year
        years = list(range(current_year - 2, current_year + 1))

    if report_types is None:
        report_types = ["年度报告", "半年度报告"]

    org_id, market = _resolve_code(code)
    all_reports = []

    for year in years:
        try:
            url = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
            params = {
                "pageNum": 1,
                "pageSize": 30,
                "column": "szse",
                "tabName": "fulltext",
                "plate": "",
                "stock": f"{org_id},{market}",
                "searchkey": "",
                "secid": "",
                "category": "category_ndbg_szsh;category_bndbg_szsh",
                "trade": "",
                "seDate": f"{year}-01-01~{year}-12-31",
            }
            resp = requests.post(url, headers=REQUEST_HEADERS, data=params, timeout=15)
            data = resp.json()

            if "announcements" not in data:
                continue

            for item in data["announcements"]:
                title = item.get("announcementTitle", "")
                # 筛选报告类型
                matched_type = None
                for rt in report_types:
                    if rt in title:
                        matched_type = rt
                        break
                if not matched_type:
                    continue

                # 排除修订版/摘要/英文版
                skip_keywords = ["修订", "摘要", "英文", "更正", "补充"]
                if any(kw in title for kw in skip_keywords):
                    continue

                # 提取年份
                report_year = None
                year_match = re.search(r"(\d{4})", title)
                if year_match:
                    report_year = int(year_match.group(1))

                # 文件类型
                adjunct_url = item.get("adjunctUrl", "")
                file_type = "pdf"
                if adjunct_url.lower().endswith(".pdf"):
                    file_type = "pdf"
                elif adjunct_url.lower().endswith(".doc"):
                    file_type = "doc"

                # 分类
                category = "annual" if "年度" in matched_type else "semi_annual"

                dl_url = f"http://static.cninfo.com.cn/{adjunct_url}" if adjunct_url else ""

                all_reports.append({
                    "title": title,
                    "download_url": dl_url,
                    "disclosure_date": item.get("announcementTime", "")[:10],
                    "report_year": report_year or year,
                    "report_type": matched_type,
                    "file_type": file_type,
                    "category": category,
                })

        except Exception as e:
            logger.debug(f"查询 {code} {year}年 失败: {e}")
            continue

    # 去重 + 按披露日期排序
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
    """下载单份PDF报告。

    Args:
        code: 股票代码
        report: query_reports 返回的单条记录
        force: 是否强制覆盖已有文件

    Returns:
        文件路径，失败返回 None
    """
    if not report.get("download_url"):
        logger.warning(f"{code} 无下载链接: {report.get('title', '?')}")
        return None

    # 目标路径
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', code)
    year = report.get("report_year", 0)
    rtype = report.get("report_type", "年报").replace("/", "_")
    sub_dir = PDF_ROOT / code / report.get("category", "annual")
    sub_dir.mkdir(parents=True, exist_ok=True)

    fname = f"{safe_name}_{year}年_{rtype}.pdf"
    fpath = sub_dir / fname

    if fpath.exists() and not force:
        return fpath

    # 下载
    try:
        resp = requests.get(report["download_url"], headers=REQUEST_HEADERS,
                            timeout=60, stream=True)
        if resp.status_code != 200:
            logger.warning(f"下载失败 HTTP {resp.status_code}: {report['download_url'][:80]}")
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
    """批量下载某只股票的所有年报/半年报PDF。

    Returns:
        成功下载的文件路径列表
    """
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
    """获取某只股票最新的已下载报告路径。

    Args:
        code: 股票代码
        report_type: "annual" 或 "semi_annual"

    Returns:
        PDF文件路径，无则返回None
    """
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
        print(f"  [{r['category']}] {r['report_year']}年 {r['title'][:50]}... "
              f"日期={r['disclosure_date']}")
    print(f"共 {len(reports)} 份")

"""申万2024一级行业映射"""
import os

import akshare as ak
import pandas as pd
from loguru import logger

SW_INDUSTRY_CACHE = "data/cache/sw_industry_map.csv"

# 申万2021版 31个一级行业指数代码
SW_CODES = {
    "801010": "农林牧渔", "801020": "煤炭", "801030": "化工",
    "801040": "钢铁", "801050": "有色金属", "801080": "电子",
    "801110": "家用电器", "801120": "食品饮料", "801130": "纺织服饰",
    "801140": "轻工制造", "801150": "医药生物", "801160": "公用事业",
    "801170": "交通运输", "801180": "房地产", "801200": "商贸零售",
    "801210": "社会服务", "801230": "综合", "801710": "建筑材料",
    "801720": "建筑装饰", "801730": "电力设备", "801740": "国防军工",
    "801750": "计算机", "801760": "传媒", "801770": "通信",
    "801780": "银行", "801790": "非银金融", "801880": "汽车",
    "801890": "机械设备", "801960": "石油石化", "801970": "环保",
    "801980": "美容护理",
}


def get_sw_industry() -> dict[str, str]:
    """
    返回 {stock_code: sw_industry_name} 映射。

    缓存优先。首次调用遍历31个申万行业指数获取成分股。
    """
    if os.path.exists(SW_INDUSTRY_CACHE):
        df = pd.read_csv(SW_INDUSTRY_CACHE, dtype={"code": str, "industry": str})
        return dict(zip(df["code"], df["industry"]))

    mapping: dict[str, str] = {}
    for sw_code, industry_name in SW_CODES.items():
        try:
            df = ak.index_stock_cons(symbol=sw_code)
            for _, row in df.iterrows():
                code = str(row["品种代码"]).zfill(6)
                if code not in mapping:
                    mapping[code] = industry_name
            logger.debug(f"{industry_name}({sw_code}): {len(df)} stocks")
        except Exception as e:
            logger.warning(f"获取 {industry_name}({sw_code}) 成分股失败: {e}")

    cache_df = pd.DataFrame(
        [{"code": k, "industry": v} for k, v in mapping.items()]
    )
    os.makedirs(os.path.dirname(SW_INDUSTRY_CACHE), exist_ok=True)
    cache_df.to_csv(SW_INDUSTRY_CACHE, index=False)
    logger.info(f"申万行业映射已缓存: {len(mapping)} 只股票, {len(SW_CODES)} 个行业")
    return mapping

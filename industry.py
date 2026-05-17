"""申万行业映射 — Sina源，覆盖L1/L2/L3全部行业"""
import os

import pandas as pd
from loguru import logger

_STOCK_MAP_CACHE = "data/cache/sw_stock_industry.csv"
_HIERARCHY_CACHE = "data/cache/sw_hierarchy.csv"

# 内存缓存
_map_l1: dict[str, str] | None = None
_map_l2: dict[str, str] | None = None
_map_l3: dict[str, str] | None = None


def _load_maps():
    """加载三级映射到内存"""
    global _map_l1, _map_l2, _map_l3
    if _map_l1 is not None:
        return
    if not os.path.exists(_STOCK_MAP_CACHE):
        logger.warning(f"{_STOCK_MAP_CACHE} 不存在，请先运行 sw_classify.py 生成")
        _map_l1 = _map_l2 = _map_l3 = {}
        return
    df = pd.read_csv(_STOCK_MAP_CACHE, dtype={"code": str})
    _map_l1 = dict(zip(df["code"], df["sw1"]))
    _map_l2 = dict(zip(df["code"], df["sw2"]))
    _map_l3 = dict(zip(df["code"], df["sw3"]))
    logger.info(f"申万行业映射已加载: {len(_map_l1)} 只股票 (L1/L2/L3)")


def get_sw_industry() -> dict[str, str]:
    """返回 {code: sw_level1_name} 映射"""
    _load_maps()
    return _map_l1 or {}


def get_sw_industry_l2() -> dict[str, str]:
    """返回 {code: sw_level2_name} 映射"""
    _load_maps()
    return _map_l2 or {}


def get_sw_industry_l3() -> dict[str, str]:
    """返回 {code: sw_level3_name} 映射"""
    _load_maps()
    return _map_l3 or {}

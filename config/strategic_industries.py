"""国家战略发展方向行业映射 — 人工维护的策略层 overlay

═══ 为什么这个文件存在 ═══
申万三级行业是描述性的（"这家公司做什么"），不是判断性的（"这个方向重不重要"）。
系统无法自动判断"通信网络设备及器件"比"煤炭开采"更值得战略倾斜——这是政策判断。
此文件叠加在申万分类之上，决定哪些行业享受战略池优待（降 moat 权重、放宽 S1 阈值、保底名额）。

═══ 什么时候需要更新 ═══
1. 每季度财报季后：检查新上市公司的 SW3 是否在映射中
2. 重大政策发布时：如国家大基金三期投向、新质生产力目录更新
3. 运行 `python -m screener` 时：检查日志中的覆盖缺口警告
4. 发现 Top 20 中重要标的系统性缺席时（如光模块龙头未出现 → 检查其 SW3 是否在 STRATEGIC_INDUSTRIES）

═══ 如何更新 ═══
1. 确认标的的申万三级行业名：查看 data/cache/sw_hierarchy.csv 的 l3_name 列
2. 在 STRATEGIC_INDUSTRIES 中新增/修改对应条目
3. 标签规则：
   - "核心战略": 六大方向中直接涉及国家战略的（芯片设计/光模块/AI软件/创新药等）
   - "国产替代": 技术自主可控需求强烈（半导体设备/材料/高端机床等）
   - "新兴成长": 产业初期高增速（低空经济/商业航天/燃料电池/机器人等）
   - "绿色转型": 碳中和相关（光伏/风电/储能/锂电/电网等）
   - "数字经济": 数字化转型（云计算/大数据/金融科技等）
4. 运行 `python -m screener` 验证：检查日志中的覆盖报告

═══ 数据源 ═══
六大科技方向 × 申万2021版三级行业（与 streamlit项目01/components/six_directions.py 同步）
SW3名称对应 data/cache/sw_hierarchy.csv 中的 l3_name（含Ⅲ后缀的原样保留）

═══ 标签体系 ═══
- 核心战略: 国家明确列为优先发展方向
- 新兴成长: 产业初期，高增速
- 国产替代: 技术自主可控需求
- 绿色转型: 碳中和相关
- 数字经济: 数字化转型相关
"""

# {SW3行业名称: [标签列表]}
# 组织方式: 六大科技方向 → 细分赛道 → SW3
STRATEGIC_INDUSTRIES = {
    # ═══════════════════════════════════════════════
    # 方向一：AI全产业链（算力基建 + 大模型 + 智能终端）
    # ═══════════════════════════════════════════════
    # GPU/AI芯片/存储芯片
    "数字芯片设计":       ["核心战略", "国产替代"],
    "模拟芯片设计":       ["核心战略", "国产替代"],
    "集成电路制造":       ["核心战略", "国产替代"],
    "分立器件":           ["国产替代"],
    # 光模块/光通信
    "通信网络设备及器件":  ["核心战略", "国产替代"],
    "通信线缆及配套":      ["国产替代"],
    "通信终端及配件":      ["数字经济"],  # IoT模组/企业通信终端
    # PCB/被动元件
    "印制电路板":         ["国产替代"],
    "被动元件":           ["国产替代"],
    # 数据中心/IDC/服务器
    "IT服务Ⅲ":           ["数字经济"],
    "其他计算机设备":      ["数字经济"],
    "通信应用增值服务":    ["数字经济"],
    # 大模型软件/AI应用
    "垂直应用软件":       ["数字经济"],
    "横向通用软件":       ["核心战略", "数字经济"],
    # 消费电子（AI终端）
    "品牌消费电子":       ["数字经济"],
    "消费电子零部件及组装": ["数字经济"],
    "光学元件":           ["核心战略", "国产替代"],
    # 人形机器人（电控/传感外溢）
    "机器人":             ["核心战略", "新兴成长"],
    "工控设备":           ["国产替代"],
    "激光设备":           ["国产替代"],
    # 自动驾驶
    "汽车电子电气系统":    ["新兴成长"],
    "电动乘用车":         ["新兴成长"],

    # ═══════════════════════════════════════════════
    # 方向二：电力与新能源（"新石油"能源底座）
    # ═══════════════════════════════════════════════
    # 发电运营
    "火力发电":           ["绿色转型"],
    "水力发电":           ["绿色转型"],
    "核力发电":           ["绿色转型"],
    "风力发电":           ["核心战略", "绿色转型"],
    "光伏发电":           ["核心战略", "绿色转型"],
    "其他能源发电":        ["绿色转型"],
    "电能综合服务":        ["绿色转型"],
    # 储能/锂电/氢能
    "锂电池":             ["核心战略", "绿色转型"],
    "电池化学品":          ["绿色转型"],
    "锂电专用设备":        ["绿色转型"],
    "蓄电池及其他电池":    ["绿色转型"],
    "燃料电池":           ["新兴成长", "绿色转型"],
    # 风光装备
    "风电整机":           ["核心战略", "绿色转型"],
    "风电零部件":          ["绿色转型"],
    "光伏电池组件":        ["核心战略", "绿色转型"],
    "逆变器":             ["核心战略", "绿色转型"],
    "光伏辅材":           ["绿色转型"],
    "光伏加工设备":        ["绿色转型"],
    "硅料硅片":           ["绿色转型"],
    # 特高压/电网改造
    "输变电设备":          ["绿色转型"],
    "配电设备":           ["绿色转型"],
    "电网自动化设备":       ["绿色转型"],
    "电工仪器仪表":        ["绿色转型"],
    "线缆部件及其他":       ["绿色转型"],
    # 上游资源
    "铜":                ["绿色转型"],
    "锂":                ["核心战略", "绿色转型"],
    "钴":                ["绿色转型"],
    "镍":                ["绿色转型"],
    "稀土":               ["核心战略"],
    "磁性材料":           ["绿色转型"],

    # ═══════════════════════════════════════════════
    # 方向三：芯片半导体（国产替代"骨"支撑）
    # ═══════════════════════════════════════════════
    "半导体设备":          ["核心战略", "国产替代"],
    "半导体材料":          ["核心战略", "国产替代"],
    "电子化学品Ⅲ":        ["国产替代"],
    "集成电路封测":        ["核心战略"],
    # (数字芯片设计/模拟芯片设计/集成电路制造 已在方向一)

    # ═══════════════════════════════════════════════
    # 方向四：机器人与高端制造
    # ═══════════════════════════════════════════════
    "电机Ⅲ":             ["国产替代"],
    "仪器仪表":           ["国产替代"],
    "其他电子Ⅲ":          ["国产替代"],
    "机床工具":           ["核心战略", "国产替代"],
    "其他自动化设备":      ["国产替代"],
    "金属制品":           ["国产替代"],
    # (机器人/工控设备/激光设备 已在方向一)

    # ═══════════════════════════════════════════════
    # 方向五：生命科学 + AI
    # ═══════════════════════════════════════════════
    "化学制剂":           ["新兴成长"],  # 含仿制药，范围太宽，降级
    "其他生物制品":        ["核心战略"],
    "疫苗":              ["核心战略"],
    "血液制品":           ["核心战略"],
    "原料药":             ["国产替代"],
    "医疗研发外包":        ["新兴成长"],
    "医疗设备":           ["核心战略", "国产替代"],
    "医疗耗材":           ["国产替代"],
    "体外诊断":           ["国产替代"],
    "医药流通":           ["数字经济"],
    "线下药店":           ["数字经济"],
    # (垂直应用软件 已在方向一，AI制药/医疗信息化)

    # ═══════════════════════════════════════════════
    # 方向六：商业航天与低空经济
    # ═══════════════════════════════════════════════
    "航天装备Ⅲ":          ["核心战略", "新兴成长"],
    "航空装备Ⅲ":          ["核心战略", "新兴成长"],
    "其他运输设备":        ["新兴成长"],
    "基建市政工程":        ["新兴成长"],
    "其他专业工程":        ["新兴成长"],
    "通信工程及服务":       ["新兴成长"],
    "军工电子Ⅲ":          ["核心战略"],
    "航空运输":           ["新兴成长"],
    "机场":              ["新兴成长"],

    # ═══════════════════════════════════════════════
    # 传统高端制造（六大方向外溢）
    # ═══════════════════════════════════════════════
    "工程机械整机":        ["国产替代"],  # 传统基建周期，非科技前沿
    "工程机械器件":        ["国产替代"],
}

# 已人工审查、确认不需加入映射的 SW3（"其他"兜底分类等）
# 在 validate_strategic_mapping 中会被跳过，不再重复告警
KNOWN_FALSE_POSITIVES: set[str] = {
    "其他通信设备",  # "其他"兜底分类，成分混杂
}

# 标签权重加成 (加到 inflection_score)
TAG_BONUS = {
    "核心战略": 0.15,
    "国产替代": 0.10,
    "新兴成长": 0.08,
    "绿色转型": 0.05,
    "数字经济": 0.05,
}


def get_strategic_tags(sw3_name: str) -> list[str]:
    """查询某SW3行业的战略标签"""
    return STRATEGIC_INDUSTRIES.get(sw3_name, [])


# 六大战略方向核心 SW3 集合（带"核心战略"标签的行业）
STRATEGIC_CORE_SW3: set[str] = {
    sw3 for sw3, tags in STRATEGIC_INDUSTRIES.items()
    if "核心战略" in tags
}

# composite 中的战略加成权重
STRATEGIC_COMPOSITE_BONUS = 0.03  # 轻量加成，不扭曲排序


def is_strategic_core(sw3_name: str) -> bool:
    """判断 SW3 行业是否属于六大战略方向核心"""
    return sw3_name in STRATEGIC_CORE_SW3


def get_strategic_bonus(sw3_name: str) -> float:
    """计算战略标签加成（取最高标签，非累加）"""
    tags = get_strategic_tags(sw3_name)
    if not tags:
        return 0.0
    return max(TAG_BONUS.get(t, 0) for t in tags)


# ═══════════════════════════════════════════════════════════
# 自检与诊断
# ═══════════════════════════════════════════════════════════

def validate_strategic_mapping(candidate_sw3: set[str] = None,
                               verbose: bool = True) -> dict:
    """
    验证 STRATEGIC_INDUSTRIES 映射的完整性和时效性。

    检查项:
    1. 映射中的 SW3 名是否在实际数据中存在（防命名漂移）
    2. 候选池中有多少 SW3 未被映射（覆盖缺口）
    3. 候选池中未被映射的标的数量和占比

    Args:
        candidate_sw3: 当前候选池中出现的 SW3 集合（可选，用于覆盖报告）
        verbose: 是否通过 logger 输出

    Returns:
        {stale_entries, unmapped_sw3, unmapped_count, coverage_pct}
    """
    import os as _os
    import pandas as _pd
    from loguru import logger as _logger

    result = {"stale_entries": [], "unmapped_sw3": [], "ok": True}

    # 1. 加载实际 SW3 数据，检查映射中的名字是否存在于数据中
    hier_path = "data/cache/sw_hierarchy.csv"
    if _os.path.exists(hier_path):
        hier = _pd.read_csv(hier_path, dtype={"l3_name": str})
        all_sw3 = set(hier["l3_name"].dropna().unique())

        stale = [n for n in STRATEGIC_INDUSTRIES if n not in all_sw3]
        if stale:
            result["stale_entries"] = stale
            result["ok"] = False
            if verbose:
                _logger.warning(
                    f"战略映射中有 {len(stale)} 个 SW3 名不在 sw_hierarchy.csv 中（可能已改名）: "
                    f"{stale[:10]}{'...' if len(stale) > 10 else ''}"
                )
    else:
        all_sw3 = set()

    # 2. 候选池覆盖缺口
    if candidate_sw3 and all_sw3:
        unmapped = sorted(candidate_sw3 - set(STRATEGIC_INDUSTRIES.keys()))
        mapped = candidate_sw3 & set(STRATEGIC_INDUSTRIES.keys())
        coverage = len(mapped) / len(candidate_sw3) * 100 if candidate_sw3 else 100

        result["unmapped_sw3"] = unmapped
        result["coverage_pct"] = round(coverage, 1)
        result["mapped_count"] = len(mapped)
        result["total_count"] = len(candidate_sw3)

        if verbose and unmapped:
            # 过滤已知排除项后，报告可能重要但未映射的
            suspicious = [
                n for n in unmapped
                if n not in KNOWN_FALSE_POSITIVES
                and any(kw in n for kw in [
                    "芯片", "半导体", "集成电路", "光模块",
                    "软件", "通信", "电子",
                    "医药", "生物", "制药",
                    "航空", "航天", "机器人", "智能",
                    "数据", "云", "算力",
                    "新能源", "储能", "电池", "光伏", "风电", "核电",
                    "军工", "卫星", "低空",
                ])
            ]
            if suspicious:
                _logger.warning(
                    f"覆盖缺口: 候选池中 {len(suspicious)} 个疑似相关 SW3 未在战略映射中: "
                    f"{suspicious[:15]}{'...' if len(suspicious) > 15 else ''}"
                )
                _logger.info(
                    f"  如需加入，编辑 config/strategic_industries.py → STRATEGIC_INDUSTRIES 字典"
                )
            _logger.info(
                f"战略映射覆盖率: {coverage:.0f}% "
                f"({result['mapped_count']}/{result['total_count']} 个 SW3 已映射) "
                f"→ config/strategic_industries.py"
            )

    # 3. 映射完备性: 所有已映射 SW3 的标签分布
    if verbose:
        from collections import Counter as _Counter
        all_tags = [t for tags in STRATEGIC_INDUSTRIES.values() for t in tags]
        tag_dist = _Counter(all_tags)
        _logger.info(
            f"config/strategic_industries.py — "
            f"{len(STRATEGIC_INDUSTRIES)} 个 SW3, "
            f"{len(STRATEGIC_CORE_SW3)} 个核心 | "
            f"标签分布: {dict(tag_dist)}"
        )

    return result

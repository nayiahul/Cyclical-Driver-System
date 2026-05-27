"""决策矩阵可视化 — Q(质量)×V(估值) 散点图。"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# 中文字体
_cjk_font = None
for f in fm.fontManager.ttflist:
    if any(k in f.name.lower() for k in ["songti", "heiti", "cjk", "noto", "wqy", "pingfang"]):
        _cjk_font = f.fname
        break
if _cjk_font:
    fm.fontManager.addfont(_cjk_font)
    plt.rcParams["font.family"] = fm.FontProperties(fname=_cjk_font).get_name()


def plot_decision_matrix(pool_path: str, output_path: str = None):
    """读取筛选池CSV，画Q×V四象限散点图。

    Args:
        pool_path: growth_pool_YYYYMMDD.csv 路径
        output_path: 输出PNG路径，默认同名.png
    """
    if output_path is None:
        output_path = pool_path.replace(".csv", "_matrix.png")

    df = pd.read_csv(pool_path)
    if "quality_score" not in df.columns or len(df) < 5:
        return None

    q = df["quality_score"].values
    v = df["score_l5"].fillna(0).values
    codes = df["code"].astype(str).values
    names = df.get("name", codes).values
    l5s = df.get("l5_status", pd.Series(["ok"] * len(df))).values

    fig, ax = plt.subplots(figsize=(10, 8))

    # 颜色：L5 OK绿色，PARTIAL橙色，MISSING灰色
    colors = []
    for s in l5s:
        if s == "ok": colors.append("#2ecc71")
        elif s == "partial": colors.append("#f39c12")
        else: colors.append("#bdc3c7")

    ax.scatter(q, v, c=colors, s=50, alpha=0.7, edgecolors="white", linewidth=0.5)

    # 标注 Top 10
    top_idx = np.argsort(q)[-10:]
    for i in top_idx:
        ax.annotate(str(names[i])[:4], (q[i], v[i]),
                    fontsize=7, ha="center", va="bottom",
                    bbox=dict(boxstyle="round,pad=0.1", facecolor="white", alpha=0.7))

    # 象限线
    ax.axhline(y=5, color="#e74c3c", linestyle="--", alpha=0.5, label="估值中线 (5/10)")
    ax.axvline(x=65, color="#3498db", linestyle="--", alpha=0.5, label="质量中线 (65/100)")

    # 象限标签
    ax.text(85, 9, "🟢 核心持仓", fontsize=11, ha="center", color="#27ae60", fontweight="bold")
    ax.text(85, 2, "🟡 优质但偏贵", fontsize=10, ha="center", color="#e67e22")
    ax.text(45, 9, "🟡 便宜待研究", fontsize=10, ha="center", color="#2980b9")
    ax.text(45, 2, "🔴 回避区", fontsize=10, ha="center", color="#c0392b")

    ax.set_xlabel("成长质量 Q (L1-L4)", fontsize=12)
    ax.set_ylabel("估值安全边际 V (L5)", fontsize=12)
    ax.set_title(f"Growth OS 决策矩阵 — {len(df)} 只股票", fontsize=14, fontweight="bold")
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.5, 10.5)
    ax.legend(loc="lower left", fontsize=8)
    ax.grid(True, alpha=0.2)

    # 统计
    n_core = ((q >= 65) & (v >= 5)).sum()
    n_rich = ((q >= 65) & (v < 5)).sum()
    n_cheap = ((q < 65) & (v >= 5)).sum()
    stats = f"核心持仓:{n_core} | 优质偏贵:{n_rich} | 便宜待研:{n_cheap}"
    ax.text(0.5, -0.06, stats, transform=ax.transAxes, fontsize=9,
            ha="center", color="gray")

    plt.tight_layout()
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    fig.savefig(output_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return output_path


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "output/growth_pool_20260525.csv"
    out = plot_decision_matrix(path)
    print(f"Saved: {out}")

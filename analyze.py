"""
GPU租赁价格 — 信号分析模块
============================
读取 data/gpu_prices.csv 的时间序列,输出拐点判断。

核心信号(对应库存周期框架):
  1. 价格趋势: 近30天 vs 前30天的中位价变化
  2. 供给趋势: 可租GPU数量的变化(代理"利用率"的反面)
  3. 关键拐点: 价格↓ + 供给↑ 同时出现 = 从"主动补库存"滑向"被动补库存"
  4. 折旧剪刀差: 旧卡(H100)与新卡(B200)价格比,反映残值崩塌速度

依赖: 仅标准库(csv, statistics)
用法: python analyze.py
"""

import csv
import os
import statistics
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CSV_PATH = os.path.join(DATA_DIR, "gpu_prices.csv")


def load():
    if not os.path.exists(CSV_PATH):
        return [], []
    with open(CSV_PATH, newline="") as f:
        rows = list(csv.reader(f))
    if len(rows) < 2:
        return rows[0] if rows else [], []
    return rows[0], rows[1:]


def col(header, rows, name):
    """取某列的 (date, value) 序列,跳过空值。"""
    if name not in header:
        return []
    idx = header.index(name)
    out = []
    for r in rows:
        if len(r) > idx and r[idx] not in ("", None):
            try:
                out.append((r[0], float(r[idx])))
            except ValueError:
                pass
    return out


def trend(series, window=30):
    """
    比较最近 window 天均值 vs 前一个 window 天均值。
    返回 (变化百分比, 方向描述) 或 None。
    """
    if len(series) < 4:
        return None
    vals = [v for _, v in series]
    recent = vals[-window:] if len(vals) >= window else vals[len(vals)//2:]
    prior = vals[-2*window:-window] if len(vals) >= 2*window else vals[:len(vals)//2]
    if not prior or not recent:
        return None
    r_avg, p_avg = statistics.mean(recent), statistics.mean(prior)
    if p_avg == 0:
        return None
    pct = (r_avg - p_avg) / p_avg * 100
    return pct


def analyze():
    header, rows = load()
    if not rows:
        print("还没有数据。先运行 fetch_vast.py 积累几天的数据。")
        print("(单点数据无法判断趋势,建议至少连续运行 2 周)")
        return

    print("=" * 60)
    print(f"GPU 租赁价格信号分析  |  数据点: {len(rows)} 天")
    print(f"区间: {rows[0][0]} → {rows[-1][0]}")
    print("=" * 60)

    # ── 各型号价格趋势 ──
    print("\n【价格趋势】(负=降价,正=涨价)")
    for gpu in ["H100", "H200", "B200", "A100"]:
        series = col(header, rows, f"{gpu}_median")
        t = trend(series)
        if t is None:
            print(f"  {gpu:8s}  数据不足")
            continue
        latest = series[-1][1]
        arrow = "↓" if t < -2 else ("↑" if t > 2 else "→")
        print(f"  {gpu:8s}  最新 ${latest:.3f}/h   趋势 {arrow} {t:+.1f}%")

    # ── 供给趋势(利用率的反面) ──
    print("\n【供给趋势】可租GPU数量变化(供给↑可能意味需求跟不上)")
    for gpu in ["H100", "H200", "B200"]:
        series = col(header, rows, f"{gpu}_gpus")
        t = trend(series)
        if t is None:
            print(f"  {gpu:8s}  数据不足")
            continue
        latest = int(series[-1][1])
        arrow = "↑" if t > 5 else ("↓" if t < -5 else "→")
        print(f"  {gpu:8s}  当前可租 {latest:5d} 张   趋势 {arrow} {t:+.1f}%")

    # ── 核心拐点判断 ──
    print("\n【拐点信号】" + "—" * 40)
    h100_price = trend(col(header, rows, "H100_median"))
    h100_supply = trend(col(header, rows, "H100_gpus"))

    if h100_price is not None and h100_supply is not None:
        if h100_price < -5 and h100_supply > 10:
            print("  ⚠️  危险: H100 价格下跌 + 供给上升")
            print("      → 需求可能跟不上产能,'被动补库存'特征显现")
            print("      → 这是从补库存滑向去库存的早期拐点")
        elif h100_price < -5 and h100_supply < 0:
            print("  ✓  良性: 价格下跌但供给收缩")
            print("      → 降价被需求消化,属于健康的成本下降")
        elif h100_price > 5:
            print("  ✓  强势: 价格上升,需求旺盛,补库存合理")
        else:
            print("  →  中性: 价格供给均无明显方向,观察中")
    else:
        print("  数据不足以判断拐点(需要至少 4 周连续数据)")

    # ── 折旧剪刀差 ──
    print("\n【折旧剪刀差】旧卡残值 vs 新卡")
    h100 = col(header, rows, "H100_median")
    b200 = col(header, rows, "B200_median")
    if h100 and b200:
        ratio = h100[-1][1] / b200[-1][1] if b200[-1][1] else 0
        print(f"  H100/B200 价格比 = {ratio:.2f}")
        print(f"  (比值持续走低 = H100 残值在崩塌,持有大量H100的公司资产承压)")
    else:
        print("  B200 数据不足,暂无法计算")

    print("\n" + "=" * 60)
    print("提示: 真正的拐点信号 = 价格↓ + 供给↑ + 厂商capex仍在上调")
    print("     三者同时出现时,通常领先财报营收放缓 1-2 个季度")
    print("=" * 60)


if __name__ == "__main__":
    analyze()

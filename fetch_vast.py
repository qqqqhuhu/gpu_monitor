"""
GPU租赁价格监测器 — Vast.ai 数据抓取模块
=========================================
抓取 Vast.ai 公开市场的 GPU 现货挂单,提取价格与供需信号。

核心思路(对应投资框架):
  - 不只记录价格,还记录"利用率代理",因为:
      价格跌 + 利用率高 = 良性(供给增加,需求消化得了) → 补库存合理
      价格跌 + 利用率低 = 恶性(需求退潮,GPU闲置)     → 滑向去库存
  - 记录价格离散度(中位数 vs 最低价),反映市场结构

依赖: requests  (pip install requests)
用法: python fetch_vast.py
输出: 追加一行到 data/gpu_prices.csv
"""

import requests
import csv
import json
import os
import statistics
from datetime import datetime, timezone

# ── 配置 ────────────────────────────────────────────────
# Vast.ai 公开 bundles 端点,无需 API key
VAST_API = "https://console.vast.ai/api/v0/bundles/"

# 要监测的 GPU 型号(Vast.ai 的命名)
TARGET_GPUS = ["H100", "H200", "B200", "RTX 4090", "A100"]

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CSV_PATH = os.path.join(DATA_DIR, "gpu_prices.csv")

# 请求头,模拟正常浏览器,降低被拦概率
HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
}


def fetch_offers():
    """
    拉取 Vast.ai 当前所有可租 GPU 挂单。
    返回原始 offers 列表;失败抛异常由上层处理。
    """
    # Vast 支持用查询参数过滤,这里只取可租(rentable)的实例
    params = {"q": json.dumps({
        "rentable": {"eq": True},
        "rented": {"eq": False},
        "order": [["dph_total", "asc"]],   # 按总价升序
        "limit": 5000,
    })}
    resp = requests.get(VAST_API, params=params, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    return data.get("offers", [])


def summarize(offers):
    """
    把原始挂单聚合成每个型号的信号指标。
    返回 dict: { 'H100': {price_median, price_min, count, ...}, ... }
    """
    result = {}
    for gpu in TARGET_GPUS:
        # 匹配该型号的挂单(gpu_name 字段做模糊包含匹配)
        matched = [
            o for o in offers
            if gpu.replace(" ", "").lower() in o.get("gpu_name", "").replace(" ", "").lower()
        ]
        if not matched:
            result[gpu] = None
            continue

        # 关键: 计算"每卡每小时"价格 = 总价 / GPU数量
        # dph_total 是整个实例的时价, num_gpus 是卡数
        per_gpu_prices = []
        total_gpus = 0
        for o in matched:
            n = o.get("num_gpus", 1) or 1
            dph = o.get("dph_total")
            if dph and n:
                per_gpu_prices.append(dph / n)
                total_gpus += n

        if not per_gpu_prices:
            result[gpu] = None
            continue

        per_gpu_prices.sort()
        result[gpu] = {
            "price_median": round(statistics.median(per_gpu_prices), 4),
            "price_min": round(min(per_gpu_prices), 4),
            "price_p25": round(per_gpu_prices[len(per_gpu_prices) // 4], 4),
            # 离散度: 中位数/最低价, 越大说明市场分化越严重(可能有人在甩卖)
            "price_dispersion": round(statistics.median(per_gpu_prices) / min(per_gpu_prices), 3),
            # 供给代理: 当前可租的该型号实例数 与 总GPU数
            "offer_count": len(matched),
            "available_gpus": total_gpus,
        }
    return result


def append_csv(summary):
    """把本次结果追加为 CSV 的一行(宽表: 每个型号几列)。"""
    os.makedirs(DATA_DIR, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 构造表头与行
    header = ["date"]
    row = [today]
    for gpu in TARGET_GPUS:
        key = gpu.replace(" ", "")
        header += [f"{key}_median", f"{key}_min", f"{key}_dispersion",
                   f"{key}_offers", f"{key}_gpus"]
        s = summary.get(gpu)
        if s:
            row += [s["price_median"], s["price_min"], s["price_dispersion"],
                    s["offer_count"], s["available_gpus"]]
        else:
            row += ["", "", "", "", ""]

    file_exists = os.path.exists(CSV_PATH)
    # 防重复: 如果今天已经写过,先读出来去重(简单实现: 跳过同日期)
    if file_exists:
        with open(CSV_PATH, newline="") as f:
            existing = [r for r in csv.reader(f)]
        existing = [r for r in existing if r and r[0] != today]  # 去掉今天的旧记录
        with open(CSV_PATH, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(existing[1:] if existing and existing[0][0] == "date" else existing)
            w.writerow(row)
    else:
        with open(CSV_PATH, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerow(row)


def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] 开始抓取 Vast.ai ...")
    try:
        offers = fetch_offers()
        print(f"  ✓ 拿到 {len(offers)} 条挂单")
    except Exception as e:
        print(f"  ✗ 抓取失败: {e}")
        print("  → 保留历史数据,本次跳过(不写入空行)")
        return 1

    summary = summarize(offers)
    print("\n  各型号信号:")
    for gpu, s in summary.items():
        if s:
            print(f"    {gpu:10s}  中位 ${s['price_median']:.3f}/h  "
                  f"最低 ${s['price_min']:.3f}  离散 {s['price_dispersion']:.2f}  "
                  f"挂单 {s['offer_count']}  可租GPU {s['available_gpus']}")
        else:
            print(f"    {gpu:10s}  (无挂单)")

    append_csv(summary)
    print(f"\n  ✓ 已写入 {CSV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

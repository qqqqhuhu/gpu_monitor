"""
GPU租赁价格 — HTML看板生成器
============================
读取 data/gpu_prices.csv,生成一个自包含的 HTML 看板(可直接浏览器打开)。
依赖: 仅标准库。图表用 Chart.js (CDN)。
用法: python make_dashboard.py  →  生成 dashboard.html
"""

import csv
import os
import json

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CSV_PATH = os.path.join(DATA_DIR, "gpu_prices.csv")
OUT = os.path.join(os.path.dirname(__file__), "dashboard.html")


def load():
    if not os.path.exists(CSV_PATH):
        return [], []
    with open(CSV_PATH, newline="") as f:
        rows = list(csv.reader(f))
    return (rows[0], rows[1:]) if len(rows) > 1 else ([], [])


def series(header, rows, name):
    if name not in header:
        return []
    i = header.index(name)
    out = []
    for r in rows:
        if len(r) > i and r[i] not in ("", None):
            try:
                out.append(float(r[i]))
            except ValueError:
                out.append(None)
        else:
            out.append(None)
    return out


def main():
    header, rows = load()
    if not rows:
        print("无数据,先运行 fetch_vast.py")
        return
    dates = [r[0] for r in rows]
    price_data = {g: series(header, rows, f"{g}_median") for g in ["H100", "H200", "B200", "A100"]}
    supply_data = {g: series(header, rows, f"{g}_gpus") for g in ["H100", "H200", "B200"]}

    html = """<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GPU租赁价格看板</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500&display=swap');
*{box-sizing:border-box;margin:0;padding:0}
body{background:#09090f;color:#e2e2ee;font-family:'IBM Plex Sans',sans-serif;padding:20px;font-size:13px}
h1{font-family:'IBM Plex Mono',monospace;font-size:16px;margin-bottom:4px}
.sub{color:#6060a0;font-family:'IBM Plex Mono',monospace;font-size:11px;margin-bottom:20px}
.card{background:#111118;border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:18px;margin-bottom:12px}
.ct{font-family:'IBM Plex Mono',monospace;font-size:10px;color:#6060a0;text-transform:uppercase;letter-spacing:.5px;margin-bottom:14px}
</style></head><body>
<h1>GPU 租赁价格看板</h1>
<div class="sub">数据源: Vast.ai 现货市场 · 每卡每小时中位价</div>
<div class="card"><div class="ct">现货中位价趋势 ($/GPU/小时)</div>
<div style="position:relative;height:340px"><canvas id="price"></canvas></div></div>
<div class="card"><div class="ct">可租GPU供给量(供给↑+价格↓ = 去库存拐点信号)</div>
<div style="position:relative;height:300px"><canvas id="supply"></canvas></div></div>
<script>
const dates=__DATES__;
const priceData=__PRICE__;
const supplyData=__SUPPLY__;
const colors={H100:'#f5a623',H200:'#00e5a0',B200:'#ff4466',A100:'#4488ff'};
const gc='rgba(255,255,255,0.05)',tc='#6060a0';
new Chart(document.getElementById('price'),{type:'line',
 data:{labels:dates,datasets:Object.keys(priceData).map(g=>({label:g,data:priceData[g],
   borderColor:colors[g],backgroundColor:'transparent',borderWidth:2,pointRadius:0,tension:.3,spanGaps:true}))},
 options:{responsive:true,maintainAspectRatio:false,
   plugins:{legend:{labels:{color:tc,font:{family:'IBM Plex Mono',size:10},boxWidth:10}}},
   scales:{x:{ticks:{color:tc,font:{size:9},maxTicksLimit:12},grid:{color:gc}},
     y:{ticks:{color:tc,font:{size:10},callback:v=>'$'+v},grid:{color:gc}}}}});
new Chart(document.getElementById('supply'),{type:'line',
 data:{labels:dates,datasets:Object.keys(supplyData).map(g=>({label:g,data:supplyData[g],
   borderColor:colors[g],backgroundColor:'transparent',borderWidth:2,pointRadius:0,tension:.3,spanGaps:true}))},
 options:{responsive:true,maintainAspectRatio:false,
   plugins:{legend:{labels:{color:tc,font:{family:'IBM Plex Mono',size:10},boxWidth:10}}},
   scales:{x:{ticks:{color:tc,font:{size:9},maxTicksLimit:12},grid:{color:gc}},
     y:{ticks:{color:tc,font:{size:10}},grid:{color:gc}}}}});
</script></body></html>"""

    html = html.replace("__DATES__", json.dumps(dates))
    html = html.replace("__PRICE__", json.dumps(price_data))
    html = html.replace("__SUPPLY__", json.dumps(supply_data))
    with open(OUT, "w") as f:
        f.write(html)
    print(f"看板已生成: {OUT}")


if __name__ == "__main__":
    main()

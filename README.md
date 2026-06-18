# GPU 租赁价格监测器

监测 Vast.ai 现货市场的 GPU 租赁价格,作为 AI 基建"库存周期"的领先指标。

## 为什么是这个指标

GPU 租赁现货价格是 AI 算力供需**最诚实的温度计**——它不受财报口径影响,比公司营收数据领先 1-2 个季度。核心判断逻辑:

| 价格 | 供给 | 含义 | 库存周期阶段 |
|------|------|------|------------|
| ↑ | — | 需求旺盛 | 主动补库存(健康) |
| ↓ | ↓ | 降价被需求消化 | 良性成本下降 |
| ↓ | ↑ | **需求跟不上产能** | **滑向被动补库存(危险)** |

真正的拐点信号 = **价格↓ + 供给↑ + 厂商capex仍在上调**,三者同时出现。

## 安装

```bash
pip install requests
```

(分析和看板模块只用标准库,只有抓取需要 requests)

## 使用

```bash
# 1. 每天运行一次,抓取并追加数据
python fetch_vast.py

# 2. 积累 ≥2 周后,分析趋势和拐点
python analyze.py

# 3. 生成可视化看板(浏览器打开 dashboard.html)
python make_dashboard.py
```

## 自动化(每天定时跑)

**macOS / Linux — crontab:**
```bash
crontab -e
# 加一行(每天早上9点跑):
0 9 * * * cd /path/to/gpu_monitor && /usr/bin/python3 fetch_vast.py >> log.txt 2>&1
```

**GitHub Actions(零成本云端运行,推荐):**
把这个文件夹推到 GitHub 私有仓库,加 `.github/workflows/daily.yml`:
```yaml
name: daily-gpu-fetch
on:
  schedule:
    - cron: '0 9 * * *'   # UTC时间每天9点
  workflow_dispatch:        # 也支持手动触发
jobs:
  fetch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '3.12'}
      - run: pip install requests
      - run: python fetch_vast.py
      - run: |
          git config user.name "bot"
          git config user.email "bot@local"
          git add data/ && git commit -m "data: $(date +%F)" || true
          git push
```
这样数据会自动每天积累到仓库里,完全免费。

## 文件结构

```
gpu_monitor/
├── fetch_vast.py       # 抓取(每天跑)
├── analyze.py          # 信号分析
├── make_dashboard.py   # 生成HTML看板
├── data/
│   └── gpu_prices.csv  # 自动积累的时间序列
└── dashboard.html      # 生成的看板
```

## 已知限制 / 容错设计

- **API 不稳定**: Vast.ai 偶尔会变更端点或限流。抓取失败时脚本**不会写入空行**,保留历史数据,只跳过当次。
- **单一数据源**: 目前只接 Vast.ai。Vast 是 C2C 市场,价格波动比大厂牌价灵敏,但样本偏小型租户。建议后续加 RunPod API 做交叉验证。
- **型号匹配**: 用字符串模糊匹配 `gpu_name`,Vast 改命名可能漏匹配。`TARGET_GPUS` 列表可自行调整。
- **需要时间积累**: 单点数据无意义,至少连续运行 2-4 周才能看出趋势。

## 扩展方向

这个管道是整个"双因子泡沫看板"的第一块。后续可并入同一框架的其他数据源:
- FINRA 融资余额(月度,杠杆维度)
- FRED 净流动性 / 高收益利差(宏观维度)
- SEC EDGAR 内部人减持(聪明钱维度)
- AAII 情绪 / Google Trends(散户FOMO维度)

每个数据源独立成一个 fetch_*.py,共用 analyze 和 dashboard 框架。

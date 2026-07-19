"""Fetch and aggregate Vast.ai GPU offers into ``data/gpu_prices.csv``."""

import csv
import os
import re
import statistics
import sys
import tempfile
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


VAST_API = "https://console.vast.ai/api/v0/bundles/"
TARGET_GPUS = ["H100", "H200", "B200", "RTX 4090", "A100"]
REQUIRED_GPUS = ["H100", "H200", "B200", "A100"]

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CSV_PATH = os.path.join(DATA_DIR, "gpu_prices.csv")


class FetchError(RuntimeError):
    """The response is not safe to append to the historical dataset."""


def _session():
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("POST",),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def fetch_offers(api_key=None, session=None):
    """Return the complete authenticated on-demand offer search response."""
    api_key = api_key or os.environ.get("VAST_API_KEY")
    if not api_key:
        raise FetchError("VAST_API_KEY is not set; refusing Vast.ai's unauthenticated fallback data")

    payload = {
        "rentable": {"eq": True},
        "rented": {"eq": False},
        "type": "ondemand",
        "order": [["dph_total", "asc"]],
        "limit": 5000,
    }
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "qqqqhuhu-gpu-monitor/2.0",
    }
    client = session or _session()
    response = client.post(VAST_API, json=payload, headers=headers, timeout=30)
    print(f"HTTP status: {response.status_code}")
    if response.status_code >= 400:
        snippet = response.text.replace("\n", " ")[:300]
        raise FetchError(f"Vast.ai HTTP {response.status_code}: {snippet}")

    try:
        data = response.json()
    except ValueError as exc:
        raise FetchError("Vast.ai returned invalid JSON") from exc
    if not isinstance(data, dict) or not isinstance(data.get("offers"), list):
        keys = list(data) if isinstance(data, dict) else type(data).__name__
        raise FetchError(f"unexpected Vast.ai response shape; keys/type={keys}")

    offers = data["offers"]
    print(f"Returned records: {len(offers)}")
    if not offers:
        raise FetchError("Vast.ai returned zero offers")
    return offers


def classify_gpu_name(name):
    """Map current Vast.ai model variants to stable dashboard series names."""
    normalized = re.sub(r"[^A-Z0-9]+", " ", str(name).upper()).strip()
    compact = normalized.replace(" ", "")
    # Check exact generations independently so H100 PCIe/SXM/NVL all map to H100.
    for model in ("B200", "H200", "H100", "A100"):
        if re.search(rf"(?:^| ){model}(?: |$)", normalized) or model in compact:
            return model
    if "RTX4090" in compact:
        return "RTX 4090"
    return None


def summarize(offers):
    grouped = {gpu: [] for gpu in TARGET_GPUS}
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        gpu = classify_gpu_name(offer.get("gpu_name", ""))
        if gpu:
            grouped[gpu].append(offer)

    result = {}
    for gpu in TARGET_GPUS:
        matched = grouped[gpu]
        prices = []
        total_gpus = 0
        invalid = 0
        for offer in matched:
            try:
                count = int(offer.get("num_gpus"))
                total_price = float(offer.get("dph_total"))
                if count <= 0 or total_price <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                invalid += 1
                continue
            prices.append(total_price / count)
            total_gpus += count

        print(f"{gpu} matches: {len(matched)} (valid={len(prices)}, invalid={invalid})")
        if not prices:
            result[gpu] = None
            print(f"{gpu} median: n/a; supply: 0")
            continue

        prices.sort()
        median = statistics.median(prices)
        result[gpu] = {
            "price_median": round(median, 4),
            "price_min": round(prices[0], 4),
            "price_p25": round(prices[len(prices) // 4], 4),
            "price_dispersion": round(median / prices[0], 3),
            "offer_count": len(prices),
            "available_gpus": total_gpus,
        }
        print(f"{gpu} median: ${median:.4f}/GPU/hour; supply: {total_gpus} GPUs")
    return result


def validate_summary(summary):
    missing = [gpu for gpu in REQUIRED_GPUS if not summary.get(gpu)]
    if missing:
        raise FetchError(
            "no valid priced offers for required GPU series: " + ", ".join(missing)
        )


def _csv_header():
    header = ["date"]
    for gpu in TARGET_GPUS:
        key = gpu.replace(" ", "")
        header += [
            f"{key}_median", f"{key}_min", f"{key}_dispersion",
            f"{key}_offers", f"{key}_gpus",
        ]
    return header


def append_csv(summary, csv_path=CSV_PATH, today=None):
    """Atomically replace today's row only after the full summary is valid."""
    validate_summary(summary)
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    header = _csv_header()
    row = [today]
    for gpu in TARGET_GPUS:
        item = summary.get(gpu)
        if item:
            row += [item["price_median"], item["price_min"], item["price_dispersion"],
                    item["offer_count"], item["available_gpus"]]
        else:
            row += ["", "", "", "", ""]

    existing_rows = []
    if os.path.exists(csv_path):
        with open(csv_path, newline="", encoding="utf-8") as handle:
            current = list(csv.reader(handle))
        if current and current[0] != header:
            raise FetchError("existing CSV header does not match the current schema")
        existing_rows = [r for r in current[1:] if r and r[0] != today]

    directory = os.path.dirname(csv_path)
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix="gpu_prices.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            writer.writerows(existing_rows)
            writer.writerow(row)
        os.replace(temp_path, csv_path)
    except Exception:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Fetching Vast.ai offers")
    try:
        offers = fetch_offers()
        summary = summarize(offers)
        validate_summary(summary)
        append_csv(summary)
    except (FetchError, requests.RequestException, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("Historical data preserved; no CSV row was written.", file=sys.stderr)
        return 1

    print(f"Wrote validated snapshot to {CSV_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

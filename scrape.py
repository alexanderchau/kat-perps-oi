#!/usr/bin/env python3
"""
Hourly scraper: pulls open interest per market from Katana Perps REST API
and appends a point to data.json. Designed to be idempotent and safe:
if the API is down or returns junk, the existing data.json is left intact.
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

API_BASE = "https://api-perps.katana.network/v1"
UA = "kat-perps-oi/1.0 (+https://kat-perps-oi.pages.dev)"
DATA_FILE = Path(__file__).parent / "data.json"
MAX_POINTS_PER_MARKET = 24 * 365  # ~1 year of hourly points; trim if longer


def fetch(path: str) -> dict | list:
    req = urllib.request.Request(f"{API_BASE}{path}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def load_data() -> dict:
    if not DATA_FILE.exists():
        return {"markets": {}, "total": [], "updated_at": 0}
    with DATA_FILE.open() as f:
        d = json.load(f)
    d.setdefault("markets", {})
    d.setdefault("total", [])
    d.setdefault("updated_at", 0)
    return d


def save_data(d: dict) -> None:
    tmp = DATA_FILE.with_suffix(".json.tmp")
    with tmp.open("w") as f:
        json.dump(d, f, separators=(",", ":"))
    os.replace(tmp, DATA_FILE)


def main() -> int:
    try:
        markets = fetch("/markets")
        exchange = fetch("/exchange")
    except Exception as e:
        print(f"[scrape] fetch failed: {e}", file=sys.stderr)
        return 0

    if not isinstance(markets, list) or not markets:
        print("[scrape] markets payload empty or wrong shape", file=sys.stderr)
        return 0

    now_ms = int(time.time() * 1000)
    data = load_data()

    total_usd = 0.0
    total_vol = 0.0
    for m in markets:
        sym = m.get("market")
        if not sym:
            continue
        try:
            oi_base = float(m["openInterest"])
            px = float(m["indexPrice"])
        except (KeyError, ValueError):
            continue
        try:
            vol_usd = float(m.get("volume24h") or 0)
        except (TypeError, ValueError):
            vol_usd = 0.0
        try:
            trades24h = int(m.get("trades24h") or 0)
        except (TypeError, ValueError):
            trades24h = 0
        oi_usd = oi_base * px
        total_usd += oi_usd
        total_vol += vol_usd

        bucket = data["markets"].setdefault(
            sym,
            {"baseAsset": m.get("baseAsset"), "quoteAsset": m.get("quoteAsset"), "points": []},
        )
        bucket["baseAsset"] = m.get("baseAsset") or bucket.get("baseAsset")
        bucket["quoteAsset"] = m.get("quoteAsset") or bucket.get("quoteAsset")
        bucket["status"] = m.get("status")
        bucket["points"].append(
            {
                "t": now_ms,
                "oi": round(oi_base, 8),
                "px": round(px, 8),
                "usd": round(oi_usd, 2),
                "vol": round(vol_usd, 2),
                "tr": trades24h,
            }
        )
        if len(bucket["points"]) > MAX_POINTS_PER_MARKET:
            bucket["points"] = bucket["points"][-MAX_POINTS_PER_MARKET:]

    exchange_vol = None
    if isinstance(exchange, dict):
        try:
            exchange_vol = float(exchange.get("volume24h") or 0)
        except (TypeError, ValueError):
            exchange_vol = None

    data["total"].append({
        "t": now_ms,
        "usd": round(total_usd, 2),
        "vol": round(exchange_vol if exchange_vol is not None else total_vol, 2),
    })
    if len(data["total"]) > MAX_POINTS_PER_MARKET:
        data["total"] = data["total"][-MAX_POINTS_PER_MARKET:]

    data["updated_at"] = now_ms
    data["exchange"] = {
        "chainId": exchange.get("chainId") if isinstance(exchange, dict) else None,
        "volume24h": exchange.get("volume24h") if isinstance(exchange, dict) else None,
    }

    save_data(data)
    vol_print = exchange_vol if exchange_vol is not None else total_vol
    print(
        f"[scrape] {len(markets)} markets, total OI ${total_usd:,.0f}, "
        f"24h vol ${vol_print:,.0f} @ {now_ms}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

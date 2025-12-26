"""Insider activity analysis (MVP using Alpha Vantage transactions).

Computes net shares bought/sold over 3, 6, 12 months, counts unique
buyers/sellers, detects clustered activity, and flags routine selling
patterns per insider.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional


def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt)
        except Exception:
            continue
    return None


def _tx_sign(t: str) -> int:
    """Return +1 for buy, -1 for sell, 0 otherwise based on transaction type text."""
    if not t:
        return 0
    tl = t.lower()
    if "purchase" in tl or tl.startswith("p"):
        return +1
    if "sale" in tl or tl.startswith("s"):
        return -1
    return 0


def _aggregate_windows(
    tx: List[Dict[str, Any]],
    now: datetime,
) -> Dict[str, Any]:
    windows = {
        "3m": now - timedelta(days=90),
        "6m": now - timedelta(days=180),
        "12m": now - timedelta(days=365),
    }
    result = {}
    for label, start in windows.items():
        net_shares = 0.0
        buyers = set()
        sellers = set()
        total_dollars = 0.0
        for r in tx:
            d = _parse_date(r.get("transactionDate") or r.get("filingDate"))
            if not d or d < start:
                continue
            name = r.get("reportingName") or r.get("name") or r.get("filingOwnerName") or r.get("reportingCik")
            shares = r.get("securitiesTransacted") or r.get("shares") or r.get("transactionShares")
            price = r.get("price") or r.get("transactionPrice") or r.get("transactionPricePerShare")
            try:
                shares = float(shares) if shares is not None else 0.0
            except Exception:
                shares = 0.0
            try:
                price = float(price) if price is not None else 0.0
            except Exception:
                price = 0.0
            sign = _tx_sign(r.get("transactionType") or r.get("type") or "")
            net_shares += sign * shares
            total_dollars += abs(shares * price)
            if sign > 0 and name:
                buyers.add(name)
            elif sign < 0 and name:
                sellers.add(name)
        result[label] = {
            "net_shares": net_shares,
            "unique_buyers": len(buyers),
            "unique_sellers": len(sellers),
            "total_dollars": total_dollars,
        }
    return result


def _clustered_buying(
    tx: List[Dict[str, Any]],
    *,
    window_days: int = 30,
    min_insiders: int = 3,
    min_dollars: float = 500_000.0,
    shares_outstanding: Optional[float] = None,
    min_pct_float: float = 0.001,  # 0.1%
) -> Dict[str, Any]:
    """Detect clustered buying events within a rolling window.

    Heuristic: at least `min_insiders` unique insiders buy within `window_days`,
    with aggregate dollar value >= `min_dollars`, and if shares_outstanding is
    known, aggregate shares >= 0.1% of diluted shares.
    """
    # Build a list of buy events
    buys = []
    for r in tx:
        sign = _tx_sign(r.get("transactionType") or r.get("type") or "")
        if sign <= 0:
            continue
        d = _parse_date(r.get("transactionDate") or r.get("filingDate"))
        if not d:
            continue
        name = r.get("reportingName") or r.get("name") or r.get("filingOwnerName") or r.get("reportingCik")
        shares = r.get("securitiesTransacted") or r.get("shares") or r.get("transactionShares")
        price = r.get("price") or r.get("transactionPrice") or r.get("transactionPricePerShare")
        try:
            shares = float(shares) if shares is not None else 0.0
        except Exception:
            shares = 0.0
        try:
            price = float(price) if price is not None else 0.0
        except Exception:
            price = 0.0
        buys.append({"date": d, "name": name, "shares": shares, "dollars": abs(shares * price)})

    buys.sort(key=lambda x: x["date"]) 
    events: List[Dict[str, Any]] = []
    n = len(buys)
    i = 0
    while i < n:
        j = i
        end = buys[i]["date"] + timedelta(days=window_days)
        insiders = set()
        shares_sum = 0.0
        dollars_sum = 0.0
        while j < n and buys[j]["date"] <= end:
            insiders.add(buys[j]["name"]) if buys[j]["name"] else None
            shares_sum += buys[j]["shares"]
            dollars_sum += buys[j]["dollars"]
            j += 1
        pct = None
        meets_pct = False
        if shares_outstanding and shares_outstanding > 0:
            pct = shares_sum / shares_outstanding
            meets_pct = pct >= min_pct_float
        if len(insiders) >= min_insiders and (dollars_sum >= min_dollars or meets_pct):
            events.append(
                {
                    "window_start": buys[i]["date"].date().isoformat(),
                    "window_end": (end).date().isoformat(),
                    "unique_insiders": len(insiders),
                    "shares_sum": shares_sum,
                    "dollars_sum": dollars_sum,
                    "shares_pct_of_out": pct,
                }
            )
        i += 1
    return {"events": events}


def _routine_selling(
    tx: List[Dict[str, Any]],
    *,
    cadence_tolerance_days: int = 15,
    size_tolerance_pct: float = 0.20,
    min_occurrences: int = 3,
) -> Dict[str, Any]:
    """Detect routine selling for each insider (repeated sales with cadence and size stability)."""
    from collections import defaultdict

    sells = defaultdict(list)
    for r in tx:
        if _tx_sign(r.get("transactionType") or r.get("type") or "") < 0:
            d = _parse_date(r.get("transactionDate") or r.get("filingDate"))
            if not d:
                continue
            name = r.get("reportingName") or r.get("name") or r.get("filingOwnerName") or r.get("reportingCik")
            shares = r.get("securitiesTransacted") or r.get("shares") or r.get("transactionShares")
            try:
                shares = float(shares) if shares is not None else 0.0
            except Exception:
                shares = 0.0
            sells[name].append({"date": d, "shares": shares})

    flags = {}
    for name, events in sells.items():
        if not name or len(events) < min_occurrences:
            continue
        events.sort(key=lambda x: x["date"])
        # Check cadence: differences between dates roughly monthly/quarterly
        diffs = [ (events[i]["date"] - events[i-1]["date"]).days for i in range(1, len(events)) ]
        if not diffs:
            continue
        avg = sum(diffs) / len(diffs)
        # Accept ~monthly (30d) or ~quarterly (90d) within tolerance
        is_cadenced = any(abs(avg - target) <= cadence_tolerance_days for target in (30, 90))
        # Check size stability
        sizes = [e["shares"] for e in events]
        if sizes and min(sizes) > 0:
            max_dev = max(abs(s - sizes[0]) / sizes[0] for s in sizes[1:]) if len(sizes) > 1 else 0
        else:
            max_dev = 1.0
        stable_size = max_dev <= size_tolerance_pct
        if is_cadenced and stable_size:
            flags[name] = {
                "occurrences": len(events),
                "avg_days_between": avg,
                "size_deviation_pct": max_dev,
            }
    return {"routine_sellers": flags}


def analyze_insiders(
    *,
    transactions: List[Dict[str, Any]],
    shares_outstanding: Optional[float] = None,
    asof: Optional[datetime] = None,
) -> Dict[str, Any]:
    now = asof or datetime.utcnow()
    windows = _aggregate_windows(transactions, now)
    cluster = _clustered_buying(transactions, shares_outstanding=shares_outstanding)
    routine = _routine_selling(transactions)
    # Simple alignment summary
    net12 = windows.get("12m", {}).get("net_shares") or 0.0
    buyers12 = windows.get("12m", {}).get("unique_buyers") or 0
    sellers12 = windows.get("12m", {}).get("unique_sellers") or 0
    alignment = (
        "positive" if net12 > 0 and buyers12 >= sellers12 else "negative" if net12 < 0 and sellers12 > buyers12 else "mixed"
    )
    return {
        "windows": windows,
        "clustered_buying": cluster,
        "routine_selling": routine,
        "owner_alignment": alignment,
    }

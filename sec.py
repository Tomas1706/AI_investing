"""SEC data access and helpers (MVP implementation of Step 3).

Implements SEC filings retrieval using the submissions API:
- Latest 10-K
- Last 2–3 10-Q filings
- 8-K filings from the last 90 days
- Form 4 filings from the last 24 months
- Latest DEF 14A (proxy)

Stores metadata JSON and provides raw document URLs (download optional later).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional


def _normalize_cik(cik: str) -> str:
    digits = re.sub(r"\D", "", str(cik))
    return digits.zfill(10)


def _cik_nodash(cik: str) -> str:
    return re.sub(r"\D", "", str(cik)).lstrip("0") or "0"


@dataclass
class Filing:
    form: str
    filingDate: str
    accessionNumber: str
    primaryDocument: Optional[str] = None
    reportDate: Optional[str] = None
    filingUrl: Optional[str] = None
    indexUrl: Optional[str] = None


class SECClient:
    def __init__(self, user_agent: str):
        try:
            import requests  # import here to avoid hard dependency on module import
        except ImportError as e:
            raise RuntimeError(
                "Missing dependency 'requests'. Install it (e.g., 'uv add requests')."
            ) from e

        self._requests = requests
        self.sess = requests.Session()
        self.sess.headers.update({
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
        })

    def get_json(self, url: str) -> Dict[str, Any]:
        from time import sleep

        for attempt in range(5):
            r = self.sess.get(url, timeout=30)
            if r.status_code == 429:
                sleep(1 + attempt)
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError(f"Too many 429 responses from SEC for {url}")


def _zip_recent_filings(recent: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
    keys = [
        "form",
        "filingDate",
        "accessionNumber",
        "primaryDocument",
        "reportDate",
    ]
    n = len(recent.get("form", []))
    rows: List[Dict[str, Any]] = []
    for i in range(n):
        row = {k: recent.get(k, [None] * n)[i] for k in keys}
        rows.append(row)
    return rows


def _attach_urls(cik10: str, row: Dict[str, Any]) -> Filing:
    acc_no = (row.get("accessionNumber") or "").replace("-", "")
    primary = row.get("primaryDocument")
    base = f"https://www.sec.gov/Archives/edgar/data/{_cik_nodash(cik10)}/{acc_no}"
    filing_url = f"{base}/{primary}" if primary else None
    index_url = f"{base}-index.html"
    return Filing(
        form=row.get("form"),
        filingDate=row.get("filingDate"),
        accessionNumber=row.get("accessionNumber"),
        primaryDocument=primary,
        reportDate=row.get("reportDate"),
        filingUrl=filing_url,
        indexUrl=index_url,
    )


def fetch_filings(
    *,
    cik: str,
    out_root: Path,
    user_agent: str,
    form4_lookback_months: int = 24,
    recent_q_count: int = 3,
) -> Dict[str, Any]:
    """Fetch required filings for a CIK and persist metadata.

    Returns a dict with selected filings and cache paths.
    """
    cik10 = _normalize_cik(cik)
    client = SECClient(user_agent=user_agent)

    cache_dir = out_root / ".cache" / "sec" / cik10
    cache_dir.mkdir(parents=True, exist_ok=True)

    # 1) Load submissions summary
    subs_url = f"https://data.sec.gov/submissions/CIK{cik10}.json"
    subs = client.get_json(subs_url)
    (cache_dir / "submissions.json").write_text(
        json.dumps(subs, indent=2), encoding="utf-8"
    )

    company_name = subs.get("name")
    recent = subs.get("filings", {}).get("recent", {})
    recent_rows = _zip_recent_filings(recent)

    # 2) Optionally load additional year files to extend history (esp. for Form 4)
    history_rows: List[Dict[str, Any]] = []
    files = subs.get("filings", {}).get("files", []) or []
    # Fetch only last two years or those within lookback window
    cutoff_date = datetime.utcnow().date() - timedelta(days=30 * form4_lookback_months)
    for fmeta in files[-3:]:  # last few files are most recent years
        name = fmeta.get("name")
        if not name:
            continue
        # Expect paths like CIK0000320193-2024.json
        url = f"https://data.sec.gov/submissions/{name}"
        try:
            year_json = client.get_json(url)
        except Exception:
            continue
        for row in year_json.get("filings", []):
            # Each row is a dict with similar keys
            try:
                # Filter by date roughly to reduce volume
                fdate = row.get("filingDate")
                if fdate and datetime.strptime(fdate, "%Y-%m-%d").date() < cutoff_date:
                    # keep anyway; we will filter later per form
                    pass
            except Exception:
                pass
            history_rows.append(row)

    all_rows = recent_rows + history_rows

    # 3) Build Filing objects with URLs
    filings: List[Filing] = [_attach_urls(cik10, r) for r in all_rows]

    # 4) Select required sets
    def by_form(form: str) -> List[Filing]:
        return [f for f in filings if (f.form or "").upper() == form.upper()]

    def first_by_form(form: str) -> Optional[Filing]:
        xs = by_form(form)
        xs.sort(key=lambda x: x.filingDate or "", reverse=True)
        return xs[0] if xs else None

    # Latest 10-K
    latest_10k = first_by_form("10-K")

    # Last N 10-Q
    q_filings = by_form("10-Q")
    q_filings.sort(key=lambda x: x.filingDate or "", reverse=True)
    latest_qs = q_filings[: max(0, recent_q_count)]

    # 8-K in last 90 days
    cutoff_8k = datetime.utcnow().date() - timedelta(days=90)
    k_filings = [f for f in filings if (f.form or "").upper() == "8-K"]
    recent_8ks = []
    for f in k_filings:
        try:
            if f.filingDate and datetime.strptime(f.filingDate, "%Y-%m-%d").date() >= cutoff_8k:
                recent_8ks.append(f)
        except Exception:
            pass

    # DEF 14A latest
    def14a = first_by_form("DEF 14A")

    # Form 4 last N months (include 4 and 4/A)
    cutoff_4 = datetime.utcnow().date() - timedelta(days=30 * form4_lookback_months)
    f4_filings = [f for f in filings if (f.form or "").upper() in ("4", "4/A")]
    f4_window = []
    for f in f4_filings:
        try:
            if f.filingDate and datetime.strptime(f.filingDate, "%Y-%m-%d").date() >= cutoff_4:
                f4_window.append(f)
        except Exception:
            pass

    # 5) Persist metadata selection
    def _as_dict(f: Optional[Filing]) -> Optional[Dict[str, Any]]:
        if not f:
            return None
        return {
            "form": f.form,
            "filingDate": f.filingDate,
            "accessionNumber": f.accessionNumber,
            "primaryDocument": f.primaryDocument,
            "filingUrl": f.filingUrl,
            "indexUrl": f.indexUrl,
        }

    selected = {
        "10-K": _as_dict(latest_10k),
        "10-Q": [
            _as_dict(x) for x in latest_qs
        ],
        "8-K": [_as_dict(x) for x in recent_8ks],
        "DEF 14A": _as_dict(def14a),
        "4": [_as_dict(x) for x in f4_window],
    }

    meta = {
        "cik": cik10,
        "companyName": company_name,
        "selected": selected,
        "counts": {
            "total": len(filings),
            "10-Q": len(latest_qs),
            "8-K_90d": len(recent_8ks),
            "4_lookback": len(f4_window),
        },
    }

    meta_path = cache_dir / "filings_metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return {
        "selected": selected,
        "cache_paths": {
            "metadata": str(meta_path),
            "submissions": str(cache_dir / "submissions.json"),
        },
    }


# Placeholder for Step 4 extraction entry to keep API consistent with imports elsewhere
def extract_xbrl_timeseries(cik: str) -> Dict[str, object]:
    raise NotImplementedError("extract_xbrl_timeseries stub (to be implemented in Step 4)")

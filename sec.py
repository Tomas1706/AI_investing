"""SEC data access and helpers (MVP stubs).

This module will:
- Resolve ticker→CIK
- Retrieve filings metadata and raw text
- Extract structured XBRL timeseries

For Step 1: provide import-safe stubs only.
"""

from typing import Dict, Optional


def resolve_ticker(ticker: str) -> Dict[str, str]:
    """Resolve a US ticker to {cik, company_name}.

    Step 2 will implement this. For now, a stub is provided.
    """
    raise NotImplementedError("resolve_ticker stub (to be implemented in Step 2)")


def fetch_filings(cik: str) -> Dict[str, object]:
    """Fetch required filings for a CIK (metadata and raw text pointers).

    Step 3 will implement this. Stub for now.
    """
    raise NotImplementedError("fetch_filings stub (to be implemented in Step 3)")


def extract_xbrl_timeseries(cik: str) -> Dict[str, object]:
    """Extract structured financial timeseries from SEC XBRL.

    Step 4 will implement this. Stub for now.
    """
    raise NotImplementedError("extract_xbrl_timeseries stub (to be implemented in Step 4)")


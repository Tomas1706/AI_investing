"""Classification and confidence scoring (MVP)."""

from __future__ import annotations

from typing import Dict, Any, Tuple


def _collect_bools(d: Dict[str, Any]) -> Tuple[int, int]:
    known = 0
    positive = 0
    for v in d.values():
        if isinstance(v, bool):
            known += 1
            if v:
                positive += 1
        elif isinstance(v, dict):
            k2, p2 = _collect_bools(v)
            known += k2
            positive += p2
        else:
            # ignore Nones/ints/str
            pass
    return known, positive


def _any_red_flag(rf: Dict[str, Any]) -> bool:
    for v in rf.values():
        if isinstance(v, bool) and v:
            return True
    return False


def classify(signals: Dict[str, Any]) -> Tuple[str, str]:
    """Return (classification, confidence)."""
    red_flags = signals.get("red_flags", {}) or {}
    if _any_red_flag(red_flags):
        classification = "Avoid-for-now"
    else:
        # Count positive signals across categories
        known, positive = _collect_bools({
            "durability": signals.get("durability", {}),
            "moat": signals.get("moat", {}),
            "balance_sheet": signals.get("balance_sheet", {}),
            "capital_allocation": signals.get("capital_allocation", {}),
        })
        ratio = (positive / known) if known else 0.0
        if ratio >= 0.7:
            classification = "Investigate Further"
        else:
            classification = "Watch"

    # Confidence based on coverage and lack of red flags
    known, positive = _collect_bools(signals)
    coverage = (positive + (known - positive)) / known if known else 0.0
    if coverage >= 0.8 and not _any_red_flag(red_flags):
        confidence = "High"
    elif coverage >= 0.5:
        confidence = "Medium"
    else:
        confidence = "Low"

    return classification, confidence

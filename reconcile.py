"""
reconcile.py
------------
Three-pass matching strategy, cheapest and most certain first:

  Pass 1 (exact):  regex-extract a payment_id out of the bank narration text.
                    If it matches a known Razorpay payment 1:1, done - no AI needed.
  Pass 2 (fuzzy):   for anything left, narrow candidates by amount-after-fee tolerance
                    and a settlement-date window, then rank by name similarity.
  Pass 3 (LLM):     when Pass 2 leaves more than one plausible candidate, or the best
                    candidate is borderline, hand it to llm_resolver.py for a judgment
                    call with reasoning, instead of guessing silently.

Anything still unmatched after all three passes is a genuine exception and gets
reported honestly, not hidden.
"""

import re
import difflib
from datetime import datetime

PAYMENT_ID_RE = re.compile(r"pay_[A-Z0-9]{10,}")
FEE_RATE = 0.02
AMOUNT_TOLERANCE = 0.05   # 5% band around the expected post-fee amount (candidate pool, not auto-accept)
DATE_WINDOW_DAYS = 4
PENDING_WINDOW_DAYS = 3   # payments younger than this with no settlement are "pending", not exceptions


def _parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def extract_payment_id(narration: str):
    m = PAYMENT_ID_RE.search(narration)
    return m.group(0) if m else None


def exact_match_pass(payments, bank_rows):
    """Returns (matched: list[dict], remaining_payments, remaining_bank_rows)"""
    matched = []
    matched_bank_idx = set()
    matched_payment_ids = set()

    for bi, row in enumerate(bank_rows):
        pid = extract_payment_id(row["narration"])
        if pid is None:
            continue
        for p in payments:
            if p["payment_id"] == pid and pid not in matched_payment_ids:
                matched.append({
                    "payment_id": pid,
                    "utr_number": row["utr_number"],
                    "method": "exact_id_match",
                    "confidence": "high",
                    "reasoning": "payment_id found verbatim in bank narration.",
                })
                matched_bank_idx.add(bi)
                matched_payment_ids.add(pid)
                break

    remaining_payments = [p for p in payments if p["payment_id"] not in matched_payment_ids]
    remaining_bank = [row for i, row in enumerate(bank_rows) if i not in matched_bank_idx]
    return matched, remaining_payments, remaining_bank


def find_fuzzy_candidates(payment, bank_rows):
    """Narrow candidates by amount tolerance + date window; return sorted by name similarity."""
    expected_amount = round(payment["amount"] * (1 - FEE_RATE), 2)
    pay_date = _parse_date(payment["payment_date"])
    first_name = payment["customer_name"].split()[0].lower()

    candidates = []
    for row in bank_rows:
        amt_diff_pct = abs(row["settled_amount"] - expected_amount) / expected_amount
        if amt_diff_pct > AMOUNT_TOLERANCE:
            continue
        settle_date = _parse_date(row["settlement_date"])
        if not (0 <= (settle_date - pay_date).days <= DATE_WINDOW_DAYS):
            continue
        name_score = difflib.SequenceMatcher(
            None, first_name, row["narration"].lower()
        ).find_longest_match(0, len(first_name), 0, len(row["narration"])).size / max(len(first_name), 1)
        candidates.append({**row, "_amt_diff_pct": amt_diff_pct, "_name_score": name_score})

    candidates.sort(key=lambda c: (-c["_name_score"], c["_amt_diff_pct"]))
    return candidates

"""
run_reconciliation.py
----------------------
Ties generate_data -> reconcile -> llm_resolver together and produces:
  - audit_log.csv : one row per payment/bank-row with the decision and WHY
  - report.md     : the honest summary a human would actually want to read

Run: python3 run_reconciliation.py   (after generate_data.py has been run once)
"""

import csv
from collections import Counter
from datetime import date

import reconcile
from llm_resolver import resolve_ambiguous_match

TODAY = date(2026, 8, 27)


def load_payments(path):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["amount"] = float(r["amount"])
    return rows


def load_bank_rows(path):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["settled_amount"] = float(r["settled_amount"])
    return rows


def main():
    payments = load_payments("data/razorpay_payments.csv")
    bank_rows = load_bank_rows("data/bank_settlement.csv")

    audit = []

    # Pass 1: exact payment_id extraction from narration
    exact_matches, remaining_payments, remaining_bank = reconcile.exact_match_pass(payments, bank_rows)
    for m in exact_matches:
        audit.append({**m, "status": "MATCHED"})

    unmatched_bank = list(remaining_bank)
    llm_calls = 0

    for p in remaining_payments:
        candidates = reconcile.find_fuzzy_candidates(p, unmatched_bank)

        if not candidates:
            days_old = (TODAY - reconcile._parse_date(p["payment_date"])).days
            if days_old <= reconcile.PENDING_WINDOW_DAYS:
                audit.append({
                    "payment_id": p["payment_id"], "utr_number": None,
                    "method": "none", "confidence": "n/a", "status": "PENDING_SETTLEMENT",
                    "reasoning": f"No settlement found yet; only {days_old} day(s) since payment "
                                 f"- within the normal settlement window.",
                })
            else:
                audit.append({
                    "payment_id": p["payment_id"], "utr_number": None,
                    "method": "none", "confidence": "n/a", "status": "UNRESOLVED_EXCEPTION",
                    "reasoning": f"No settlement found within the matching window and payment is "
                                 f"{days_old} days old - needs manual review.",
                })
            continue

        top = candidates[0]
        unambiguous = len(candidates) == 1 or (
            candidates[1]["_amt_diff_pct"] - top["_amt_diff_pct"] > 0.02
        )
        if top["_amt_diff_pct"] < 0.003 and top["_name_score"] > 0.5 and unambiguous:
            audit.append({
                "payment_id": p["payment_id"], "utr_number": top["utr_number"],
                "method": "fuzzy_auto", "confidence": "high", "status": "MATCHED",
                "reasoning": "Settled amount within 0.3% of expected post-fee amount, customer "
                             "name appears in the narration, and no other candidate is close - "
                             "confident enough to skip the LLM call.",
            })
            unmatched_bank = [r for r in unmatched_bank if r["utr_number"] != top["utr_number"]]
            continue

        llm_calls += 1
        decision = resolve_ambiguous_match(p, candidates[:3])
        if decision["decision"] == "match" and decision["chosen_utr"]:
            audit.append({
                "payment_id": p["payment_id"], "utr_number": decision["chosen_utr"],
                "method": f"llm_{decision['mode']}", "confidence": decision["confidence"],
                "status": "MATCHED", "reasoning": decision["reasoning"],
            })
            unmatched_bank = [r for r in unmatched_bank if r["utr_number"] != decision["chosen_utr"]]
        else:
            audit.append({
                "payment_id": p["payment_id"], "utr_number": None,
                "method": f"llm_{decision['mode']}", "confidence": decision["confidence"],
                "status": "UNRESOLVED_EXCEPTION", "reasoning": decision["reasoning"],
            })

    # Whatever bank rows nobody claimed are bank-side exceptions
    for row in unmatched_bank:
        pid = reconcile.extract_payment_id(row["narration"])
        if pid:
            status = "DUPLICATE_SETTLEMENT"
            reasoning = f"Narration references {pid}, which was already settled by another " \
                        f"bank row - looks like a duplicate credit."
        else:
            status = "UNEXPLAINED_BANK_CREDIT"
            reasoning = "No corresponding Razorpay payment found for this bank credit within tolerance."
        audit.append({
            "payment_id": None, "utr_number": row["utr_number"],
            "method": "none", "confidence": "n/a", "status": status, "reasoning": reasoning,
        })

    write_audit_log(audit)
    write_report(audit, len(payments), llm_calls)


def write_audit_log(audit):
    fields = ["payment_id", "utr_number", "method", "confidence", "status", "reasoning"]
    with open("audit_log.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in audit:
            w.writerow({k: row.get(k) for k in fields})
    print(f"Wrote audit_log.csv ({len(audit)} rows)")


def write_report(audit, total_payments, llm_calls):
    status_counts = Counter(a["status"] for a in audit if a["payment_id"] is not None)
    bank_exceptions = [a for a in audit if a["payment_id"] is None]
    bank_exception_counts = Counter(a["status"] for a in bank_exceptions)

    matched = status_counts.get("MATCHED", 0)
    match_rate = matched / total_payments * 100
    method_counts = Counter(a["method"] for a in audit if a["status"] == "MATCHED")

    lines = ["# Reconciliation Report", ""]
    lines.append(f"**Total Razorpay payments:** {total_payments}")
    lines.append(f"**Matched to a bank settlement:** {matched} ({match_rate:.1f}%)")
    lines.append(f"**LLM resolver calls made:** {llm_calls}")
    lines.append("")
    lines.append("## Payment-side breakdown")
    for status, count in status_counts.most_common():
        lines.append(f"- **{status}**: {count}")
    lines.append("")
    lines.append("## How matches were found")
    for method, count in method_counts.most_common():
        lines.append(f"- **{method}**: {count}")
    lines.append("")
    lines.append("## Bank-side exceptions (credits with no clean payment match)")
    if bank_exceptions:
        for status, count in bank_exception_counts.most_common():
            lines.append(f"- **{status}**: {count}")
    else:
        lines.append("- None")
    lines.append("")
    lines.append("## Honest exception list")
    lines.append("Everything below is something the system could NOT resolve automatically "
                  "and would need a human to look at:")
    lines.append("")
    for a in audit:
        if a["status"] in ("UNRESOLVED_EXCEPTION", "DUPLICATE_SETTLEMENT", "UNEXPLAINED_BANK_CREDIT"):
            lines.append(f"- `{a['status']}` — payment: {a['payment_id']}, "
                          f"bank row: {a['utr_number']} — {a['reasoning']}")

    with open("report.md", "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote report.md — match rate {match_rate:.1f}%")


if __name__ == "__main__":
    main()

# Reconciliation Report

**Total Razorpay payments:** 65
**Matched to a bank settlement:** 58 (89.2%)
**LLM resolver calls made:** 12

## Payment-side breakdown
- **MATCHED**: 58
- **UNRESOLVED_EXCEPTION**: 7

## How matches were found
- **exact_id_match**: 46
- **llm_mock**: 12

## Bank-side exceptions (credits with no clean payment match)
- **UNEXPLAINED_BANK_CREDIT**: 3
- **DUPLICATE_SETTLEMENT**: 2

## Honest exception list
Everything below is something the system could NOT resolve automatically and would need a human to look at:

- `UNRESOLVED_EXCEPTION` — payment: pay_HMGVQZZRTL0020, bank row: None — No settlement found within the matching window and payment is 19 days old - needs manual review.
- `UNRESOLVED_EXCEPTION` — payment: pay_QJOAQLRUUS0024, bank row: None — No settlement found within the matching window and payment is 8 days old - needs manual review.
- `UNRESOLVED_EXCEPTION` — payment: pay_TJURDHGMOS0031, bank row: None — No settlement found within the matching window and payment is 9 days old - needs manual review.
- `UNRESOLVED_EXCEPTION` — payment: pay_PXKMCDUWBD0032, bank row: None — No settlement found within the matching window and payment is 4 days old - needs manual review.
- `UNRESOLVED_EXCEPTION` — payment: pay_NLZUYOXUVM0037, bank row: None — No settlement found within the matching window and payment is 8 days old - needs manual review.
- `UNRESOLVED_EXCEPTION` — payment: pay_ILQEBYZAEF0042, bank row: None — No settlement found within the matching window and payment is 15 days old - needs manual review.
- `UNRESOLVED_EXCEPTION` — payment: pay_KEMBSRCZFH0054, bank row: None — No settlement found within the matching window and payment is 8 days old - needs manual review.
- `DUPLICATE_SETTLEMENT` — payment: None, bank row: UTR2809107457 — Narration references pay_VOTTJHKJNV0056, which was already settled by another bank row - looks like a duplicate credit.
- `UNEXPLAINED_BANK_CREDIT` — payment: None, bank row: UTR7992591409 — No corresponding Razorpay payment found for this bank credit within tolerance.
- `UNEXPLAINED_BANK_CREDIT` — payment: None, bank row: UTR9371775139 — No corresponding Razorpay payment found for this bank credit within tolerance.
- `UNEXPLAINED_BANK_CREDIT` — payment: None, bank row: UTR7450834621 — No corresponding Razorpay payment found for this bank credit within tolerance.
- `DUPLICATE_SETTLEMENT` — payment: None, bank row: UTR6711686861 — Narration references pay_NNNHSLTCFA0039, which was already settled by another bank row - looks like a duplicate credit.

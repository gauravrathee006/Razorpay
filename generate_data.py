"""
generate_data.py
-----------------
Creates two synthetic ledgers that a real merchant would need to reconcile:

  1. data/razorpay_payments.csv  -> Razorpay-side record of every payment collected
  2. data/bank_settlement.csv    -> Bank statement showing what actually landed in the account

The two files are deliberately messy, the way real data is:
  - most payments settle a few days later with a small platform fee deducted
  - some bank narrations don't carry the full payment_id (truncated by the bank's system)
  - some payments are still pending settlement (not a problem, just not settled yet)
  - a few bank credits don't correspond to any known payment (unexplained -> real exception)
  - a couple of payments get settled twice by mistake (duplicate credit -> real exception)

Run: python3 generate_data.py
"""

import csv
import random
from datetime import date, timedelta
from faker import Faker

fake = Faker()
random.seed(42)  # reproducible run, so results in the README are stable

NUM_PAYMENTS = 65
PLATFORM_FEE_RATE = 0.02  # Razorpay-style settlement fee
TODAY = date(2026, 8, 27)


def rand_date_between(start_days_ago, end_days_ago):
    d = random.randint(end_days_ago, start_days_ago)
    return TODAY - timedelta(days=d)


def make_payment_id(i):
    return f"pay_{fake.lexify('??????????').upper()}{i:04d}"


def main():
    payments = []
    bank_rows = []

    for i in range(1, NUM_PAYMENTS + 1):
        payment_id = make_payment_id(i)
        amount = round(random.uniform(250, 45000), 2)
        pay_date = rand_date_between(20, 1)
        customer = fake.name()
        email = fake.email()

        payments.append({
            "payment_id": payment_id,
            "amount": amount,
            "payment_date": pay_date.isoformat(),
            "customer_name": customer,
            "customer_email": email,
            "order_id": f"order_{fake.lexify('????????').upper()}",
        })

        scenario = random.random()
        settle_date = pay_date + timedelta(days=random.randint(1, 3))
        settled_amount = round(amount * (1 - PLATFORM_FEE_RATE), 2)

        if scenario < 0.68:
            # Normal case: settles with full payment_id visible in the bank narration
            bank_rows.append({
                "utr_number": f"UTR{fake.numerify('##########')}",
                "settled_amount": settled_amount,
                "settlement_date": settle_date.isoformat(),
                "narration": f"NEFT CR RAZORPAY {payment_id} SETTLEMENT",
            })
        elif scenario < 0.83:
            # Bank truncates or drops the payment_id -> needs fuzzy/LLM matching.
            # Real settlement amounts also aren't always a perfectly clean 2% fee cut
            # (rounding, occasional extra micro-fee), so add a bit of realistic noise.
            noisy_amount = round(settled_amount * random.uniform(0.975, 1.025), 2)
            bank_rows.append({
                "utr_number": f"UTR{fake.numerify('##########')}",
                "settled_amount": noisy_amount,
                "settlement_date": settle_date.isoformat(),
                "narration": f"NEFT CR RAZORPAY SETTLEMENT {customer.split()[0].upper()}",
            })
        elif scenario < 0.92:
            # Still pending -> genuinely not settled yet, not an "error"
            pass
        elif scenario < 0.97:
            # Duplicate settlement credit by mistake -> real exception
            bank_rows.append({
                "utr_number": f"UTR{fake.numerify('##########')}",
                "settled_amount": settled_amount,
                "settlement_date": settle_date.isoformat(),
                "narration": f"NEFT CR RAZORPAY {payment_id} SETTLEMENT",
            })
            bank_rows.append({
                "utr_number": f"UTR{fake.numerify('##########')}",
                "settled_amount": settled_amount,
                "settlement_date": (settle_date + timedelta(days=1)).isoformat(),
                "narration": f"NEFT CR RAZORPAY {payment_id} SETTLEMENT DUP",
            })
        else:
            # Payment simply never settles (failed payout, chargeback pulled it, etc.)
            pass

    # A few unexplained bank credits with no matching payment at all
    for _ in range(4):
        bank_rows.append({
            "utr_number": f"UTR{fake.numerify('##########')}",
            "settled_amount": round(random.uniform(200, 9000), 2),
            "settlement_date": rand_date_between(15, 1).isoformat(),
            "narration": "NEFT CR UNKNOWN SOURCE",
        })

    random.shuffle(bank_rows)

    with open("data/razorpay_payments.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(payments[0].keys()))
        w.writeheader()
        w.writerows(payments)

    with open("data/bank_settlement.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(bank_rows[0].keys()))
        w.writeheader()
        w.writerows(bank_rows)

    print(f"Generated {len(payments)} Razorpay payments -> data/razorpay_payments.csv")
    print(f"Generated {len(bank_rows)} bank settlement rows -> data/bank_settlement.csv")


if __name__ == "__main__":
    main()

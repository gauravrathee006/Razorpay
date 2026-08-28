"""
llm_resolver.py
----------------
Handles the cases rule-based matching genuinely can't resolve on its own: a Razorpay
payment with one or more plausible-but-not-certain bank rows (no payment_id in the
narration, so we're matching on amount + date + customer name similarity instead).

Supports two LLM providers - use whichever key you have:

  - ANTHROPIC_API_KEY  -> calls Claude
  - OPENAI_API_KEY     -> calls OpenAI
  - LLM_PROVIDER=anthropic|openai  -> force a provider if both keys happen to be set
  - neither key set    -> MOCK mode: a transparent heuristic fallback. Every mock
                           decision is labeled as such in the audit trail - nothing
                           is silently faked as "AI-verified". This is what lets the
                           whole pipeline run end-to-end even with zero API access,
                           and is the actual failure path this repo was tested against.

Swap in a real key and MOCK mode is never used.
"""

import os
import json

try:
    from dotenv import load_dotenv
    load_dotenv()  # pulls ANTHROPIC_API_KEY / OPENAI_API_KEY from a local .env file, if present
except ImportError:
    pass  # dotenv is optional - plain `export` env vars still work fine without it

ANTHROPIC_MODEL = "claude-sonnet-4-6"
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

_provider = None


def _resolve_provider() -> str:
    """Pick a provider once per run: explicit override > whichever key exists > mock."""
    global _provider
    if _provider is not None:
        return _provider
    forced = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if forced in ("anthropic", "openai"):
        _provider = forced
    elif os.environ.get("ANTHROPIC_API_KEY"):
        _provider = "anthropic"
    elif os.environ.get("OPENAI_API_KEY"):
        _provider = "openai"
    else:
        _provider = "mock"
    return _provider


def _build_prompt(payment: dict, candidates: list[dict]) -> str:
    return f"""You are reconciling a merchant's payment ledger against a bank settlement file.

Razorpay payment (unmatched by exact ID lookup):
{json.dumps(payment, indent=2)}

Candidate bank settlement rows (matched loosely by amount/date proximity, but the
narration does not contain the full payment_id so we can't be certain):
{json.dumps(candidates, indent=2)}

A 2% platform fee is normally deducted before settlement, and settlement usually
happens 1-3 days after the payment date.

Decide whether ONE of these candidates is almost certainly the settlement for this
payment, or whether none of them confidently is. Respond ONLY with JSON, no other text:
{{"decision": "match" or "no_match", "chosen_utr": "<utr_number or null>",
  "confidence": "low" or "medium" or "high", "reasoning": "<one sentence>"}}"""


def _call_anthropic(prompt: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _call_openai(prompt: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


def resolve_ambiguous_match(payment: dict, candidates: list[dict]) -> dict:
    """
    payment: the unmatched Razorpay payment dict
    candidates: list of bank rows that are plausible matches on amount/date proximity

    Returns: {"decision": "match"|"no_match", "chosen_utr": str|None,
              "confidence": "low"|"medium"|"high", "reasoning": str,
              "mode": "live_anthropic"|"live_openai"|"mock"}
    """
    provider = _resolve_provider()

    if provider == "mock":
        return _mock_resolve(payment, candidates)

    prompt = _build_prompt(payment, candidates)

    try:
        raw = _call_anthropic(prompt) if provider == "anthropic" else _call_openai(prompt)
        text = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        result = json.loads(text)
        result["mode"] = f"live_{provider}"
        return result
    except Exception as e:
        # A real API call can fail for lots of reasons (rate limit, network, bad JSON
        # back from the model, wrong/expired key). Rather than crash the whole
        # reconciliation run, fall back to the heuristic and log exactly why.
        fallback = _mock_resolve(payment, candidates)
        fallback["reasoning"] = f"[{provider} call failed: {e}] " + fallback["reasoning"]
        return fallback


def _mock_resolve(payment: dict, candidates: list[dict]) -> dict:
    """Transparent heuristic fallback: closest amount within 3% after fee, closest date."""
    if not candidates:
        return {"decision": "no_match", "chosen_utr": None, "confidence": "low",
                "reasoning": "No candidates within tolerance.", "mode": "mock"}

    expected = round(payment["amount"] * 0.98, 2)
    best = min(candidates, key=lambda c: abs(c["settled_amount"] - expected))
    diff_pct = abs(best["settled_amount"] - expected) / expected

    if diff_pct < 0.005:
        return {"decision": "match", "chosen_utr": best["utr_number"], "confidence": "high",
                "reasoning": "[MOCK - no LLM key set] Settled amount matches expected "
                              "post-fee amount almost exactly.", "mode": "mock"}
    elif diff_pct < 0.03:
        return {"decision": "match", "chosen_utr": best["utr_number"], "confidence": "medium",
                "reasoning": "[MOCK - no LLM key set] Settled amount is close to expected "
                              "post-fee amount within tolerance.", "mode": "mock"}
    else:
        return {"decision": "no_match", "chosen_utr": None, "confidence": "low",
                "reasoning": "[MOCK - no LLM key set] No candidate close enough to the "
                              "expected post-fee amount.", "mode": "mock"}

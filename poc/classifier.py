"""Task classifier for the proof-carrying data minimization PoC.

Routes a synthetic support ticket to a queue. Uses the OpenAI API when
OPENAI_API_KEY is set, and otherwise falls back to a deterministic
rule-based classifier so the demo runs fully offline.
"""

from __future__ import annotations

import os
import re
from typing import Dict, Optional

QUEUES = [
    "billing",
    "account_security",
    "shipping_logistics",
    "technical_support",
    "general_inquiry",
]

# Declared field order for the ticket routing task.
FIELDS = [
    "issue_description",
    "product_area",
    "urgency",
    "name",
    "email",
    "phone",
    "date_of_birth",
    "address",
    "account_id",
]

# Fields the routing task never needs are still shown to a human reviewer
# with an explicit privacy-cost label, independent of the empirical test.
PRIVACY_COST = {
    "issue_description": "task-relevant, not personal",
    "product_area": "task-relevant, not personal",
    "urgency": "task-relevant, not personal",
    "name": "direct identifier",
    "email": "direct identifier",
    "phone": "direct identifier",
    "date_of_birth": "quasi-identifier",
    "address": "direct identifier",
    "account_id": "direct identifier (linkable)",
}

_KEYWORDS = {
    "billing": ["invoice", "payment", "billing", "charge", "refund", "statement"],
    "account_security": [
        "login", "password", "locked out", "2fa", "two-factor",
        "authentication", "account access", "security",
    ],
    "shipping_logistics": ["shipping", "delivery", "package", "tracking", "courier"],
    "technical_support": ["bug", "crash", "error", "app", "software", "sync"],
}


def _matches(text: str, queue: str) -> bool:
    text = text.lower()
    return any(kw in text for kw in _KEYWORDS[queue])


def classify_rule_based(record: Dict[str, str]) -> str:
    """Deterministic stand-in for an LLM that only reasons about the task.

    Only reads issue_description and product_area. Never reads urgency or
    any of the identifier fields, so their removal never changes the
    routing decision (that is the property the ablation study measures).
    """
    area = record.get("product_area") or ""
    desc = record.get("issue_description") or ""
    combined_signals = [area, desc]

    for queue in ["billing", "account_security", "shipping_logistics", "technical_support"]:
        if any(_matches(signal, queue) for signal in combined_signals if signal):
            return queue
    return "general_inquiry"


def _build_prompt(record: Dict[str, str]) -> str:
    present_fields = "\n".join(f"- {k}: {v}" for k, v in record.items() if v is not None)
    return (
        "You are a support ticket router. Given the fields below, reply with "
        f"exactly one queue name from this list: {', '.join(QUEUES)}. "
        "Reply with the queue name only, nothing else.\n\n"
        f"Fields:\n{present_fields}"
    )


def classify_openai(record: Dict[str, str], model: str) -> str:
    from openai import OpenAI  # imported lazily so the offline path has no hard dependency

    client = OpenAI()
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": _build_prompt(record)}],
        temperature=0,
    )
    text = (response.choices[0].message.content or "").strip().lower()
    match = re.search("|".join(QUEUES), text)
    return match.group(0) if match else "general_inquiry"


def classify(record: Dict[str, str], model: str = "gpt-4o-mini", use_openai: Optional[bool] = None) -> str:
    if use_openai is None:
        use_openai = bool(os.environ.get("OPENAI_API_KEY"))
    if use_openai:
        return classify_openai(record, model)
    return classify_rule_based(record)


def count_tokens(text: str, model: str = "gpt-4o-mini") -> int:
    try:
        import tiktoken

        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except ImportError:
        return len(text.split())

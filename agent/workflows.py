"""
Decision-Logic Workflow Engine

Defines the workflow state machine for transaction query resolution.
Each workflow type maps to a set of decision rules applied before and
after the LLM call to determine routing, actions, and escalation logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WorkflowContext:
    """Accumulated context passed through workflow stages."""

    query_id: str
    user_id: str
    query: str
    category: str
    transaction_id: Optional[str] = None
    conversation_history: list[dict] = field(default_factory=list)
    transaction_record: Optional[dict] = None
    workflow_state: str = "received"
    actions_taken: list[str] = field(default_factory=list)

    def advance(self, state: str, action: str) -> None:
        self.workflow_state = state
        self.actions_taken.append(action)


# ── Escalation rules — applied BEFORE LLM call ──────────────────────────────

ESCALATION_KEYWORDS = [
    "fraud",
    "unauthorized",
    "stolen",
    "identity theft",
    "chargeback",
    "legal action",
    "lawsuit",
    "attorney",
]

ALWAYS_ESCALATE_CATEGORIES = {"fraud_alert"}


def should_pre_escalate(ctx: WorkflowContext) -> tuple[bool, Optional[str]]:
    """
    Check if the query should be escalated before hitting the LLM.
    Returns (should_escalate, reason).
    """
    if ctx.category in ALWAYS_ESCALATE_CATEGORIES:
        return True, f"Category '{ctx.category}' requires immediate human review"

    query_lower = ctx.query.lower()
    for kw in ESCALATION_KEYWORDS:
        if kw in query_lower:
            return True, f"High-risk keyword detected: '{kw}'"

    return False, None


def should_post_escalate(confidence: float, classification: str, threshold: float) -> tuple[bool, Optional[str]]:
    """
    Check if the LLM's answer should be escalated post-processing.
    Returns (should_escalate, reason).
    """
    if confidence < threshold:
        return True, f"LLM confidence {confidence:.2f} below threshold {threshold:.2f}"
    if classification == "escalate":
        return True, "LLM explicitly recommended human escalation"
    return False, None


# ── Category-specific prompt augmentations ───────────────────────────────────

CATEGORY_CONTEXT: dict[str, str] = {
    "payment_status": (
        "The user is asking about a payment's processing status. "
        "Standard ACH/card payments take 1–3 business days. "
        "If the payment has been pending more than 5 business days, recommend contacting the bank."
    ),
    "refund_request": (
        "The user is requesting a refund. Refunds typically take 5–10 business days to appear. "
        "Verify whether the refund has been initiated; if not, explain the dispute process."
    ),
    "dispute": (
        "The user is disputing a transaction. Acknowledge the dispute, explain the review process "
        "(typically 10 business days), and confirm the user's rights under Regulation E."
    ),
    "account_inquiry": (
        "The user has a general account question. Answer accurately and concisely. "
        "Do not share sensitive account details; direct to secure channels if needed."
    ),
    "billing_error": (
        "The user believes there is a billing error. Ask for the specific transaction details, "
        "confirm the error, and outline steps to correct it."
    ),
    "general": (
        "This is a general transaction or account inquiry. Answer helpfully and concisely."
    ),
}


def get_category_context(category: str) -> str:
    return CATEGORY_CONTEXT.get(category, CATEGORY_CONTEXT["general"])

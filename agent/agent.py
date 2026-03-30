"""
AI Workflow Automation Agent

Architecture:
  Input → Pre-check (rule-based escalation) → Context Load (MongoDB)
       → LLM Call (OpenAI GPT with engineered prompt) → Post-check
       → RESOLVED or ESCALATED → Persist to MongoDB
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Optional

import structlog
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from agent.config import settings
from agent.database import get_conversation_history, get_transaction_record
from agent.models import QueryInput, QueryResolution
from agent.workflows import (
    WorkflowContext,
    get_category_context,
    should_post_escalate,
    should_pre_escalate,
)

logger = structlog.get_logger(__name__)

# ── System prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an intelligent transaction support agent for a financial services platform.

Your role is to resolve customer queries about transactions, payments, and accounts through structured decision-logic.

## Response Guidelines
1. Analyze the user's query in the context of their transaction history (if provided)
2. Provide a clear, accurate, and empathetic resolution
3. If the issue cannot be resolved with certainty, recommend escalation rather than guessing
4. Keep responses concise — under 150 words unless complexity requires more

## Output Format (raw JSON only, no markdown)
{
  "resolution": "<your response to the user>",
  "confidence": <float 0.0–1.0>,
  "classification": "resolved" | "escalate",
  "actions": [<list of actions taken, e.g. "checked_transaction_status", "applied_refund_policy">]
}

## Classification Rules
- "resolved": You are confident (≥ 0.85) the resolution is accurate and complete
- "escalate": The issue requires human review (fraud, complex disputes, missing transaction data, confidence < 0.85)"""


def _build_user_message(ctx: WorkflowContext) -> str:
    parts = []

    if ctx.transaction_record:
        txn = ctx.transaction_record
        parts.append(
            f"[TRANSACTION RECORD]\n"
            f"ID: {txn.get('transaction_id')}\n"
            f"Amount: ${txn.get('amount')}\n"
            f"Status: {txn.get('status')}\n"
            f"Merchant: {txn.get('merchant')}\n"
            f"Date: {txn.get('date')}\n"
        )

    if ctx.conversation_history:
        history_str = "\n".join(
            f"Q: {h.get('query', '')} → A: {h.get('resolution', '')}"
            for h in ctx.conversation_history
        )
        parts.append(f"[RECENT HISTORY]\n{history_str}\n")

    category_ctx = get_category_context(ctx.category)
    parts.append(f"[CATEGORY CONTEXT]\n{category_ctx}\n")
    parts.append(f"[USER QUERY]\n{ctx.query}")

    return "\n\n".join(parts)


class WorkflowAgent:
    """
    LLM-powered workflow agent for transaction query resolution.

    Implements a full decision-logic pipeline:
      pre-escalation check → context load → LLM reasoning → post-escalation check → persist
    """

    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def resolve(self, query_input: QueryInput) -> QueryResolution:
        query_id = str(uuid.uuid4())
        log = logger.bind(query_id=query_id, user_id=query_input.user_id, category=query_input.category)
        start = time.perf_counter()

        ctx = WorkflowContext(
            query_id=query_id,
            user_id=query_input.user_id,
            query=query_input.query,
            category=query_input.category,
            transaction_id=query_input.transaction_id,
        )

        # Stage 1: Pre-escalation rule check
        ctx.advance("received", "query_received")
        escalate, reason = should_pre_escalate(ctx)
        if escalate:
            latency = (time.perf_counter() - start) * 1000
            log.warning("pre_escalated", reason=reason)
            return QueryResolution(
                query_id=query_id,
                workflow_state="escalated",
                resolution="Your query has been escalated to a specialist for immediate review.",
                confidence=1.0,
                escalated=True,
                escalation_reason=reason,
                actions_taken=ctx.actions_taken,
                latency_ms=round(latency, 2),
            )

        # Stage 2: Load context from MongoDB
        ctx.advance("context_loaded", "context_loaded")
        ctx.conversation_history = await get_conversation_history(query_input.user_id)
        if query_input.transaction_id:
            ctx.transaction_record = await get_transaction_record(query_input.transaction_id)
            if ctx.transaction_record:
                ctx.actions_taken.append("fetched_transaction_record")

        # Stage 3: LLM processing
        ctx.advance("llm_processing", "llm_called")
        parsed = await self._call_llm(ctx)

        # Stage 4: Post-escalation check
        escalate, reason = should_post_escalate(
            confidence=parsed["confidence"],
            classification=parsed["classification"],
            threshold=settings.CONFIDENCE_THRESHOLD,
        )

        latency = (time.perf_counter() - start) * 1000
        final_state = "escalated" if escalate else "resolved"
        ctx.advance(final_state, "decision_finalized")

        resolution_text = (
            "Your query has been escalated to a specialist for review. You will be contacted within 24 hours."
            if escalate else parsed["resolution"]
        )

        log.info(
            "query_resolved",
            state=final_state,
            confidence=parsed["confidence"],
            latency_ms=round(latency, 2),
        )

        return QueryResolution(
            query_id=query_id,
            workflow_state=final_state,
            resolution=resolution_text,
            confidence=parsed["confidence"],
            escalated=escalate,
            escalation_reason=reason,
            actions_taken=ctx.actions_taken + parsed.get("actions", []),
            latency_ms=round(latency, 2),
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
    async def _call_llm(self, ctx: WorkflowContext) -> dict:
        response = await self._client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_message(ctx)},
            ],
            max_tokens=400,
            temperature=0.15,
        )
        raw = response.choices[0].message.content or "{}"
        return self._parse(raw)

    def _parse(self, raw: str) -> dict:
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1])
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {
                "resolution": "I was unable to fully process your request. A specialist will follow up.",
                "confidence": 0.0,
                "classification": "escalate",
                "actions": [],
            }

        classification = parsed.get("classification", "escalate")
        if classification not in ("resolved", "escalate"):
            classification = "escalate"

        confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0.0))))

        return {
            "resolution": str(parsed.get("resolution", "")),
            "confidence": confidence,
            "classification": classification,
            "actions": [str(a) for a in parsed.get("actions", [])],
        }


agent = WorkflowAgent()

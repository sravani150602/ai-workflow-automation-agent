"""Unit tests for the WorkflowAgent and decision-logic pipeline."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.models import QueryInput
from agent.workflows import should_post_escalate, should_pre_escalate, WorkflowContext


class TestPreEscalation:
    def _ctx(self, query: str, category: str = "general") -> WorkflowContext:
        return WorkflowContext(
            query_id="q_test",
            user_id="usr_test",
            query=query,
            category=category,
        )

    def test_fraud_alert_always_escalates(self):
        ctx = self._ctx("my payment was rejected", "fraud_alert")
        escalate, reason = should_pre_escalate(ctx)
        assert escalate is True
        assert "fraud_alert" in reason

    def test_fraud_keyword_triggers_escalation(self):
        ctx = self._ctx("there was an unauthorized charge on my account")
        escalate, reason = should_pre_escalate(ctx)
        assert escalate is True
        assert "unauthorized" in reason

    def test_normal_query_does_not_escalate(self):
        ctx = self._ctx("why is my payment still pending?", "payment_status")
        escalate, reason = should_pre_escalate(ctx)
        assert escalate is False
        assert reason is None

    def test_dispute_category_does_not_auto_escalate(self):
        ctx = self._ctx("I want to dispute a charge", "dispute")
        escalate, _ = should_pre_escalate(ctx)
        assert escalate is False  # Goes to LLM first


class TestPostEscalation:
    def test_low_confidence_escalates(self):
        escalate, reason = should_post_escalate(0.70, "resolved", 0.85)
        assert escalate is True
        assert "0.70" in reason

    def test_high_confidence_resolves(self):
        escalate, reason = should_post_escalate(0.92, "resolved", 0.85)
        assert escalate is False
        assert reason is None

    def test_llm_escalate_classification_triggers(self):
        escalate, reason = should_post_escalate(0.90, "escalate", 0.85)
        assert escalate is True
        assert "human escalation" in reason

    def test_exact_threshold_resolves(self):
        escalate, _ = should_post_escalate(0.85, "resolved", 0.85)
        assert escalate is False


class TestResponseParsing:
    def setup_method(self):
        from agent.agent import WorkflowAgent
        self.agent = WorkflowAgent.__new__(WorkflowAgent)

    def test_parses_valid_resolved_response(self):
        raw = json.dumps({
            "resolution": "Your payment is processing normally.",
            "confidence": 0.93,
            "classification": "resolved",
            "actions": ["checked_transaction_status"],
        })
        result = self.agent._parse(raw)
        assert result["classification"] == "resolved"
        assert result["confidence"] == 0.93
        assert "checked_transaction_status" in result["actions"]

    def test_strips_markdown_fences(self):
        raw = "```json\n{\"resolution\": \"ok\", \"confidence\": 0.9, \"classification\": \"resolved\", \"actions\": []}\n```"
        result = self.agent._parse(raw)
        assert result["classification"] == "resolved"

    def test_invalid_json_returns_escalate_fallback(self):
        result = self.agent._parse("not json at all")
        assert result["classification"] == "escalate"
        assert result["confidence"] == 0.0

    def test_clamps_confidence_bounds(self):
        raw = json.dumps({"resolution": "r", "confidence": 1.8, "classification": "resolved", "actions": []})
        result = self.agent._parse(raw)
        assert result["confidence"] == 1.0

        raw = json.dumps({"resolution": "r", "confidence": -0.5, "classification": "resolved", "actions": []})
        result = self.agent._parse(raw)
        assert result["confidence"] == 0.0

    def test_unknown_classification_defaults_to_escalate(self):
        raw = json.dumps({"resolution": "r", "confidence": 0.9, "classification": "unknown", "actions": []})
        result = self.agent._parse(raw)
        assert result["classification"] == "escalate"


@pytest.mark.asyncio
class TestAgentResolve:
    @patch("agent.agent.get_conversation_history", new_callable=AsyncMock, return_value=[])
    @patch("agent.agent.get_transaction_record", new_callable=AsyncMock, return_value=None)
    @patch("agent.agent.AsyncOpenAI")
    async def test_resolves_normal_query(self, MockOpenAI, mock_txn, mock_history):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = json.dumps({
            "resolution": "Your payment is processing normally.",
            "confidence": 0.93,
            "classification": "resolved",
            "actions": ["checked_transaction_status"],
        })
        mock_client = AsyncMock()
        mock_client.chat.completions.create.return_value = mock_response
        MockOpenAI.return_value = mock_client

        from agent.agent import WorkflowAgent
        wf_agent = WorkflowAgent()
        result = await wf_agent.resolve(QueryInput(
            user_id="usr_test",
            query="Why is my payment still pending?",
            category="payment_status",
        ))

        assert result.workflow_state == "resolved"
        assert result.escalated is False
        assert result.confidence == 0.93

    async def test_fraud_alert_pre_escalates(self):
        from agent.agent import WorkflowAgent
        wf_agent = WorkflowAgent()
        result = await wf_agent.resolve(QueryInput(
            user_id="usr_test",
            query="There is an unauthorized charge on my account",
            category="fraud_alert",
        ))
        assert result.workflow_state == "escalated"
        assert result.escalated is True

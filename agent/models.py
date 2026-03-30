"""Pydantic models for transaction queries and workflow state."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

QueryCategory = Literal[
    "payment_status",
    "refund_request",
    "dispute",
    "account_inquiry",
    "fraud_alert",
    "billing_error",
    "general",
]

WorkflowState = Literal[
    "received",
    "context_loaded",
    "llm_processing",
    "resolved",
    "escalated",
]


class QueryInput(BaseModel):
    """Incoming transaction query from a user."""

    user_id: str = Field(..., description="User identifier")
    query: str = Field(..., min_length=5, max_length=2000, description="The user's query text")
    transaction_id: Optional[str] = Field(None, description="Related transaction ID if applicable")
    category: QueryCategory = Field("general", description="Query category for routing")

    model_config = {
        "json_schema_extra": {
            "example": {
                "user_id": "usr_8821",
                "query": "My payment of $149.99 is showing as pending for 3 days. Is this normal?",
                "transaction_id": "txn_abc123",
                "category": "payment_status",
            }
        }
    }


class QueryResolution(BaseModel):
    """Result from the workflow agent for a single query."""

    query_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_state: WorkflowState = Field(..., description="Final workflow state")
    resolution: str = Field(..., description="Agent-generated resolution text")
    confidence: float = Field(..., ge=0.0, le=1.0, description="LLM confidence score")
    escalated: bool = Field(..., description="True if escalated to a human agent")
    escalation_reason: Optional[str] = Field(None, description="Reason for escalation if applicable")
    actions_taken: list[str] = Field(default_factory=list, description="Workflow actions executed")
    latency_ms: float = Field(..., description="End-to-end processing latency in ms")
    resolved_at: datetime = Field(default_factory=datetime.utcnow)


class FeedbackInput(BaseModel):
    """Human feedback on an agent resolution."""

    accurate: bool = Field(..., description="Was the resolution accurate?")
    human_resolution: Optional[str] = Field(None, description="Correct resolution if agent was wrong")
    notes: Optional[str] = Field(None, max_length=1000)


class MetricsResponse(BaseModel):
    """Aggregate workflow performance metrics."""

    total_queries: int
    resolved_count: int
    escalated_count: int
    resolution_rate: float
    escalation_rate: float
    avg_latency_ms: float
    accuracy_from_feedback: Optional[float]
    queries_per_category: dict[str, int]

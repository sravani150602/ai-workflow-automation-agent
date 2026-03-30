"""
FastAPI application — AI Workflow Automation Agent

REST API that exposes the workflow agent for transaction query resolution.
All decisions are persisted to MongoDB for audit and evaluation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

import structlog
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from agent.agent import agent
from agent.database import close_client, get_database, save_feedback, save_query_record
from agent.models import FeedbackInput, MetricsResponse, QueryInput, QueryResolution

logger = structlog.get_logger(__name__)

app = FastAPI(
    title="AI Workflow Automation Agent",
    description=(
        "An LLM-powered assistant that automates transaction query resolution "
        "through decision-logic workflows. Built with OpenAI GPT, FastAPI, and MongoDB."
    ),
    version="1.0.0",
    contact={
        "name": "Sravani Elavarthi",
        "url": "https://github.com/sravani150602",
    },
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown() -> None:
    await close_client()


# ── Health ───────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health_check() -> dict:
    return {"status": "ok", "service": "ai-workflow-automation-agent", "timestamp": datetime.utcnow().isoformat()}


# ── Query resolution ─────────────────────────────────────────────────────────

@app.post("/query", response_model=QueryResolution, tags=["Agent"])
async def submit_query(query_input: QueryInput) -> QueryResolution:
    """
    Submit a transaction query for automated resolution.

    The agent runs the full decision-logic workflow pipeline:
    pre-escalation check → context load → LLM reasoning → post-escalation check.
    Every resolution is persisted to MongoDB.
    """
    result = await agent.resolve(query_input)

    record = {
        "query_id": result.query_id,
        "user_id": query_input.user_id,
        "query": query_input.query,
        "transaction_id": query_input.transaction_id,
        "category": query_input.category,
        "workflow_state": result.workflow_state,
        "resolution": result.resolution,
        "confidence": result.confidence,
        "escalated": result.escalated,
        "escalation_reason": result.escalation_reason,
        "actions_taken": result.actions_taken,
        "latency_ms": result.latency_ms,
        "resolved_at": result.resolved_at,
    }
    await save_query_record(record)

    return result


@app.get("/query/{query_id}", tags=["Agent"])
async def get_query(query_id: str) -> dict:
    """Retrieve a query's full record including resolution history."""
    db = get_database()
    doc = await db.queries.find_one({"query_id": query_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Query not found")
    return doc


@app.get("/queries", tags=["Agent"])
async def list_queries(
    workflow_state: Optional[Literal["resolved", "escalated"]] = Query(None),
    category: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    escalated: Optional[bool] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    """List all queries with optional filters."""
    db = get_database()
    filt: dict = {}
    if workflow_state:
        filt["workflow_state"] = workflow_state
    if category:
        filt["category"] = category
    if user_id:
        filt["user_id"] = user_id
    if escalated is not None:
        filt["escalated"] = escalated

    total = await db.queries.count_documents(filt)
    cursor = db.queries.find(filt, {"_id": 0}).sort("resolved_at", -1).skip(offset).limit(limit)
    docs = await cursor.to_list(length=limit)

    return {"total": total, "limit": limit, "offset": offset, "queries": docs}


@app.post("/query/{query_id}/escalate", tags=["Agent"])
async def manually_escalate(query_id: str, reason: str = Query(..., min_length=5)) -> dict:
    """Manually escalate a query to a human agent."""
    db = get_database()
    result = await db.queries.update_one(
        {"query_id": query_id},
        {"$set": {"workflow_state": "escalated", "escalated": True, "escalation_reason": reason}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Query not found")
    return {"status": "escalated", "query_id": query_id, "reason": reason}


@app.post("/query/{query_id}/feedback", tags=["Agent"])
async def submit_feedback(query_id: str, feedback: FeedbackInput) -> dict:
    """Submit accuracy feedback on an agent resolution."""
    db = get_database()
    if not await db.queries.find_one({"query_id": query_id}):
        raise HTTPException(status_code=404, detail="Query not found")

    await save_feedback(query_id, feedback.model_dump())
    return {"status": "feedback_recorded", "query_id": query_id}


# ── Metrics ──────────────────────────────────────────────────────────────────

@app.get("/metrics", response_model=MetricsResponse, tags=["Metrics"])
async def get_metrics() -> MetricsResponse:
    """Aggregate workflow performance metrics."""
    db = get_database()

    total = await db.queries.count_documents({})
    resolved = await db.queries.count_documents({"workflow_state": "resolved"})
    escalated = await db.queries.count_documents({"workflow_state": "escalated"})

    # Average latency
    pipeline = [{"$group": {"_id": None, "avg_latency": {"$avg": "$latency_ms"}}}]
    agg = await db.queries.aggregate(pipeline).to_list(length=1)
    avg_latency = agg[0]["avg_latency"] if agg else 0.0

    # Accuracy from feedback
    feedback_docs = await db.queries.count_documents({"feedback": {"$exists": True}})
    correct = await db.queries.count_documents({"feedback.accurate": True})
    accuracy = round(correct / feedback_docs, 4) if feedback_docs > 0 else None

    # Per-category breakdown
    cat_pipeline = [{"$group": {"_id": "$category", "count": {"$sum": 1}}}]
    cat_agg = await db.queries.aggregate(cat_pipeline).to_list(length=20)
    per_category = {doc["_id"]: doc["count"] for doc in cat_agg}

    return MetricsResponse(
        total_queries=total,
        resolved_count=resolved,
        escalated_count=escalated,
        resolution_rate=round(resolved / total, 4) if total else 0.0,
        escalation_rate=round(escalated / total, 4) if total else 0.0,
        avg_latency_ms=round(avg_latency, 2),
        accuracy_from_feedback=accuracy,
        queries_per_category=per_category,
    )

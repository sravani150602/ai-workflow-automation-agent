"""MongoDB async connection and context retrieval using Motor."""

from __future__ import annotations

from typing import Optional

import structlog
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from agent.config import settings

logger = structlog.get_logger(__name__)

_client: Optional[AsyncIOMotorClient] = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.MONGO_URI)
    return _client


def get_database() -> AsyncIOMotorDatabase:
    return get_client()[settings.MONGO_DB_NAME]


async def close_client() -> None:
    global _client
    if _client:
        _client.close()
        _client = None


async def get_conversation_history(user_id: str, limit: int | None = None) -> list[dict]:
    """
    Retrieve recent conversation history for a user to inject as context.
    Returns messages in chronological order (oldest first).
    """
    limit = limit or settings.MAX_CONTEXT_MESSAGES
    db = get_database()
    cursor = (
        db.queries
        .find(
            {"user_id": user_id, "workflow_state": {"$in": ["resolved", "escalated"]}},
            {"query": 1, "resolution": 1, "category": 1, "resolved_at": 1}
        )
        .sort("resolved_at", -1)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    # Reverse so oldest is first (chronological for the prompt)
    return list(reversed(docs))


async def get_transaction_record(transaction_id: str) -> Optional[dict]:
    """Fetch a transaction record from MongoDB by ID."""
    if not transaction_id:
        return None
    db = get_database()
    return await db.transactions.find_one({"transaction_id": transaction_id})


async def save_query_record(record: dict) -> str:
    """Persist a query resolution record. Returns the inserted document ID."""
    db = get_database()
    result = await db.queries.insert_one(record)
    return str(result.inserted_id)


async def save_feedback(query_id: str, feedback: dict) -> None:
    """Attach human feedback to an existing query record."""
    db = get_database()
    await db.queries.update_one(
        {"query_id": query_id},
        {"$set": {"feedback": feedback}},
    )

"""
Seed MongoDB with sample transaction queries and transaction records.

Usage:
    python -m scripts.seed_data
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from agent.database import get_database

DATA_FILE = Path(__file__).parent.parent / "data" / "sample_queries.json"


async def seed() -> None:
    db = get_database()

    # Seed transaction records
    transactions = [
        {"transaction_id": "txn_abc123", "amount": 149.99, "status": "pending", "merchant": "Netflix", "date": "2024-03-05"},
        {"transaction_id": "txn_def456", "amount": 299.00, "status": "completed", "merchant": "Amazon", "date": "2024-03-01"},
        {"transaction_id": "txn_ghi789", "amount": 50.00, "status": "failed", "merchant": "Spotify", "date": "2024-03-03"},
        {"transaction_id": "txn_jkl012", "amount": 1200.00, "status": "pending", "merchant": "Best Buy", "date": "2024-03-04"},
    ]
    for txn in transactions:
        await db.transactions.update_one(
            {"transaction_id": txn["transaction_id"]},
            {"$set": txn},
            upsert=True,
        )
    print(f"  ✓ Seeded {len(transactions)} transaction records")

    # Seed sample queries
    with open(DATA_FILE) as f:
        queries = json.load(f)

    for q in queries:
        q["resolved_at"] = datetime.utcnow()
        await db.queries.update_one(
            {"query_id": q["query_id"]},
            {"$set": q},
            upsert=True,
        )
    print(f"  ✓ Seeded {len(queries)} sample queries")
    print("\nSeed complete. Start the API server: uvicorn api.main:app --reload")


if __name__ == "__main__":
    asyncio.run(seed())

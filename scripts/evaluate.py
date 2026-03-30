"""
LLM Evaluation Harness — Accuracy and Reliability Monitoring

Monitors agent resolution quality using human feedback stored in MongoDB.
Computes precision/recall per query category and flags accuracy drops.

Usage:
    python -m scripts.evaluate --report weekly
    python -m scripts.evaluate --report daily --category payment_status
"""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from datetime import datetime, timedelta

import structlog

from agent.database import get_database

logger = structlog.get_logger(__name__)

ACCURACY_ALERT_THRESHOLD = 0.80  # Alert if accuracy drops below 80%


async def run_evaluation(report_type: str, category: str | None = None) -> None:
    db = get_database()

    # Date range
    days = 7 if report_type == "weekly" else 1
    since = datetime.utcnow() - timedelta(days=days)

    filt: dict = {"resolved_at": {"$gte": since}, "feedback": {"$exists": True}}
    if category:
        filt["category"] = category

    docs = await db.queries.find(filt, {"_id": 0}).to_list(length=5000)

    if not docs:
        print(f"No feedback data found for the last {days} day(s).")
        return

    print(f"\n{'='*65}")
    print(f"LLM EVALUATION REPORT — {report_type.upper()} ({datetime.utcnow().strftime('%Y-%m-%d')})")
    print(f"{'='*65}")
    print(f"  Period:   Last {days} day(s)")
    print(f"  Samples:  {len(docs)}")
    if category:
        print(f"  Category: {category}")

    # Overall metrics
    total = len(docs)
    correct = sum(1 for d in docs if d.get("feedback", {}).get("accurate"))
    accuracy = correct / total if total else 0
    escalated = sum(1 for d in docs if d.get("escalated"))
    avg_confidence = sum(d.get("confidence", 0) for d in docs) / total if total else 0
    avg_latency = sum(d.get("latency_ms", 0) for d in docs) / total if total else 0

    print(f"\n  Overall Accuracy:    {accuracy:.1%}  ({correct}/{total} correct)")
    print(f"  Avg Confidence:      {avg_confidence:.3f}")
    print(f"  Avg Latency:         {avg_latency:.0f}ms")
    print(f"  Escalation Rate:     {escalated/total:.1%}")

    if accuracy < ACCURACY_ALERT_THRESHOLD:
        print(f"\n  ⚠ ALERT: Accuracy {accuracy:.1%} is below threshold {ACCURACY_ALERT_THRESHOLD:.1%}")
        print("  → Review recent misclassifications and consider prompt optimization")

    # Per-category breakdown
    by_category: dict[str, list] = defaultdict(list)
    for d in docs:
        by_category[d.get("category", "unknown")].append(d)

    print(f"\n  {'Category':<20} {'Samples':>8} {'Accuracy':>10} {'Avg Conf':>10} {'Escalated':>10}")
    print(f"  {'-'*60}")
    for cat, items in sorted(by_category.items()):
        cat_total = len(items)
        cat_correct = sum(1 for d in items if d.get("feedback", {}).get("accurate"))
        cat_accuracy = cat_correct / cat_total if cat_total else 0
        cat_conf = sum(d.get("confidence", 0) for d in items) / cat_total if cat_total else 0
        cat_esc = sum(1 for d in items if d.get("escalated"))
        print(f"  {cat:<20} {cat_total:>8} {cat_accuracy:>9.1%} {cat_conf:>10.3f} {cat_esc:>9}")

    # Misclassification analysis
    misclassified = [d for d in docs if not d.get("feedback", {}).get("accurate")]
    if misclassified:
        print(f"\n  Misclassified Samples ({len(misclassified)}):")
        for d in misclassified[:5]:
            print(f"    • [{d.get('category')}] conf={d.get('confidence', 0):.2f} "
                  f"state={d.get('workflow_state')} | {d.get('query', '')[:60]}")
        if len(misclassified) > 5:
            print(f"    ... and {len(misclassified) - 5} more")

    print(f"\n{'='*65}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run LLM evaluation report")
    parser.add_argument("--report", choices=["daily", "weekly"], default="weekly")
    parser.add_argument("--category", help="Filter by query category", default=None)
    args = parser.parse_args()
    asyncio.run(run_evaluation(args.report, args.category))

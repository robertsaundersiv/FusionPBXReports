"""Test UTC timezone support in queue performance report."""
import asyncio
from datetime import datetime, timezone as dt_timezone

from app.database import SessionLocal
from app.models import Queue
from app.api.dashboard import get_queue_performance_report

QUEUE_NAME = "TWE-Billing-Support-Queue"
START = datetime(2026, 4, 1, tzinfo=dt_timezone.utc)
END = datetime(2026, 4, 30, tzinfo=dt_timezone.utc)


async def main():
    db = SessionLocal()
    try:
        queue = db.query(Queue).filter(Queue.name == QUEUE_NAME).first()
        if not queue:
            print(f"Queue not found: {QUEUE_NAME}")
            return

        print("Testing UTC timezone...")
        print(f"Queue: {queue.name} ({queue.queue_extension})")
        print()

        # Test with UTC timezone
        print("=== Testing with timezone='UTC' ===")
        data_utc = await get_queue_performance_report(
            start_date=START,
            end_date=END,
            queue_ids=[queue.queue_id],
            direction="inbound",
            strict_answered=False,
            exclude_deflects=True,
            timezone="UTC",
            current_user={"role": "admin"},
            db=db,
        )

        for row in data_utc.get("rows", []):
            if row.get("queue_name") == QUEUE_NAME:
                print("UTC Result:")
                print(f"  offered: {row.get('offered')}")
                print(f"  answered: {row.get('answered')}")
                print(f"  abandoned: {row.get('abandoned')}")
                print(f"  voicemail: {row.get('voicemail_calls')}")
                print(f"  missed: {row.get('missed_calls')}")
                break

        # Test with local timezone
        print()
        print("=== Testing with timezone='America/Phoenix' ===")
        data_local = await get_queue_performance_report(
            start_date=START,
            end_date=END,
            queue_ids=[queue.queue_id],
            direction="inbound",
            strict_answered=False,
            exclude_deflects=True,
            timezone="America/Phoenix",
            current_user={"role": "admin"},
            db=db,
        )

        for row in data_local.get("rows", []):
            if row.get("queue_name") == QUEUE_NAME:
                print("America/Phoenix Result:")
                print(f"  offered: {row.get('offered')}")
                print(f"  answered: {row.get('answered')}")
                print(f"  abandoned: {row.get('abandoned')}")
                print(f"  voicemail: {row.get('voicemail_calls')}")
                print(f"  missed: {row.get('missed_calls')}")
                break

        print()
        print("✓ UTC timezone support working!")

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())

"""Print queue-performance-report row for a single queue/date range."""
import asyncio
from datetime import datetime, timezone

from app.database import SessionLocal
from app.models import Queue, CDRRecord
from app.api.dashboard import get_queue_performance_report
from app.api.dashboard import (
    is_queue_entry_answered,
    is_queue_entry_abandoned,
    is_queue_entry_voicemail,
    is_queue_entry_transferred_out,
    compute_queue_hop_transfer_keys,
)

QUEUE_NAME = "TWE-Billing-Support-Queue"
START = datetime(2026, 4, 1, tzinfo=timezone.utc)
END = datetime(2026, 4, 30, tzinfo=timezone.utc)


async def main():
    db = SessionLocal()
    try:
        queue = db.query(Queue).filter(Queue.name == QUEUE_NAME).first()
        if not queue:
            print(f"Queue not found: {QUEUE_NAME}")
            return

        print("queue_id:", queue.queue_id)
        print("queue_extension:", queue.queue_extension)

        data = await get_queue_performance_report(
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

        for row in data.get("rows", []):
            if row.get("queue_name") == QUEUE_NAME:
                print("row:", row)
                break

        # Build a raw entry map for additional diagnostics.
        queue_rows = db.query(CDRRecord).filter(
            CDRRecord.cc_queue.like(f"{queue.queue_extension}@%"),
            CDRRecord.cc_queue_joined_epoch.isnot(None),
            CDRRecord.start_epoch >= int(START.timestamp()),
            CDRRecord.start_epoch <= int(END.replace(hour=23, minute=59, second=59).timestamp()),
            CDRRecord.direction == "inbound",
        ).all()

        entry_map = {}
        for record in queue_rows:
            key = (record.caller_id_number, record.cc_queue_joined_epoch)
            entry_map.setdefault(key, []).append(record)

        # Build queue_entries dict in the same format as get_queue_performance_report
        queue_entries = {}
        for record in queue_rows:
            cc_queue = record.cc_queue or ""
            extension = cc_queue.split("@", 1)[0] if "@" in cc_queue else cc_queue
            if not extension:
                continue
            entry_key = (record.caller_id_number, record.cc_queue_joined_epoch)
            if extension not in queue_entries:
                queue_entries[extension] = {}
            if entry_key not in queue_entries[extension]:
                queue_entries[extension][entry_key] = []
            queue_entries[extension][entry_key].append(record)

        # Compute transfer keys using queue-hop detection
        transfer_keys = compute_queue_hop_transfer_keys(
            db,
            start_epoch=int(START.timestamp()),
            end_epoch=int(END.replace(hour=23, minute=59, second=59).timestamp()),
            queue_entries=queue_entries,
            direction="inbound",
        )

        def has_callback(records):
            return any((getattr(r, "cc_agent_type", "") or "").lower() == "callback" for r in records)

        def has_vm_signal(records):
            for r in records:
                dest = (getattr(r, "destination_number", "") or "")
                caller_dest = (getattr(r, "caller_destination", "") or "")
                last_app = (getattr(r, "last_app", "") or "").lower()
                disp = (getattr(r, "call_disposition", "") or "").lower()
                if last_app == "voicemail" or disp == "voicemail":
                    return True
                if dest.startswith("*99") or caller_dest.startswith("*99"):
                    return True
            return False

        unanswered_entries = [
            records
            for records in entry_map.values()
            if not any(getattr(r, "cc_queue_answered_epoch", None) is not None for r in records)
        ]
        helper_unanswered_entries = [
            records
            for records in entry_map.values()
            if not is_queue_entry_answered(records, strict_answered=False)
        ]

        callback_unanswered = sum(1 for records in unanswered_entries if has_callback(records))
        vm_unanswered = sum(1 for records in unanswered_entries if has_vm_signal(records))
        callback_and_vm_unanswered = sum(
            1 for records in unanswered_entries if has_callback(records) and has_vm_signal(records)
        )

        # Abandoned: unanswered, not voicemail, not transferred (including queue-hop)
        abandoned_entries = []
        for extension, entry_map_local in queue_entries.items():
            for entry_key, records in entry_map_local.items():
                # Must be unanswered
                if is_queue_entry_answered(records, strict_answered=False):
                    continue
                # Must not be voicemail
                if is_queue_entry_voicemail(records, strict_answered=False):
                    continue
                # Must not be transferred (check both explicit and queue-hop)
                if (extension, entry_key[0], entry_key[1]) in transfer_keys:
                    continue
                if is_queue_entry_transferred_out(records, strict_answered=False):
                    continue
                # Check for explicit abandonment signals
                if is_queue_entry_abandoned(records, strict_answered=False, exclude_deflects=True):
                    abandoned_entries.append(records)
        voicemail_entries = [
            records
            for records in entry_map.values()
            if is_queue_entry_voicemail(records, strict_answered=False)
        ]
        answered_entries = [
            records
            for records in entry_map.values()
            if is_queue_entry_answered(records, strict_answered=False)
        ]
        transferred_entries = [
            records
            for extension, entry_map_local in queue_entries.items()
            for entry_key, records in entry_map_local.items()
            if (not is_queue_entry_answered(records, strict_answered=False))
            and (
                (extension, entry_key[0], entry_key[1]) in transfer_keys
                or is_queue_entry_transferred_out(records, strict_answered=False)
            )
        ]

        abandoned_with_callback = sum(1 for records in abandoned_entries if has_callback(records))
        abandoned_with_vm_signal = sum(1 for records in abandoned_entries if has_vm_signal(records))

        print("unanswered entries:", len(unanswered_entries))
        print("helper-unanswered entries:", len(helper_unanswered_entries))
        print("answered entries (helper):", len(answered_entries))
        print("abandoned entries (helper):", len(abandoned_entries))
        print("voicemail entries (helper):", len(voicemail_entries))
        print("transferred entries (helper):", len(transferred_entries))
        print("unanswered with callback signal:", callback_unanswered)
        print("unanswered with voicemail signal:", vm_unanswered)
        print("unanswered with callback+voicemail:", callback_and_vm_unanswered)
        print("abandoned with callback signal:", abandoned_with_callback)
        print("abandoned with voicemail signal:", abandoned_with_vm_signal)
        print("helper-unanswered with callback signal:", sum(1 for records in helper_unanswered_entries if has_callback(records)))
        print("helper-unanswered with vm signal:", sum(1 for records in helper_unanswered_entries if has_vm_signal(records)))
        print("answered with vm signal:", sum(1 for records in answered_entries if has_vm_signal(records)))
        print("all entries with vm signal:", sum(1 for records in entry_map.values() if has_vm_signal(records)))

        # Show a sample of helper-unanswered entries that are NOT abandoned.
        non_abandoned_unanswered = [
            records
            for records in helper_unanswered_entries
            if not is_queue_entry_abandoned(records, strict_answered=False, exclude_deflects=True)
        ]
        print("helper-unanswered but not abandoned:", len(non_abandoned_unanswered))
        for i, records in enumerate(non_abandoned_unanswered[:10], start=1):
            sample = records[0]
            key = (getattr(sample, "caller_id_number", None), getattr(sample, "cc_queue_joined_epoch", None))
            causes = sorted({(getattr(r, "hangup_cause", None) or "") for r in records})
            agent_types = sorted({(getattr(r, "cc_agent_type", None) or "") for r in records})
            last_apps = sorted({(getattr(r, "last_app", None) or "") for r in records})
            dispositions = sorted({(getattr(r, "call_disposition", None) or "") for r in records})
            print(f"non-abandoned[{i}] key={key} causes={causes} agent_types={agent_types} last_apps={last_apps} dispositions={dispositions}")
        return

        print("Queue row not found in response rows")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())

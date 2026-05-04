from collections import defaultdict
from datetime import datetime, timezone

from app.database import SessionLocal
from app.models import CDRRecord, Queue
from app.api.dashboard import is_queue_entry_answered


def main() -> None:
    db = SessionLocal()
    try:
        start = int(datetime(2026, 4, 1, tzinfo=timezone.utc).timestamp())
        end = int(datetime(2026, 4, 30, 23, 59, 59, tzinfo=timezone.utc).timestamp())

        twe = db.query(Queue).filter(Queue.name == "TWE-Billing-Support-Queue").first()
        allq = db.query(Queue).filter(Queue.name == "ALL-Billing-Support-Queue").first()

        if not twe or not allq:
            print("Missing queue metadata", bool(twe), bool(allq))
            return

        print("twe_extension", twe.queue_extension)
        print("all_extension", allq.queue_extension)

        rows = db.query(CDRRecord).filter(
            CDRRecord.direction == "inbound",
            CDRRecord.cc_queue_joined_epoch.isnot(None),
            CDRRecord.start_epoch >= start,
            CDRRecord.start_epoch <= end,
        ).all()

        entries = defaultdict(list)
        for r in rows:
            cc = r.cc_queue or ""
            ext = cc.split("@", 1)[0] if "@" in cc else cc
            key = (ext, r.caller_id_number, r.cc_queue_joined_epoch)
            entries[key].append(r)

        by_caller = defaultdict(list)
        for (ext, caller, joined), recs in entries.items():
            if not caller or joined is None:
                continue
            by_caller[caller].append((joined, ext, recs))

        for caller in by_caller:
            by_caller[caller].sort(key=lambda x: x[0])

        unanswered_twe = []
        for (ext, caller, joined), recs in entries.items():
            if ext != twe.queue_extension:
                continue
            if joined is None:
                continue
            if is_queue_entry_answered(recs, strict_answered=False):
                continue
            unanswered_twe.append((caller, joined, recs))

        moved_to_any_other = 0
        moved_to_all = 0
        moved_to_all_300s = 0
        all_deltas = []
        window_counts = {60: 0, 120: 0, 300: 0, 600: 0, 900: 0, 1800: 0, 3600: 0}

        for caller, joined, _ in unanswered_twe:
            if not caller:
                continue

            any_other = False
            all_other = False
            all_300 = False

            min_delta_to_all = None
            for joined2, ext2, _ in by_caller.get(caller, []):
                if joined2 <= joined:
                    continue
                if ext2 == twe.queue_extension:
                    continue

                any_other = True
                if ext2 == allq.queue_extension:
                    all_other = True
                    delta = joined2 - joined
                    all_deltas.append(delta)
                    if min_delta_to_all is None or delta < min_delta_to_all:
                        min_delta_to_all = delta
                    if delta <= 300:
                        all_300 = True

            if any_other:
                moved_to_any_other += 1
            if all_other:
                moved_to_all += 1
            if min_delta_to_all is not None:
                for w in window_counts:
                    if min_delta_to_all <= w:
                        window_counts[w] += 1
            if all_300:
                moved_to_all_300s += 1

        print("unanswered_twe_entries", len(unanswered_twe))
        print("moved_to_any_other_queue", moved_to_any_other)
        print("moved_to_all_queue", moved_to_all)
        print("moved_to_all_within_300s", moved_to_all_300s)
        for w in sorted(window_counts):
            print(f"moved_to_all_within_{w}s", window_counts[w])
        if all_deltas:
            all_deltas.sort()
            n = len(all_deltas)
            p50 = all_deltas[n // 2]
            p90 = all_deltas[int(n * 0.9)]
            p95 = all_deltas[int(n * 0.95)]
            print("delta_to_all_min", all_deltas[0])
            print("delta_to_all_p50", p50)
            print("delta_to_all_p90", p90)
            print("delta_to_all_p95", p95)
            print("delta_to_all_max", all_deltas[-1])
    finally:
        db.close()


if __name__ == "__main__":
    main()

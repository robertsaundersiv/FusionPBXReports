"""
Diagnostic script to investigate why voicemail calls are not being detected
for the billing support queue.

Run inside the backend container:
  docker exec -it phonereports-backend-1 python scripts/debug_voicemail_detection.py

Or locally:
  python backend/scripts/debug_voicemail_detection.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import SessionLocal
from app.models import CDRRecord, Queue
from app.api.dashboard import is_queue_entry_answered, is_queue_entry_voicemail, is_queue_entry_abandoned
from sqlalchemy import text

# ── Config ────────────────────────────────────────────────────────────────────
QUEUE_NAME_PATTERN = "%twe-billing-support-queue%"  # partial match on queues.name
START_EPOCH   = 1743465600    # 2026-04-01 00:00:00 UTC
END_EPOCH     = 1746143999    # 2026-04-30 23:59:59 UTC
# ─────────────────────────────────────────────────────────────────────────────

db = SessionLocal()

print("=" * 70)
print("VOICEMAIL DETECTION DIAGNOSTIC – billing-support queue, Apr 2026")
print("=" * 70)

# 1. Find the queue extension from Queue metadata
queue_rows = (
  db.query(Queue.name, Queue.queue_extension)
  .filter(Queue.name.ilike(QUEUE_NAME_PATTERN))
  .order_by(Queue.name)
  .all()
)

print(f"\n[1] Queue records matching name '{QUEUE_NAME_PATTERN}':")
for name, queue_extension in queue_rows:
  print(f"    name={name}  extension={queue_extension}")

if not queue_rows:
  print("No queue metadata found – check QUEUE_NAME_PATTERN.")
  sys.exit(1)

queue_name, extension = queue_rows[0]
print(f"\n    Using queue: {queue_name}")
print(f"    Using extension: {extension}")

# 2. Overall counts
total = db.execute(text("""
    SELECT COUNT(DISTINCT (caller_id_number, cc_queue_joined_epoch))
    FROM cdr_records
    WHERE cc_queue LIKE :ext_pat
      AND cc_queue_joined_epoch IS NOT NULL
      AND start_epoch BETWEEN :s AND :e
      AND direction = 'inbound'
"""), {"ext_pat": f"{extension}@%", "s": START_EPOCH, "e": END_EPOCH}).scalar()

answered = db.execute(text("""
    SELECT COUNT(DISTINCT (caller_id_number, cc_queue_joined_epoch))
    FROM cdr_records
    WHERE cc_queue LIKE :ext_pat
      AND cc_queue_joined_epoch IS NOT NULL
      AND cc_queue_answered_epoch IS NOT NULL
      AND start_epoch BETWEEN :s AND :e
      AND direction = 'inbound'
"""), {"ext_pat": f"{extension}@%", "s": START_EPOCH, "e": END_EPOCH}).scalar()

print(f"\n[2] Unique queue entries (offered): {total}")
print(f"    Answered (cc_queue_answered_epoch set): {answered}")
print(f"    Unanswered: {total - answered}")

# 3. For unanswered entries – show distinct field values that might signal voicemail
print(f"\n[3] Field value breakdown for UNANSWERED queue entries:")

unanswered_records = db.execute(text("""
    SELECT r.caller_id_number, r.cc_queue_joined_epoch,
           r.hangup_cause, r.cc_cause, r.last_app, r.last_arg,
           r.call_disposition, r.cc_agent_type, r.voicemail_message,
           r.destination_number, r.caller_destination, r.cc_cancel_reason
    FROM cdr_records r
    WHERE r.cc_queue LIKE :ext_pat
      AND r.cc_queue_joined_epoch IS NOT NULL
      AND r.start_epoch BETWEEN :s AND :e
      AND r.direction = 'inbound'
      AND NOT EXISTS (
          SELECT 1 FROM cdr_records r2
          WHERE r2.cc_queue LIKE :ext_pat
            AND r2.caller_id_number = r.caller_id_number
            AND r2.cc_queue_joined_epoch = r.cc_queue_joined_epoch
            AND r2.cc_queue_answered_epoch IS NOT NULL
      )
    ORDER BY r.cc_queue_joined_epoch
"""), {"ext_pat": f"{extension}@%", "s": START_EPOCH, "e": END_EPOCH}).fetchall()

print(f"    Total unanswered CDR rows: {len(unanswered_records)}")

# Count distinct values for key fields
from collections import Counter

def count_field(records, idx, label):
    c = Counter()
    for r in records:
        val = r[idx] if r[idx] is not None else "(NULL)"
        c[val] += 1
    print(f"\n    [{label}] distinct values:")
    for val, cnt in c.most_common(15):
        print(f"        {str(val):<40} count={cnt}")

count_field(unanswered_records, 2,  "hangup_cause")
count_field(unanswered_records, 3,  "cc_cause")
count_field(unanswered_records, 4,  "last_app")
count_field(unanswered_records, 5,  "last_arg")
count_field(unanswered_records, 6,  "call_disposition")
count_field(unanswered_records, 7,  "cc_agent_type")
count_field(unanswered_records, 8,  "voicemail_message")
count_field(unanswered_records, 9,  "destination_number")
count_field(unanswered_records, 10, "caller_destination")
count_field(unanswered_records, 11, "cc_cancel_reason")

# 4. Check for voicemail legs that are SEPARATE CDR records (no cc_queue_joined_epoch)
#    but share the same call via originating_leg_uuid / bridge_uuid
print(f"\n[4] Checking for separate voicemail CDR legs (no cc_queue_joined_epoch)")
print(f"    linked via originating_leg_uuid or bridge_uuid to queue records...")

voicemail_legs = db.execute(text("""
    SELECT v.xml_cdr_uuid, v.last_app, v.last_arg, v.destination_number,
           v.caller_destination, v.call_disposition, v.hangup_cause,
           v.originating_leg_uuid, v.bridge_uuid
    FROM cdr_records v
    WHERE v.start_epoch BETWEEN :s AND :e
      AND v.cc_queue_joined_epoch IS NULL
      AND (
          v.last_app = 'voicemail'
          OR v.call_disposition = 'voicemail'
          OR v.destination_number LIKE '*99%'
          OR v.caller_destination LIKE '*99%'
      )
      AND (
          v.originating_leg_uuid IN (
              SELECT xml_cdr_uuid FROM cdr_records
              WHERE cc_queue LIKE :ext_pat
                AND cc_queue_joined_epoch IS NOT NULL
                AND start_epoch BETWEEN :s AND :e
          )
          OR v.bridge_uuid IN (
              SELECT xml_cdr_uuid FROM cdr_records
              WHERE cc_queue LIKE :ext_pat
                AND cc_queue_joined_epoch IS NOT NULL
                AND start_epoch BETWEEN :s AND :e
          )
      )
    LIMIT 20
"""), {"ext_pat": f"{extension}@%", "s": START_EPOCH, "e": END_EPOCH}).fetchall()

print(f"    Found {len(voicemail_legs)} voicemail legs linked to queue entries")
for r in voicemail_legs[:5]:
    print(f"      uuid={r[0][:8]}  last_app={r[1]}  dest={r[2]}  call_disp={r[5]}  orig_leg={str(r[7])[:8] if r[7] else 'NULL'}  bridge={str(r[8])[:8] if r[8] else 'NULL'}")

# 5. Sample 10 unanswered entries to see full field picture
print(f"\n[5] Sample 10 unanswered queue entries (full voicemail-relevant fields):")
for i, r in enumerate(unanswered_records[:10]):
    print(f"\n  Entry {i+1}:")
    print(f"    caller_id    = {r[0]}")
    print(f"    joined_epoch = {r[1]}")
    print(f"    hangup_cause = {r[2]}")
    print(f"    cc_cause     = {r[3]}")
    print(f"    last_app     = {r[4]}")
    print(f"    last_arg     = {r[5]}")
    print(f"    call_disp    = {r[6]}")
    print(f"    cc_agent_type= {r[7]}")
    print(f"    vm_message   = {r[8]}")
    print(f"    dest_number  = {r[9]}")
    print(f"    caller_dest  = {r[10]}")
    print(f"    cc_cancel    = {r[11]}")

# 6. Recompute outcomes using the same helper logic used by API endpoints.
queue_rows = db.query(CDRRecord).filter(
    CDRRecord.cc_queue.like(f"{extension}@%"),
    CDRRecord.cc_queue_joined_epoch.isnot(None),
    CDRRecord.start_epoch >= START_EPOCH,
    CDRRecord.start_epoch <= END_EPOCH,
    CDRRecord.direction == "inbound",
).all()

entry_map = {}
for record in queue_rows:
    key = (record.caller_id_number, record.cc_queue_joined_epoch)
    if key not in entry_map:
        entry_map[key] = []
    entry_map[key].append(record)

offered_api = len(entry_map)
answered_api = sum(1 for records in entry_map.values() if is_queue_entry_answered(records, strict_answered=False))
voicemail_api = sum(1 for records in entry_map.values() if is_queue_entry_voicemail(records, strict_answered=False))
abandoned_api = sum(1 for records in entry_map.values() if is_queue_entry_abandoned(records, strict_answered=False, exclude_deflects=True))
missed_api = voicemail_api + abandoned_api

print("\n[6] Endpoint-style outcome totals (current helper logic):")
print(f"    offered   = {offered_api}")
print(f"    answered  = {answered_api}")
print(f"    abandoned = {abandoned_api}")
print(f"    voicemail = {voicemail_api}")
print(f"    missed    = {missed_api}")

print("\n" + "=" * 70)
print("DONE")
print("=" * 70)
db.close()

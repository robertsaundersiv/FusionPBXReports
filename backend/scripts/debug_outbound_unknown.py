"""
Diagnostic script to investigate unknown outbound call attribution.
Run inside the backend container: docker exec -it phonereports-backend-1 python scripts/debug_outbound_unknown.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import SessionLocal
from app.models import CDRRecord
from sqlalchemy import text, func

db = SessionLocal()

print("=" * 70)
print("OUTBOUND CALL ATTRIBUTION DIAGNOSTIC")
print("=" * 70)

# ── 1. Total outbound record counts ──────────────────────────────────────────
total_out = db.query(CDRRecord).filter(CDRRecord.direction == 'outbound').count()
print(f"\n[1] Total outbound records in DB: {total_out}")

# ── 2. Field population rates ────────────────────────────────────────────────
print("\n[2] Field population rates for outbound records:")
fields = [
    'extension_uuid', 'cc_agent_uuid', 'cc_agent',
    'caller_id_name', 'caller_id_number',
]
for field in fields:
    col = getattr(CDRRecord, field)
    filled = db.query(CDRRecord).filter(
        CDRRecord.direction == 'outbound',
        col.isnot(None),
        col != '',
    ).count()
    pct = (filled / total_out * 100) if total_out else 0
    print(f"    {field:<25} {filled:>6} / {total_out}  ({pct:.1f}%)")

# ── 3. Sample of 10 outbound records showing all identifier fields ────────────
print("\n[3] Sample 10 outbound records (identifier fields):")
samples = db.query(CDRRecord).filter(CDRRecord.direction == 'outbound').limit(10).all()
for r in samples:
    print(f"    uuid_short={str(r.xml_cdr_uuid)[:8]}  "
          f"ext_uuid={str(r.extension_uuid)[:12] if r.extension_uuid else 'NULL':<14}  "
          f"cc_agent_uuid={str(r.cc_agent_uuid)[:12] if r.cc_agent_uuid else 'NULL':<14}  "
          f"cc_agent={str(r.cc_agent)[:16] if r.cc_agent else 'NULL':<18}  "
          f"cid_name={str(r.caller_id_name)[:16] if r.caller_id_name else 'NULL':<18}  "
          f"cid_num={str(r.caller_id_number)[:8] if r.caller_id_number else 'NULL'}")

# ── 4. Check Extension table ──────────────────────────────────────────────────
print("\n[4] Extension table:")
result = db.execute(text("SELECT COUNT(*) FROM extensions")).scalar()
print(f"    Total extension rows: {result}")

sample_exts = db.execute(text(
    "SELECT extension_uuid, extension, user_name FROM extensions LIMIT 5"
)).fetchall()
for row in sample_exts:
    print(f"    ext_uuid={str(row[0])[:12] if row[0] else 'NULL':<14}  "
          f"extension={str(row[1])[:8] if row[1] else 'NULL':<10}  "
          f"user_name={row[2]}")

# ── 5. Cross-reference: how many outbound extension_uuids exist in extensions table ──
print("\n[5] Cross-reference extension_uuid (outbound CDR → extensions table):")
matched = db.execute(text("""
    SELECT COUNT(*) FROM cdr_records c
    JOIN extensions e ON c.extension_uuid = e.extension_uuid::text
    WHERE c.direction = 'outbound'
""")).scalar()
print(f"    Outbound records where extension_uuid matches extensions table: {matched}")

# ── 6. Cross-reference: caller_id_number matches an extension number ──────────
print("\n[6] Cross-reference caller_id_number → extensions.extension:")
matched_num = db.execute(text("""
    SELECT COUNT(*) FROM cdr_records c
    JOIN extensions e ON c.caller_id_number = e.extension
    WHERE c.direction = 'outbound'
""")).scalar()
print(f"    Outbound records where caller_id_number matches extensions.extension: {matched_num}")

# ── 7. Top 20 distinct caller_id_number values for outbound ──────────────────
print("\n[7] Top 20 caller_id_number values in outbound records:")
rows = db.execute(text("""
    SELECT caller_id_number, COUNT(*) AS cnt
    FROM cdr_records
    WHERE direction = 'outbound'
    GROUP BY caller_id_number
    ORDER BY cnt DESC
    LIMIT 20
""")).fetchall()
for row in rows:
    print(f"    {str(row[0]):<20}  count={row[1]}")

# ── 8. Top 20 distinct caller_id_name values for outbound ────────────────────
print("\n[8] Top 20 caller_id_name values in outbound records:")
rows = db.execute(text("""
    SELECT caller_id_name, COUNT(*) AS cnt
    FROM cdr_records
    WHERE direction = 'outbound'
    GROUP BY caller_id_name
    ORDER BY cnt DESC
    LIMIT 20
""")).fetchall()
for row in rows:
    print(f"    {str(row[0]):<30}  count={row[1]}")

# ── 9. What extension numbers exist in extensions table ──────────────────────
print("\n[9] All extension numbers in extensions table:")
rows = db.execute(text(
    "SELECT extension, user_name FROM extensions ORDER BY extension LIMIT 30"
)).fetchall()
for row in rows:
    print(f"    ext={str(row[0]):<10}  user={row[1]}")

# ── 10. Agent table sample ────────────────────────────────────────────────────
print("\n[10] Agent table sample (first 10):")
rows = db.execute(text(
    "SELECT agent_uuid, agent_name, extension, agent_contact FROM agents LIMIT 10"
)).fetchall()
for row in rows:
    print(f"    uuid={str(row[0])[:12] if row[0] else 'NULL':<14}  "
          f"name={str(row[1]):<20}  "
          f"ext={str(row[2]):<8}  "
          f"contact={row[3]}")

db.close()
print("\n" + "=" * 70)
print("DIAGNOSTIC COMPLETE")
print("=" * 70)

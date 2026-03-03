"""Check hold time data in CDR records"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

from app.database import SessionLocal
from app.models import CDRRecord
import json

db = SessionLocal()

# Get a record with JSON data
record = db.query(CDRRecord).filter(
    CDRRecord.cc_agent_uuid.isnot(None),
    CDRRecord.json.isnot(None)
).first()

if record and record.json:
    try:
        data = json.loads(record.json)
        print("=" * 60)
        print("CDR JSON Keys from FusionPBX")
        print("=" * 60)
        
        # Look for hold-related keys
        print("\nHold/Accum related keys:")
        hold_keys = [k for k in data.keys() if 'hold' in k.lower() or 'accum' in k.lower()]
        if hold_keys:
            for k in sorted(hold_keys):
                print(f"  {k}: {data[k]}")
        else:
            print("  No hold-related keys found")
        
        print("\nAll JSON keys:")
        for k in sorted(data.keys()):
            print(f"  {k}")
            
    except Exception as e:
        print(f"Error parsing JSON: {e}")
else:
    print("No records found with JSON data")

# Also check database model field
print("\n" + "=" * 60)
print("Database hold_accum_seconds field")
print("=" * 60)
if record:
    print(f"hold_accum_seconds: {record.hold_accum_seconds}")
else:
    print("No record found")

# Check how many records have non-zero hold time
total_with_hold = db.query(CDRRecord).filter(
    CDRRecord.hold_accum_seconds > 0
).count()
total_agent_records = db.query(CDRRecord).filter(
    CDRRecord.cc_agent_uuid.isnot(None)
).count()

print(f"\nRecords with hold > 0: {total_with_hold}")
print(f"Total agent records: {total_agent_records}")
print(f"Percentage: {(total_with_hold / total_agent_records * 100):.2f}%")

db.close()

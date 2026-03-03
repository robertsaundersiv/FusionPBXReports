"""Check agent UUID mapping between CDR and Agent tables."""
from app.database import SessionLocal
from app.models import Agent, CDRRecord
from sqlalchemy import or_

db = SessionLocal()

# Get some UUIDs from CDR records
records = db.query(CDRRecord).filter(
    or_(CDRRecord.cc_agent_uuid.isnot(None), CDRRecord.cc_agent.isnot(None))
).limit(20).all()

print("Checking CDR agent UUIDs against Agent table:\n")

checked_uuids = set()
for record in records:
    # Get the agent ID using the normalize logic
    agent_id = record.cc_agent_uuid if record.cc_agent_uuid else record.cc_agent
    if not agent_id or agent_id in checked_uuids:
        continue
    
    checked_uuids.add(agent_id)
    
    agent = db.query(Agent).filter(Agent.agent_uuid == agent_id).first()
    if agent:
        print(f"✓ {agent_id}: {agent.agent_name} (enabled={agent.enabled})")
    else:
        print(f"✗ {agent_id}: NOT FOUND IN AGENT TABLE")

db.close()

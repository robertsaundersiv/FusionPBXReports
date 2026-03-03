"""Check specific CDR record details."""
from app.database import SessionLocal
from app.models import CDRRecord, Agent
from app.utils.agent_performance_utils import normalize_agent_id

db = SessionLocal()

# Get a few records with both cc_agent_uuid and cc_agent set
records = db.query(CDRRecord).filter(
    CDRRecord.cc_agent.isnot(None)
).limit(5).all()

for i, record in enumerate(records):
    print(f"\n=== Record {i+1} ===")
    print(f"  xml_cdr_uuid: {record.xml_cdr_uuid}")
    print(f"  bridge_uuid: {record.bridge_uuid}")
    print(f"  cc_agent_uuid: {record.cc_agent_uuid}")
    print(f"  cc_agent: {record.cc_agent}")
    print(f"  cc_queue: {record.cc_queue}")
    
    agent_id = normalize_agent_id(record)
    print(f"  Normalized agent_id: {agent_id}")
    
    # Check if this agent exists in the Agent table
    agent = db.query(Agent).filter(Agent.agent_uuid == agent_id).first()
    if agent:
        print(f"  ✓ Agent found: {agent.agent_name}")
    else:
        print(f"  ✗ Agent NOT found with UUID: {agent_id}")
        
        # Check if cc_agent exists instead
        if record.cc_agent and record.cc_agent != agent_id:
            agent2 = db.query(Agent).filter(Agent.agent_uuid == record.cc_agent).first()
            if agent2:
               print(f"  ✓ BUT cc_agent {record.cc_agent} found: {agent2.agent_name}")

db.close()

"""Test the leaderboard logic directly."""
from app.database import SessionLocal
from app.models import CDRRecord, Agent
from app.utils.agent_performance_utils import (
    normalize_agent_id,
    normalize_agent_name,
    get_call_key,
    is_handled,
    is_missed,
    is_excluded,
)
from sqlalchemy import or_
from datetime import datetime, timedelta
from typing import Dict

db = SessionLocal()

# Get time window (last 7 days)
end = datetime.utcnow()
start = end - timedelta(days=7)
start_epoch = int(start.timestamp())
end_epoch = int(end.replace(hour=23, minute=59, second=59).timestamp())

# Build agent name map - include ALL agents
agents = db.query(Agent).all()
agent_name_map = {agent.agent_uuid: agent.agent_name for agent in agents}

print(f"Agent name map has {len(agent_name_map)} entries")
print(f"First 5 agent names: {list(agent_name_map.values())[:5]}\n")

# Query CDR records
query = db.query(CDRRecord).filter(
    CDRRecord.start_epoch >= start_epoch,
    CDRRecord.start_epoch <= end_epoch,
    or_(
        CDRRecord.cc_agent_uuid.isnot(None),
        CDRRecord.cc_agent.isnot(None),
    )
)

records = query.limit(100).all()
print(f"Found {len(records)} CDR records\n")

# Process records
handled_calls: Dict[str, Dict[str, CDRRecord]] = {}
fallback_agent_names: Dict[str, str] = {}

for record in records:
    if is_excluded(record):
        continue

    agent_id = normalize_agent_id(record)
    if not agent_id:
        continue

    call_key = get_call_key(record)
    if not call_key:
        continue

    if agent_id not in fallback_agent_names:
        fallback_agent_names[agent_id] = normalize_agent_name(record, agent_name_map)

    if is_handled(record):
        agent_bucket = handled_calls.setdefault(agent_id, {})
        existing = agent_bucket.get(call_key)
        if existing is None:
            agent_bucket[call_key] = record

# Build agents payload
agents_payload = []
for agent_id, calls in handled_calls.items():
    handled_count = len(calls)
    agent_name_from_map = agent_name_map.get(agent_id)
    agent_name_fallback = fallback_agent_names.get(agent_id, agent_id)
    final_agent_name = agent_name_from_map or agent_name_fallback
    
    agents_payload.append({
        "agent_id": agent_id,
        "agent_name": final_agent_name,
        "handled_calls": handled_count,
        "lookup_result": "MAP" if agent_name_from_map else "FALLBACK"
    })

# Show results
print(f"Processed {len(agents_payload)} agents\n")
print("First 10 agents:")
for agent in sorted(agents_payload, key=lambda x: x['handled_calls'], reverse=True)[:10]:
    print(f"  {agent['agent_id'][:36]}: {agent['agent_name']} - {agent['handled_calls']} calls ({agent['lookup_result']})")

db.close()

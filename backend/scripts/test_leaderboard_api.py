"""Test the leaderboard API endpoint."""
import requests
from datetime import datetime, timedelta
import json

end = datetime.now()
start = end - timedelta(days=7)

try:
    resp = requests.get(
        'http://localhost:8000/api/v1/agent-performance/leaderboard',
        params={
            'start': start.isoformat(),
            'end': end.isoformat()
        },
        headers={'Authorization': 'Bearer test-token-12345'}
    )
    
    print(f"Status Code: {resp.status_code}")
    print(f"\nResponse:")
    data = resp.json()
    
    if 'agents' in data:
        print(f"\nTotal agents: {len(data['agents'])}")
        print(f"\nFirst 5 agents:")
        for agent in data['agents'][:5]:
            print(f"  {agent['agent_id']}: {agent['agent_name']} - {agent['handled_calls']} calls")
    else:
        print(json.dumps(data, indent=2))
        
except Exception as e:
    print(f"Error: {e}")
    print(f"Response text: {resp.text if 'resp' in locals() else 'No response'}")

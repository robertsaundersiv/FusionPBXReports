import asyncio
import json
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.clients.fusionpbx import FusionPBXClient


async def test():
    client = FusionPBXClient()
    await client.initialize()
    
    # Get raw agents response
    url = f"{client.host}/app/api/7/call_center_agents"
    async with client.session.get(url, timeout=30, ssl=False) as response:
        text = await response.text()
        data = json.loads(text)
        
        print("Raw Agents API Response (first item):")
        if isinstance(data, list) and len(data) > 0:
            print(json.dumps(data[0], indent=2))
        elif isinstance(data, dict):
            items = data.get('call_center_agents', [])
            if items:
                print(json.dumps(items[0], indent=2))
        
    await client.close()


if __name__ == "__main__":
    asyncio.run(test())

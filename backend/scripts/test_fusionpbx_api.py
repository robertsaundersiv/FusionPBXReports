"""
Test script to verify FusionPBX API connectivity
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.clients.fusionpbx import get_fusion_client
from app.clients.fusionpbx import logger


async def test_api():
    """Test FusionPBX API endpoints"""
    client = get_fusion_client()
    
    print("=" * 60)
    print("FusionPBX API Connection Test")
    print("=" * 60)
    print(f"Host: {client.host}")
    print(f"API Key: {client.api_key[:10]}..." if len(client.api_key) > 10 else f"API Key: {client.api_key}")
    print()
    
    try:
        await client.initialize()
        
        # Test queues
        print("Testing: /app/api/7/call_center_queues")
        queues = await client.get_call_center_queues()
        print(f"✓ Retrieved {len(queues)} queues")
        if queues:
            print(f"  Sample: {queues[0]}")
        else:
            print(f"  Response appears to be empty - trying to fetch raw data...")
            # Make a raw request to see what we're getting
            url = f"{client.host}/app/api/7/call_center_queues"
            async with client.session.get(url, headers=client._get_headers(), ssl=False) as resp:
                text = await resp.text()
                print(f"  Status: {resp.status}")
                print(f"  Response (first 500 chars): {text[:500]}")
        print()
        
        # Test agents
        print("Testing: /app/api/7/call_center_agents")
        agents = await client.get_call_center_agents()
        print(f"✓ Retrieved {len(agents)} agents")
        if agents:
            print(f"  Sample: {agents[0]}")
        print()
        
        # Test CDR records
        from datetime import datetime, timedelta, timezone
        print("Testing: /app/api/7/xml_cdr")
        
        # Test with date range (last 7 days)
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=7)
        print(f"  Date range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        cdrs = await client.get_xml_cdr(start_date=start_date, end_date=end_date, limit=10)
        print(f"✓ Retrieved {len(cdrs)} CDR records (last 7 days, limit 10)")
        
        if cdrs:
            print(f"  Sample keys: {list(cdrs[0].keys())[:15]}")
            print(f"  Sample: queue={cdrs[0].get('cc_queue')}, direction={cdrs[0].get('direction')}, duration={cdrs[0].get('duration')}")
        print()
        
        print("=" * 60)
        print("All tests completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(test_api())

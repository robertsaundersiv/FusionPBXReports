"""Test hold time data for handled calls with agents"""
import sys
import os
import asyncio
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

from app.clients.fusionpbx import FusionPBXClient
from datetime import datetime, timedelta

async def main():
    client = FusionPBXClient()
    await client.initialize()
    
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        print("=" * 60)
        print("Fetching CDR records with agents from FusionPBX")
        print("=" * 60)
        
        records = await client.get_xml_cdr(
            start_date=start_date,
            end_date=end_date,
            limit=100,
            offset=0
        )
        
        if records:
            print(f"\nGot {len(records)} records total")
            
            # Find records with agents
            agent_records = [r for r in records if r.get('cc_agent_uuid')]
            print(f"Records with agents: {len(agent_records)}")
            
            if agent_records:
                print("\nHold time in agent records:")
                print("-" * 60)
                
                hold_distribution = {}
                for r in agent_records[:20]:  # Show first 20
                    hold = r.get('hold_accum_seconds', 0)
                    agent = r.get('cc_agent', 'Unknown')[:30]
                    billsec = r.get('billsec', 0)
                    
                    print(f"  Agent: {agent}")
                    print(f"    Hold: {hold}s | Talk: {billsec}s | UUID: {r.get('xml_cdr_uuid', '')[:30]}")
                    
                    if hold not in hold_distribution:
                        hold_distribution[hold] = 0
                    hold_distribution[hold] += 1
                
                print("\n" + "=" * 60)
                print("Hold time distribution for all agent records:")
                print("=" * 60)
                for r in agent_records:
                    hold = r.get('hold_accum_seconds', 0)
                    if hold not in hold_distribution:
                        hold_distribution[hold] = 0
                    hold_distribution[hold] += 1
                
                for hold_val, count in sorted(hold_distribution.items()):
                    pct = (count / len(agent_records)) * 100
                    print(f"  {hold_val}s: {count} records ({pct:.1f}%)")
                    
        else:
            print("No records returned from FusionPBX")
    
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())

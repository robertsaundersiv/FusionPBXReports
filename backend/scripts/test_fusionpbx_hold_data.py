"""Test what fields FusionPBX provides in CDR data"""
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
        print("Fetching sample CDR records from FusionPBX")
        print("=" * 60)
        
        records = await client.get_xml_cdr(
            start_date=start_date,
            end_date=end_date,
            limit=1,
            offset=0
        )
        
        if records:
            record = records[0]
            print(f"\nGot {len(records)} record(s)")
            print(f"\nKeys in CDR record from FusionPBX:")
            
            # Look for hold-related keys
            hold_keys = [k for k in record.keys() if 'hold' in k.lower() or 'accum' in k.lower()]
            if hold_keys:
                print("\nHold/Accum related keys:")
                for k in sorted(hold_keys):
                    print(f"  {k}: {record[k]}")
            else:
                print("\n⚠ No hold-related keys found in FusionPBX data")
            
            # Show all keys
            print(f"\nAll keys ({len(record)} total):")
            for k in sorted(record.keys()):
                value = record[k]
                # Truncate long values
                value_str = str(value)[:50] if len(str(value)) > 50 else str(value)
                print(f"  {k}: {value_str}")
                
        else:
            print("No records returned from FusionPBX")
    
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())

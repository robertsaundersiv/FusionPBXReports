"""Check queue fields from FusionPBX"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.clients.fusionpbx import get_fusion_client
import json

async def main():
    client =get_fusion_client()
    await client.initialize()
    
    try:
        queues = await client.get_call_center_queues()
        if queues:
            print("Sample queue data:")
            print(json.dumps(queues[0], indent=2))
        else:
            print("No queues found")    
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())

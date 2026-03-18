"""
Sync only queues and agents from FusionPBX
"""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.sync_fusionpbx_data import sync_queues, sync_agents
from app.database import Base, engine


async def main():
    """Sync metadata only"""
    # Ensure model tables exist before running metadata sync tasks.
    Base.metadata.create_all(bind=engine)

    await sync_queues()
    await sync_agents()


if __name__ == "__main__":
    asyncio.run(main())

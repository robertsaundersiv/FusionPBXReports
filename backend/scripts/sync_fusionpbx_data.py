"""
Sync data from FusionPBX to local database
"""
import sys
import os
import asyncio
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

from app.database import SessionLocal, engine, get_db_context, Base
from app.models import Queue, Agent, CDRRecord
from app.clients.fusionpbx import FusionPBXClient
from app.utils.logger import logger


async def sync_queues():
    """Sync queues from FusionPBX"""
    print("\n" + "=" * 60)
    print("Syncing Queues from FusionPBX")
    print("=" * 60)
    
    client = FusionPBXClient()
    await client.initialize()
    
    try:
        queues = await client.get_queues()
        print(f"Retrieved {len(queues)} queues from FusionPBX")
        
        if queues and len(queues) > 0:
            print(f"Sample queue data: {queues[0]}")
        
        total_inserted = 0
        total_updated = 0
        total_skipped = 0
        
        with get_db_context() as db:
            for queue_data in queues:
                try:
                    queue_uuid = queue_data.get('queue_uuid')
                    queue_name = queue_data.get('queue_name')
                    
                    if not queue_uuid or not queue_name:
                        print(f"Skipping queue (missing uuid or name): {queue_data}")
                        total_skipped += 1
                        continue
                    
                    # Check if queue exists by queue_id (UUID from FusionPBX)
                    existing = db.query(Queue).filter(
                        Queue.queue_id == queue_uuid
                    ).first()
                    
                    # Map FusionPBX fields to our Queue model
                    mapped_data = {
                        'queue_id': queue_uuid,
                        'name': queue_name,
                        'queue_extension': queue_data.get('queue_extension'),
                        'description': queue_data.get('queue_description'),
                        'enabled': queue_data.get('queue_enabled', True),
                        'last_synced': datetime.utcnow()
                    }
                    
                    if existing:
                        # Update existing
                        for key, value in mapped_data.items():
                            setattr(existing, key, value)
                        total_updated += 1
                    else:
                        # Create new
                        queue = Queue(**mapped_data)
                        db.add(queue)
                        total_inserted += 1
                    
                    # Commit per queue to avoid transaction abort cascades
                    db.commit()
                except Exception as e:
                    print(f"Error processing queue {queue_data.get('queue_name', 'unknown')}: {e}")
                    db.rollback()
                    total_skipped += 1
        
        print(f"✓ Synced {len(queues)} queues")
        print(f"  Inserted: {total_inserted}")
        print(f"  Updated: {total_updated}")
        print(f"  Skipped: {total_skipped}")
        
    finally:
        await client.close()


async def sync_agents():
    """Sync agents from FusionPBX"""
    print("\n" + "=" * 60)
    print("Syncing Agents from FusionPBX")
    print("=" * 60)
    
    client = FusionPBXClient()
    await client.initialize()
    
    try:
        agents = await client.get_agents()
        print(f"Retrieved {len(agents)} agents from FusionPBX")
        
        total_inserted = 0
        total_updated = 0
        
        with get_db_context() as db:
            for agent_data in agents:
                try:
                    agent_uuid = agent_data.get('agent_uuid')
                    agent_name = agent_data.get('agent_name')
                    
                    if not agent_uuid or not agent_name:
                        continue
                    
                    # Check if agent exists by agent_uuid
                    existing = db.query(Agent).filter(
                        Agent.agent_uuid == agent_uuid
                    ).first()
                    
                    # Map FusionPBX fields to our Agent model
                    mapped_data = {
                        'agent_uuid': agent_uuid,
                        'agent_name': agent_name,
                        'agent_contact': agent_data.get('agent_contact'),
                        'extension': agent_data.get('agent_extension'),
                        'enabled': agent_data.get('agent_enabled', True),
                        'last_synced': datetime.utcnow()
                    }
                    
                    if existing:
                        # Update existing
                        for key, value in mapped_data.items():
                            setattr(existing, key, value)
                        total_updated += 1
                    else:
                        # Create new
                        agent = Agent(**mapped_data)
                        db.add(agent)
                        total_inserted += 1
                    
                    # Commit per agent to avoid transaction abort cascades
                    db.commit()
                except Exception as e:
                    print(f"Error processing agent {agent_data.get('agent_name', 'unknown')}: {e}")
                    db.rollback()
                    continue
        
        print(f"✓ Synced {len(agents)} agents")
        print(f"  Inserted: {total_inserted}")
        print(f"  Updated: {total_updated}")
        
    finally:
        await client.close()


async def sync_cdr_records(days: int = 1825, batch_size: int = 10000):
    """Sync CDR records from FusionPBX"""
    print("\n" + "=" * 60)
    print("Syncing CDR Records (last {} days)".format(days))
    print("=" * 60)
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    print(f"Date range: {start_date.date()} to {end_date.date()}\n")
    
    client = FusionPBXClient()
    await client.initialize()
    
    try:
        offset = 0
        total_fetched = 0
        total_processed = 0
        total_updated = 0
        total_skipped = 0
        batch_count = 0
        
        while True:
            batch_count += 1
            # print(f"\nFetching batch {batch_count} at offset {offset}...")
            
            records = await client.get_xml_cdr(
                start_date=start_date,
                end_date=end_date,
                limit=batch_size,
                offset=offset
            )
            
            if not records:
                print("No more records to fetch")
                break
                
            # print(f"Retrieved {len(records)} CDR records in batch {batch_count}")
            total_fetched += len(records)
            
            # Save to database - create new session for each record
            for record_data in records:
                try:
                    xml_cdr_uuid = record_data.get('xml_cdr_uuid')
                    
                    if not xml_cdr_uuid:
                        logger.warning("Record missing xml_cdr_uuid, skipping")
                        total_skipped += 1
                        continue
                    
                    # Create a fresh session for each record
                    with get_db_context() as db:
                        # First, try to get existing record
                        try:
                            existing = db.query(CDRRecord).filter(
                                CDRRecord.xml_cdr_uuid == xml_cdr_uuid
                            ).first()
                        except Exception as query_error:
                            logger.warning(f"Cannot query by xml_cdr_uuid for record {xml_cdr_uuid}, checking if column exists")
                            existing = None
                        
                        if existing:
                            # Update existing record
                            logger.info(f"Updating existing record {xml_cdr_uuid}")
                            for key, value in record_data.items():
                                if hasattr(existing, key) and key != 'id':
                                    setattr(existing, key, value)
                            total_updated += 1
                        else:
                            # Create new record
                            cdr = CDRRecord(**record_data)
                            db.add(cdr)
                            total_processed += 1
                        
                        db.commit()
                    
                except Exception as e:
                    logger.error(f"Error processing record {record_data.get('xml_cdr_uuid')}: {type(e).__name__}: {str(e)[:200]}")
                    total_skipped += 1
                    continue
            
            # Check if we got fewer records than requested (indicates last batch)
            if len(records) < batch_size:
                print(f"Last batch retrieved ({len(records)} < {batch_size}), stopping pagination")
                break
                
            offset += batch_size
            # print(f"Progress: {total_fetched} records fetched so far...")
            
        print(f"\n" + "=" * 60)
        print(f"✓ Sync complete!")
        print(f"  Total batches: {batch_count}")
        print(f"  Total fetched: {total_fetched}")
        print(f"  Total inserted: {total_processed} records")
        print(f"  Total updated: {total_updated} records")
        print(f"  Total skipped: {total_skipped} records")
        print("=" * 60)
        
    finally:
        await client.close()


async def main():
    """Main sync function"""
    print("=" * 60)
    print("FusionPBX Data Sync")
    print("=" * 60)
    
    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)
    
    # Sync metadata first
    await sync_queues()
    await sync_agents()
    
    # Sync CDR records (last 1 year, all records via pagination)
    await sync_cdr_records(days=365, batch_size=10000)
    
    print("\n" + "=" * 60)
    print("Sync Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

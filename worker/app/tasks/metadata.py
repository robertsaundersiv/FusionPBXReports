"""
Metadata sync tasks (queues and agents)
"""
import logging
import asyncio
from datetime import datetime
from celery import shared_task

from app.celery_app import celery_app
from app.clients.fusionpbx import FusionPBXClient
from app.database import SessionLocal
from app.models import Queue, Agent

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.sync_metadata")
def sync_metadata():
    """
    Periodic task: Sync queues and agents from FusionPBX
    Updates queue and agent configurations
    Runs every 4 hours (less frequent than extensions/CDR)
    """
    logger.info("Starting metadata sync task")
    try:
        result = asyncio.run(_sync_metadata_from_api())
        logger.info(f"Metadata sync completed: {result}")
        return result
    except Exception as e:
        logger.error(f"Error in metadata sync: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


async def _sync_metadata_from_api() -> dict:
    """
    Sync queues and agents from FusionPBX API

    Returns:
        Dictionary with sync status and counts
    """
    stats = {
        'queues': {'created': 0, 'updated': 0, 'skipped': 0, 'total': 0},
        'agents': {'created': 0, 'updated': 0, 'skipped': 0, 'total': 0}
    }

    try:
        # Sync queues first
        queue_stats = await _sync_queues()
        stats['queues'] = queue_stats

        # Then sync agents
        agent_stats = await _sync_agents()
        stats['agents'] = agent_stats

        return {
            "status": "success",
            "stats": stats
        }

    except Exception as e:
        logger.error(f"Error syncing metadata: {e}")
        return {
            "status": "error",
            "message": str(e),
            "stats": stats
        }


async def _sync_queues() -> dict:
    """Sync queues from FusionPBX"""
    logger.info("Syncing queues from FusionPBX")

    client = FusionPBXClient()
    await client.initialize()

    stats = {'created': 0, 'updated': 0, 'skipped': 0, 'total': 0}

    try:
        queues = await client.get_call_center_queues()
        stats['total'] = len(queues)
        logger.info(f"Retrieved {len(queues)} queues from FusionPBX")

        db = SessionLocal()

        for queue in queues:
            try:
                # Transform API field names to match our model expectations
                queue_data = {
                    'queue_uuid': queue.get('call_center_queue_uuid'),
                    'queue_name': queue.get('queue_name'),
                    'queue_extension': queue.get('queue_extension'),
                    'queue_description': queue.get('queue_description'),
                    'queue_enabled': queue.get('queue_enabled', True),
                }
                
                queue_uuid = queue_data.get('queue_uuid')
                queue_name = queue_data.get('queue_name')
                
                if not queue_uuid or not queue_name:
                    logger.warning(f"Skipping queue (missing uuid or name): {queue_data}")
                    stats['skipped'] += 1
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
                    stats['updated'] += 1
                else:
                    # Create new
                    queue_obj = Queue(**mapped_data)
                    db.add(queue_obj)
                    stats['created'] += 1
                    
            except Exception as e:
                logger.error(f"Error processing queue {queue}: {e}")
                stats['skipped'] += 1

        db.commit()
        logger.info(f"Queue sync completed: {stats}")

    finally:
        await client.close()
        db.close()

    return stats


async def _sync_agents() -> dict:
    """Sync agents from FusionPBX"""
    logger.info("Syncing agents from FusionPBX")

    client = FusionPBXClient()
    await client.initialize()

    stats = {'created': 0, 'updated': 0, 'skipped': 0, 'total': 0}

    try:
        agents = await client.get_call_center_agents()
        stats['total'] = len(agents)
        logger.info(f"Retrieved {len(agents)} agents from FusionPBX")

        db = SessionLocal()

        for agent in agents:
            try:
                # Transform API field names to match our model expectations
                agent_data = {
                    'agent_uuid': agent.get('call_center_agent_uuid'),
                    'agent_name': agent.get('agent_name'),
                    'agent_extension': agent.get('agent_id'),  # agent_id is the extension
                    'agent_contact': agent.get('agent_contact'),
                    'agent_enabled': agent.get('agent_enabled', True),
                }
                
                agent_uuid = agent_data.get('agent_uuid')
                agent_name = agent_data.get('agent_name')
                
                if not agent_uuid or not agent_name:
                    stats['skipped'] += 1
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
                    stats['updated'] += 1
                else:
                    # Create new
                    agent_obj = Agent(**mapped_data)
                    db.add(agent_obj)
                    stats['created'] += 1
                    
            except Exception as e:
                logger.error(f"Error processing agent {agent}: {e}")
                stats['skipped'] += 1

        db.commit()
        logger.info(f"Agent sync completed: {stats}")

    finally:
        await client.close()
        db.close()

    return stats
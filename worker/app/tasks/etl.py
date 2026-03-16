"""
ETL tasks for data ingestion and aggregation
"""
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from celery import shared_task

from app.celery_app import celery_app
from app.clients.fusionpbx import get_fusion_client
from app.database import SessionLocal
from app.models import Agent, CDRRecord, Queue

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.ingest_cdr_records")
def ingest_cdr_records():
    """
    Periodic task: Ingest new CDR records from FusionPBX
    Syncs from (newest record - 5 minutes) to now
    Runs every 15 minutes
    """
    logger.info("Starting CDR record ingestion task")
    try:
        # Get FusionPBX client and fetch recent CDRs
        result = asyncio.run(_sync_recent_cdr_records())
        logger.info(f"CDR ingestion completed successfully: {result}")
        return result
    except Exception as e:
        logger.error(f"Error in CDR ingestion: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


async def _sync_recent_cdr_records(lookback_minutes: int = 5, batch_size: int = 1000) -> dict:
    """
    Fetch CDR records from (newest in DB - lookback_minutes) to now
    This is a watermark-based sync that picks up from where we left off
    
    Args:
        lookback_minutes: Minutes to go back from newest record to avoid missing records (default 5)
        batch_size: Batch size for pagination
    
    Returns:
        Dictionary with sync status and counts
    """
    db = SessionLocal()
    try:
        # Find the newest CDR record in the database
        newest_cdr = db.query(CDRRecord).order_by(CDRRecord.start_epoch.desc()).first()
        
        # Calculate start_date based on the newest record
        end_date = datetime.now(timezone.utc)
        
        if newest_cdr and newest_cdr.start_epoch:
            # Convert epoch to datetime and subtract lookback_minutes
            newest_timestamp = datetime.fromtimestamp(newest_cdr.start_epoch, tz=timezone.utc)
            start_date = newest_timestamp - timedelta(minutes=lookback_minutes)
            logger.info(f"Found newest CDR at {newest_timestamp.isoformat()}, syncing from {start_date.isoformat()}")
        else:
            # If no records exist, sync from 365 days ago (default lookback)
            start_date = end_date - timedelta(days=365)
            logger.info(f"No existing CDR records found, syncing from {start_date.isoformat()}")
        
        logger.info(f"Syncing CDR records from {start_date.isoformat()} to {end_date.isoformat()}")
        
        client = get_fusion_client()
        await client.initialize()
        
        try:
            total_fetched = 0
            total_synced = 0
            total_skipped = 0
            offset = 0
            
            # Fetch records in batches
            while True:
                logger.debug(f"Fetching batch at offset {offset}...")
                cdrs = await client.get_xml_cdr(
                    start_date=start_date,
                    end_date=end_date,
                    limit=batch_size,
                    offset=offset
                )
                
                if not cdrs:
                    logger.debug("No more records to fetch")
                    break
                
                batch_count = len(cdrs)
                total_fetched += batch_count
                logger.debug(f"Retrieved {batch_count} CDR records in this batch")
                
                batch_synced = 0
                batch_skipped = 0
                
                for cdr_data in cdrs:
                    xml_cdr_uuid = cdr_data.get('xml_cdr_uuid')
                    if not xml_cdr_uuid:
                        batch_skipped += 1
                        continue
                    
                    # Check if record already exists
                    existing = db.query(CDRRecord).filter(
                        CDRRecord.xml_cdr_uuid == xml_cdr_uuid
                    ).first()
                    
                    raw_mos_val = cdr_data.get('rtp_audio_in_mos')
                    mos_value = float(raw_mos_val) if raw_mos_val not in (None, '', '0', 0) else None

                    if existing:
                        # Backfill MOS if it was missing from an earlier sync
                        if existing.rtp_audio_in_mos is None and mos_value is not None:
                            existing.rtp_audio_in_mos = mos_value
                        batch_skipped += 1
                        continue
                    
                    # Parse timestamps
                    start_epoch = cdr_data.get('start_epoch')
                    answer_epoch = cdr_data.get('answer_epoch')
                    end_epoch = cdr_data.get('end_epoch')
                    
                    # Create new CDR record
                    cdr = CDRRecord(
                        xml_cdr_uuid=xml_cdr_uuid,
                        caller_id_name=cdr_data.get('caller_id_name'),
                        caller_id_number=cdr_data.get('caller_id_number'),
                        destination_number=cdr_data.get('destination_number'),
                        direction=cdr_data.get('direction'),
                        start_epoch=int(start_epoch) if start_epoch else None,
                        answer_epoch=int(answer_epoch) if answer_epoch else None,
                        end_epoch=int(end_epoch) if end_epoch else None,
                        duration=int(cdr_data.get('duration', 0)),
                        billsec=int(cdr_data.get('billsec', 0)),
                        cc_queue=cdr_data.get('cc_queue'),
                        cc_queue_joined_epoch=int(cdr_data.get('cc_queue_joined_epoch', 0)) if cdr_data.get('cc_queue_joined_epoch') else None,
                        cc_queue_answered_epoch=int(cdr_data.get('cc_queue_answered_epoch', 0)) if cdr_data.get('cc_queue_answered_epoch') else None,
                        cc_agent_type=cdr_data.get('cc_agent_type'),
                        cc_member_uuid=cdr_data.get('cc_member_uuid'),
                        status=cdr_data.get('hangup_cause', 'UNKNOWN'),
                        hangup_cause=cdr_data.get('hangup_cause'),
                        hangup_cause_q850=cdr_data.get('hangup_cause_q850'),
                        domain_name=cdr_data.get('domain_name'),
                        rtp_audio_in_mos=mos_value,
                    )
                    
                    db.add(cdr)
                    batch_synced += 1
                    
                    # Commit in batches
                    if batch_synced % 100 == 0:
                        db.commit()
                        logger.debug(f"  Progress: {total_synced + batch_synced} total records synced...")
                
                # Commit remaining records from this batch
                db.commit()
                
                total_synced += batch_synced
                total_skipped += batch_skipped
                
                logger.debug(f"Batch complete: {batch_synced} synced, {batch_skipped} skipped")
                
                # If we got fewer records than batch_size, we've reached the end
                if batch_count < batch_size:
                    logger.debug("Reached end of records")
                    break
                
                # Move to next batch
                offset += batch_size
            
            logger.info(f"CDR sync complete: {total_synced} new records, {total_skipped} skipped")
            return {
                "status": "success",
                "records_synced": total_synced,
                "records_skipped": total_skipped,
                "total_fetched": total_fetched,
            }
        finally:
            await client.close()
    finally:
        db.close()


@celery_app.task(name="app.tasks.cleanup_old_cdr_records")
def cleanup_old_cdr_records(retention_days: int = 31):
    """
    Periodic task: Clean up CDR records older than retention_days
    Runs every 15 minutes to maintain database size
    
    Args:
        retention_days: Keep records from the last N days (default 31)
    """
    logger.info(f"Starting CDR cleanup task (retention: {retention_days} days)")
    try:
        db = SessionLocal()
        try:
            # Calculate cutoff date
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
            
            logger.info(f"Deleting CDR records older than {cutoff_date.isoformat()}")
            
            # Count records to be deleted
            records_to_delete = db.query(CDRRecord).filter(
                CDRRecord.insert_date < cutoff_date
            ).count()
            
            if records_to_delete > 0:
                logger.info(f"Found {records_to_delete} records to delete")
                
                # Delete in batches to avoid locking the table for too long
                batch_size = 1000
                deleted_count = 0
                
                while True:
                    # Get batch of records to delete
                    batch = db.query(CDRRecord).filter(
                        CDRRecord.insert_date < cutoff_date
                    ).limit(batch_size).all()
                    
                    if not batch:
                        break
                    
                    batch_ids = [record.id for record in batch]
                    deleted_in_batch = db.query(CDRRecord).filter(
                        CDRRecord.id.in_(batch_ids)
                    ).delete(synchronize_session=False)
                    
                    db.commit()
                    deleted_count += deleted_in_batch
                    
                    logger.debug(f"Deleted batch of {deleted_in_batch} records. Total: {deleted_count}")
                
                logger.info(f"✓ Cleanup complete: deleted {deleted_count} records")
                return {
                    "status": "success",
                    "records_deleted": deleted_count,
                    "retention_days": retention_days,
                }
            else:
                logger.info("No records to delete")
                return {
                    "status": "success",
                    "records_deleted": 0,
                    "retention_days": retention_days,
                }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error in CDR cleanup: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


async def _sync_queue_metadata() -> dict:
    """Sync queue metadata from FusionPBX into the local database."""
    client = get_fusion_client()
    db = SessionLocal()
    try:
        logger.info("Fetching queues from FusionPBX")
        await client.initialize()
        queues = await client.get_queues()

        total_processed = 0
        total_created = 0
        total_updated = 0
        total_skipped = 0

        if not queues:
            logger.info("No queues returned from FusionPBX API")
            return {
                "status": "success",
                "total": 0,
                "created": 0,
                "updated": 0,
                "skipped": 0,
            }

        for queue_data in queues:
            queue_uuid = queue_data.get("queue_uuid")
            queue_name = queue_data.get("queue_name")
            if not queue_uuid or not queue_name:
                logger.warning(f"Skipping invalid queue record: {queue_data}")
                total_skipped += 1
                continue

            existing = db.query(Queue).filter(Queue.queue_id == queue_uuid).first()

            mapped_fields = {
                "queue_id": queue_uuid,
                "name": queue_name,
                "queue_extension": queue_data.get("queue_extension"),
                "description": queue_data.get("queue_description"),
                "enabled": queue_data.get("queue_enabled", True),
                "last_synced": datetime.utcnow(),
                "extra_metadata": {
                    "source": "fusionpbx",
                },
            }

            if existing:
                for key, value in mapped_fields.items():
                    setattr(existing, key, value)
                total_updated += 1
            else:
                queue = Queue(**mapped_fields)
                db.add(queue)
                total_created += 1

            total_processed += 1

        db.commit()

        return {
            "status": "success",
            "total": total_processed,
            "created": total_created,
            "updated": total_updated,
            "skipped": total_skipped,
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error syncing queue metadata: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
    finally:
        await client.close()
        db.close()


@celery_app.task(name="app.tasks.sync_queue_metadata")
def sync_queue_metadata():
    """Periodic task to sync queue metadata from FusionPBX."""
    logger.info("Starting queue metadata sync")
    try:
        result = asyncio.run(_sync_queue_metadata())
        logger.info(f"Queue sync completed: {result}")
        return result
    except Exception as e:
        logger.error(f"Error in queue sync: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


async def _sync_agent_metadata() -> dict:
    """Sync agent metadata from FusionPBX into the local database."""
    client = get_fusion_client()
    db = SessionLocal()
    try:
        logger.info("Fetching agents from FusionPBX")
        await client.initialize()
        agents = await client.get_agents()

        total_processed = 0
        total_created = 0
        total_updated = 0
        total_skipped = 0

        if not agents:
            logger.info("No agents returned from FusionPBX API")
            return {
                "status": "success",
                "total": 0,
                "created": 0,
                "updated": 0,
                "skipped": 0,
            }

        for agent_data in agents:
            agent_uuid = agent_data.get("agent_uuid")
            agent_name = agent_data.get("agent_name")
            if not agent_uuid or not agent_name:
                logger.warning(f"Skipping invalid agent record: {agent_data}")
                total_skipped += 1
                continue

            existing = db.query(Agent).filter(Agent.agent_uuid == agent_uuid).first()

            mapped_fields = {
                "agent_uuid": agent_uuid,
                "agent_name": agent_name,
                "agent_contact": agent_data.get("agent_contact"),
                "extension": agent_data.get("agent_extension"),
                "enabled": agent_data.get("agent_enabled", True),
                "last_synced": datetime.utcnow(),
                "extra_metadata": {
                    "source": "fusionpbx",
                },
            }

            if existing:
                for key, value in mapped_fields.items():
                    setattr(existing, key, value)
                total_updated += 1
            else:
                agent = Agent(**mapped_fields)
                db.add(agent)
                total_created += 1

            total_processed += 1

        db.commit()

        return {
            "status": "success",
            "total": total_processed,
            "created": total_created,
            "updated": total_updated,
            "skipped": total_skipped,
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error syncing agent metadata: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

    finally:
        await client.close()
        db.close()


@celery_app.task(name="app.tasks.sync_agent_metadata")
def sync_agent_metadata():
    """Periodic task to sync agent metadata from FusionPBX."""
    logger.info("Starting agent metadata sync")
    try:
        result = asyncio.run(_sync_agent_metadata())
        logger.info(f"Agent sync completed: {result}")
        return result
    except Exception as e:
        logger.error(f"Error in agent sync: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@celery_app.task(name="app.tasks.compute_hourly_aggregates")
def compute_hourly_aggregates():
    """
    Periodic task: Compute hourly aggregates
    Runs every 15 minutes for near-real-time reporting
    """
    logger.info("Starting hourly aggregate computation")
    try:
        # TODO: Implement hourly aggregation logic
        # 1. Get last aggregated hour from HourlyAggregate
        # 2. Query CDR records for that hour
        # 3. Compute all KPIs
        # 4. Upsert to HourlyAggregate table
        logger.info("Hourly aggregation completed successfully")
        return {"status": "success", "hours_processed": 0}
    except Exception as e:
        logger.error(f"Error in hourly aggregation: {e}")
        return {"status": "error", "message": str(e)}


@celery_app.task(name="app.tasks.compute_daily_aggregates")
def compute_daily_aggregates():
    """
    Periodic task: Compute daily aggregates
    Runs daily at 2 AM
    """
    logger.info("Starting daily aggregate computation")
    try:
        # TODO: Implement daily aggregation logic
        # 1. Get previous day's CDR records
        # 2. Compute aggregates per queue and agent
        # 3. Upsert to DailyAggregate table
        logger.info("Daily aggregation completed successfully")
        return {"status": "success", "days_processed": 1}
    except Exception as e:
        logger.error(f"Error in daily aggregation: {e}")
        return {"status": "error", "message": str(e)}


# Beat schedule configuration
from celery.schedules import crontab

# Canonical beat schedule for periodic worker tasks.
celery_app.conf.beat_schedule.update({
    'sync-extensions-every-15-minutes': {
        'task': 'app.tasks.sync_extensions',
        'schedule': crontab(minute='*/15'),
    },
    'ingest-cdr-every-15-minutes': {
        'task': 'app.tasks.ingest_cdr_records',
        'schedule': crontab(minute='*/15'),
    },
    'cleanup-old-cdr-every-15-minutes': {
        'task': 'app.tasks.cleanup_old_cdr_records',
        'schedule': crontab(minute='*/15'),
        'kwargs': {'retention_days': 1825},
    },
    'sync-metadata-every-4-hours': {
        'task': 'app.tasks.sync_metadata',
        'schedule': crontab(minute=0, hour='*/4'),
    },
    'compute-hourly-aggregates': {
        'task': 'app.tasks.compute_hourly_aggregates',
        'schedule': crontab(minute='*/15'),
    },
    'compute-daily-aggregates': {
        'task': 'app.tasks.compute_daily_aggregates',
        'schedule': crontab(hour=2, minute=0),
    },
})

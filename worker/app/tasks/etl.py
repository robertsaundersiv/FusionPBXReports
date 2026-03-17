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
                        # Backfill fields that were missing from earlier syncs
                        if existing.rtp_audio_in_mos is None and mos_value is not None:
                            existing.rtp_audio_in_mos = mos_value
                        if existing.extension_uuid is None and cdr_data.get('extension_uuid'):
                            existing.extension_uuid = cdr_data.get('extension_uuid')
                        if existing.cc_agent_uuid is None and cdr_data.get('cc_agent_uuid'):
                            existing.cc_agent_uuid = cdr_data.get('cc_agent_uuid')
                        if existing.cc_agent is None and cdr_data.get('cc_agent'):
                            existing.cc_agent = cdr_data.get('cc_agent')
                        if existing.originating_leg_uuid is None and cdr_data.get('originating_leg_uuid'):
                            existing.originating_leg_uuid = cdr_data.get('originating_leg_uuid')
                        if existing.accountcode is None and cdr_data.get('accountcode'):
                            existing.accountcode = cdr_data.get('accountcode')
                        if existing.bridge_uuid is None and cdr_data.get('bridge_uuid'):
                            existing.bridge_uuid = cdr_data.get('bridge_uuid')
                        if existing.leg is None and cdr_data.get('leg'):
                            existing.leg = cdr_data.get('leg')
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
                        extension_uuid=cdr_data.get('extension_uuid'),
                        accountcode=cdr_data.get('accountcode'),
                        bridge_uuid=cdr_data.get('bridge_uuid'),
                        leg=cdr_data.get('leg'),
                        originating_leg_uuid=cdr_data.get('originating_leg_uuid'),
                        cc_queue=cdr_data.get('cc_queue'),
                        cc_queue_joined_epoch=int(cdr_data.get('cc_queue_joined_epoch', 0)) if cdr_data.get('cc_queue_joined_epoch') else None,
                        cc_queue_answered_epoch=int(cdr_data.get('cc_queue_answered_epoch', 0)) if cdr_data.get('cc_queue_answered_epoch') else None,
                        cc_agent_uuid=cdr_data.get('cc_agent_uuid'),
                        cc_agent=cdr_data.get('cc_agent'),
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

                # Resolve outbound attribution: for B-leg records that have
                # originating_leg_uuid but no extension_uuid, look up the
                # A-leg and copy its extension_uuid so agent reports are accurate.
                _resolve_outbound_attribution(db)

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


def _resolve_outbound_attribution(db) -> int:
    """
    For outbound B-leg records that have originating_leg_uuid but no
    extension_uuid, look up the matching A-leg and copy its extension_uuid.

    In FusionPBX, when an agent places a direct outbound call the PBX writes:
      - A-leg (local): direction=local, extension_uuid=<agent ext UUID>
      - B-leg (outbound trunk): direction=outbound, no extension_uuid,
        originating_leg_uuid = A-leg xml_cdr_uuid

    Without this resolution the B-leg always shows as "Unknown" in reports.
    Returns the number of records updated.
    """
    # Find outbound B-legs that are missing extension_uuid but have
    # originating_leg_uuid populated.
    b_legs = (
        db.query(CDRRecord)
        .filter(
            CDRRecord.direction == "outbound",
            CDRRecord.extension_uuid.is_(None),
            CDRRecord.originating_leg_uuid.isnot(None),
        )
        .all()
    )

    if not b_legs:
        return 0

    # Build a set of originating UUIDs to fetch in one query.
    orig_uuids = {r.originating_leg_uuid for r in b_legs}
    a_legs = (
        db.query(CDRRecord)
        .filter(CDRRecord.xml_cdr_uuid.in_(orig_uuids))
        .all()
    )
    a_leg_map = {r.xml_cdr_uuid: r for r in a_legs}

    updated = 0
    for b in b_legs:
        a = a_leg_map.get(b.originating_leg_uuid)
        if a and a.extension_uuid:
            b.extension_uuid = a.extension_uuid
            updated += 1

    if updated:
        db.commit()
        logger.info(
            f"Resolved outbound attribution: {updated} B-leg record(s) "
            "backfilled with extension_uuid from A-leg"
        )

    return updated


@celery_app.task(name="app.tasks.fetch_missing_a_legs")
def fetch_missing_a_legs():
    """
    One-off task: for outbound B-leg records that are missing extension_uuid,
    re-fetch them individually from the FusionPBX single-record API (/xml_cdr/{uuid})
    which returns extension_uuid even though the bulk date-range API omits it.

    Trigger:
        docker exec <worker> celery -A app.celery_app call app.tasks.fetch_missing_a_legs
    """
    logger.info("Starting missing extension_uuid fetch task (per-UUID API)")
    try:
        result = asyncio.run(_fetch_missing_a_legs_async())
        logger.info(f"Per-UUID fetch complete: {result}")
        return result
    except Exception as e:
        logger.error(f"Per-UUID fetch failed: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


async def _fetch_missing_a_legs_async() -> dict:
    """
    For every outbound record missing extension_uuid, call the per-UUID
    FusionPBX endpoint to retrieve the full record and patch extension_uuid.
    The bulk date-range API omits extension_uuid for outbound legs; the
    single-record endpoint returns it correctly.
    """
    db = SessionLocal()
    try:
        unresolved = (
            db.query(CDRRecord)
            .filter(
                CDRRecord.direction == "outbound",
                CDRRecord.extension_uuid.is_(None),
            )
            .all()
        )

        if not unresolved:
            logger.info("No outbound records missing extension_uuid — nothing to do")
            return {"status": "success", "fetched": 0, "updated": 0, "not_found": 0}

        logger.info(f"Fetching {len(unresolved)} outbound records individually by UUID")

        client = get_fusion_client()
        await client.initialize()

        updated = 0
        not_found = 0

        try:
            for i, record in enumerate(unresolved):
                cdr_data = await client.get_xml_cdr_by_uuid(record.xml_cdr_uuid)
                if not cdr_data:
                    not_found += 1
                    continue

                ext_uuid = cdr_data.get("extension_uuid")
                if ext_uuid:
                    record.extension_uuid = ext_uuid
                    updated += 1

                # Also backfill other fields the bulk API may have omitted
                if record.accountcode is None and cdr_data.get("accountcode"):
                    record.accountcode = cdr_data.get("accountcode")
                if record.bridge_uuid is None and cdr_data.get("bridge_uuid"):
                    record.bridge_uuid = cdr_data.get("bridge_uuid")
                if record.leg is None and cdr_data.get("leg"):
                    record.leg = cdr_data.get("leg")
                if record.originating_leg_uuid is None and cdr_data.get("originating_leg_uuid"):
                    record.originating_leg_uuid = cdr_data.get("originating_leg_uuid")

                if (i + 1) % 50 == 0:
                    db.commit()
                    logger.info(f"  Progress: {i + 1}/{len(unresolved)} — {updated} updated so far")

            db.commit()
        finally:
            await client.close()

        logger.info(f"Per-UUID fetch done: {updated} updated, {not_found} not found in FusionPBX")
        return {
            "status": "success",
            "fetched": len(unresolved),
            "updated": updated,
            "not_found": not_found,
        }
    finally:
        db.close()


@celery_app.task(name="app.tasks.backfill_outbound_attribution", bind=True)
def backfill_outbound_attribution(self):
    """
    One-off task: backfill originating_leg_uuid for historical outbound records
    that were synced before the fix was deployed, then resolve attribution.

    Finds the date range of affected records, iterates through the FusionPBX
    API in 1-day chunks, patches originating_leg_uuid on matching DB rows,
    and finally runs _resolve_outbound_attribution so extension_uuid is set.

    Trigger manually:
        docker exec <worker> celery -A app.celery_app call app.tasks.backfill_outbound_attribution
    """
    logger.info("Starting one-off outbound attribution backfill")
    try:
        result = asyncio.run(_backfill_outbound_attribution_async())
        logger.info(f"Backfill complete: {result}")
        return result
    except Exception as e:
        logger.error(f"Backfill failed: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


async def _backfill_outbound_attribution_async(chunk_days: int = 1, batch_size: int = 1000) -> dict:
    """
    Async implementation of the historical originating_leg_uuid backfill.
    """
    db = SessionLocal()
    try:
        from sqlalchemy import func as sa_func

        # Find the epoch range of records that are missing originating_leg_uuid
        row = (
            db.query(
                sa_func.min(CDRRecord.start_epoch),
                sa_func.max(CDRRecord.start_epoch),
            )
            .filter(
                CDRRecord.direction == "outbound",
                CDRRecord.originating_leg_uuid.is_(None),
                CDRRecord.start_epoch.isnot(None),
            )
            .one()
        )
        min_epoch, max_epoch = row

        if not min_epoch or not max_epoch:
            logger.info("No outbound records missing originating_leg_uuid — nothing to do")
            return {"status": "success", "chunks_processed": 0, "records_updated": 0, "resolved": 0}

        range_start = datetime.fromtimestamp(min_epoch, tz=timezone.utc)
        range_end = datetime.fromtimestamp(max_epoch, tz=timezone.utc) + timedelta(seconds=1)
        logger.info(f"Backfill range: {range_start.isoformat()} → {range_end.isoformat()}")

        client = get_fusion_client()
        await client.initialize()

        chunks_processed = 0
        records_updated = 0
        chunk_start = range_start

        try:
            while chunk_start < range_end:
                chunk_end = min(chunk_start + timedelta(days=chunk_days), range_end)
                offset = 0

                while True:
                    cdrs = await client.get_xml_cdr(
                        start_date=chunk_start,
                        end_date=chunk_end,
                        limit=batch_size,
                        offset=offset,
                    )
                    if not cdrs:
                        break

                    # Build a lookup of uuid → originating_leg_uuid for this batch
                    orig_map = {
                        c["xml_cdr_uuid"]: c.get("originating_leg_uuid")
                        for c in cdrs
                        if c.get("xml_cdr_uuid") and c.get("originating_leg_uuid")
                    }

                    if orig_map:
                        # Fetch matching DB rows in one query
                        rows = (
                            db.query(CDRRecord)
                            .filter(
                                CDRRecord.xml_cdr_uuid.in_(list(orig_map.keys())),
                                CDRRecord.originating_leg_uuid.is_(None),
                            )
                            .all()
                        )
                        for row in rows:
                            row.originating_leg_uuid = orig_map[row.xml_cdr_uuid]
                            records_updated += 1

                        if rows:
                            db.commit()

                    if len(cdrs) < batch_size:
                        break
                    offset += batch_size

                chunks_processed += 1
                logger.info(
                    f"Chunk {chunk_start.date()} done — "
                    f"{records_updated} total records updated so far"
                )
                chunk_start = chunk_end

        finally:
            await client.close()

        # Now resolve extension_uuid from A-leg for all newly populated rows
        resolved = _resolve_outbound_attribution(db)

        return {
            "status": "success",
            "chunks_processed": chunks_processed,
            "records_updated": records_updated,
            "resolved": resolved,
        }
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

"""
Extension sync tasks
"""
import logging
import asyncio
from datetime import datetime
from celery import shared_task

from app.celery_app import celery_app
from app.clients.fusionpbx import FusionPBXClient
from app.database import SessionLocal
from app.models import Extension

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.sync_extensions")
def sync_extensions():
    """
    Periodic task: Sync extensions from FusionPBX API
    Updates extension to user name mappings
    Runs every 15 minutes
    """
    logger.info("Starting extension sync task")
    try:
        result = asyncio.run(_sync_extensions_from_api())
        logger.info(f"Extension sync completed: {result}")
        return result
    except Exception as e:
        logger.error(f"Error in extension sync: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


async def _sync_extensions_from_api() -> dict:
    """
    Fetch extensions from FusionPBX API and update the database
    
    Returns:
        Dictionary with sync status and counts
    """
    db = SessionLocal()
    stats = {
        'created': 0,
        'updated': 0,
        'failed': 0,
        'total': 0,
    }
    
    try:
        # Create and initialize FusionPBX client
        client = FusionPBXClient()
        await client.initialize()
        
        try:
            extensions = await client.get_extensions()
            
            if not extensions:
                logger.warning("No extensions returned from FusionPBX API")
                return {**stats, 'status': 'success', 'message': 'No extensions to process'}
            
            stats['total'] = len(extensions)
            logger.info(f"Fetched {len(extensions)} extensions from FusionPBX API")
            
            # Process each extension
            for ext_data in extensions:
                try:
                    extension_uuid = ext_data.get('extension_uuid')
                    extension = ext_data.get('extension')
                    description = ext_data.get('description', '')
                    domain_uuid = ext_data.get('domain_uuid')
                    enabled = ext_data.get('enabled', True)
                    
                    # Skip if we don't have the minimum required fields
                    if not extension or not extension_uuid:
                        logger.debug(f"Skipping extension due to missing uuid or number")
                        stats['failed'] += 1
                        continue
                    
                    # Try to find existing extension by uuid OR by extension number (fallback)
                    existing = db.query(Extension).filter(
                        (Extension.extension_uuid == extension_uuid) |
                        (Extension.extension == extension)
                    ).first()
                    
                    if existing:
                        # Update existing record
                        existing.extension = extension
                        existing.extension_uuid = extension_uuid
                        existing.user_name = description or existing.user_name
                        existing.user_uuid = domain_uuid
                        existing.enabled = enabled if isinstance(enabled, bool) else enabled.lower() == 'true'
                        existing.extra_metadata = {
                            'directory_first_name': ext_data.get('directory_first_name'),
                            'directory_last_name': ext_data.get('directory_last_name'),
                            'effective_caller_id_name': ext_data.get('effective_caller_id_name'),
                            'effective_caller_id_number': ext_data.get('effective_caller_id_number'),
                        }
                        existing.last_synced = datetime.utcnow()
                        stats['updated'] += 1
                        logger.debug(f"Updated extension {extension}: {description}")
                    else:
                        # Create new record
                        new_ext = Extension(
                            extension_uuid=extension_uuid,
                            extension=extension,
                            user_name=description,
                            user_uuid=domain_uuid,
                            enabled=enabled if isinstance(enabled, bool) else enabled.lower() == 'true',
                            extra_metadata={
                                'directory_first_name': ext_data.get('directory_first_name'),
                                'directory_last_name': ext_data.get('directory_last_name'),
                                'effective_caller_id_name': ext_data.get('effective_caller_id_name'),
                                'effective_caller_id_number': ext_data.get('effective_caller_id_number'),
                            },
                            last_synced=datetime.utcnow()
                        )
                        db.add(new_ext)
                        stats['created'] += 1
                        logger.debug(f"Created extension {extension}: {description}")
                        
                except Exception as e:
                    logger.error(f"Error processing extension {ext_data.get('extension', 'unknown')}: {e}")
                    stats['failed'] += 1
                    db.rollback()
                    continue
            
            # Commit all changes
            db.commit()
            logger.info(f"Extension sync completed - Created: {stats['created']}, Updated: {stats['updated']}, Failed: {stats['failed']}")
            
            return {**stats, 'status': 'success'}
            
        finally:
            await client.close()
            
    except Exception as e:
        logger.error(f"Error during extension sync: {e}", exc_info=True)
        db.rollback()
        return {'status': 'error', 'message': str(e), **stats}
    finally:
        db.close()

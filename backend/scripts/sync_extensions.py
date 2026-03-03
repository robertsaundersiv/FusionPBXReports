#!/usr/bin/env python3
"""
Sync extensions from FusionPBX API to the database
Fetches extension data including user mappings
"""
import os
import sys
import asyncio
import json
from datetime import datetime

# Add backend app directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.database import SessionLocal
from app.models import Extension
from app.clients.fusionpbx import FusionPBXClient


async def fetch_extensions_from_api() -> list:
    """Fetch extensions from FusionPBX API"""
    client = FusionPBXClient()
    
    print(f"Initializing FusionPBX client...")
    await client.initialize()
    
    print(f"Fetching extensions from {client.host}/app/api/7/extensions...")
    try:
        extensions = await client.get_extensions()
        print(f"Successfully fetched {len(extensions)} extensions from API")
        return extensions
    finally:
        await client.close()


def sync_extensions_to_db(extensions: list) -> dict:
    """
    Sync fetched extensions to the database
    
    Returns statistics about the sync operation
    """
    db = SessionLocal()
    stats = {
        'created': 0,
        'updated': 0,
        'failed': 0,
        'total': len(extensions)
    }
    
    try:
        for ext_data in extensions:
            try:
                # Extract required fields from the API response
                extension_uuid = ext_data.get('extension_uuid')
                extension = ext_data.get('extension')
                description = ext_data.get('description', '')
                domain_uuid = ext_data.get('domain_uuid')
                enabled = ext_data.get('enabled', True)
                
                # Skip if we don't have the minimum required fields
                if not extension_uuid or not extension:
                    print(f"Skipping extension due to missing uuid or number")
                    stats['failed'] += 1
                    continue
                
                # Try to find existing extension by uuid
                existing = db.query(Extension).filter(
                    Extension.extension_uuid == extension_uuid
                ).first()
                
                if existing:
                    # Update existing record
                    existing.extension = extension
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
                    print(f"Updated extension {extension} ({extension_uuid}): {description}")
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
                    print(f"Created extension {extension} ({extension_uuid}): {description}")
                    
            except Exception as e:
                print(f"Error processing extension: {e}")
                stats['failed'] += 1
                continue
        
        # Commit all changes
        db.commit()
        print(f"\nSync completed successfully!")
        print(f"  Created: {stats['created']}")
        print(f"  Updated: {stats['updated']}")
        print(f"  Failed: {stats['failed']}")
        print(f"  Total processed: {stats['total']}")
        
    except Exception as e:
        print(f"Error during database sync: {e}")
        db.rollback()
        raise
    finally:
        db.close()
    
    return stats


async def main():
    """Main entry point"""
    try:
        # Fetch extensions from API
        extensions = await fetch_extensions_from_api()
        
        if not extensions:
            print("No extensions fetched from API")
            return 1
        
        # Sync to database
        stats = sync_extensions_to_db(extensions)
        
        if stats['failed'] > 0 and stats['created'] == 0 and stats['updated'] == 0:
            print("All records failed to process")
            return 1
        
        return 0
        
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

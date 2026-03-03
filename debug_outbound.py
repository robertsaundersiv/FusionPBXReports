from app.database import SessionLocal
from app.models import Extension, CDRRecord

db = SessionLocal()

# Check extensions
exts = db.query(Extension).limit(5).all()
ext_count = db.query(Extension).count()
print(f'Total Extensions: {ext_count}')
for ext in exts:
    print(f'  UUID: {ext.extension_uuid}, Extension: {ext.extension}, User: {ext.user_name}')

# Check outbound CDR records
outbound = db.query(CDRRecord).filter(CDRRecord.direction == 'outbound').limit(5).all()
outbound_count = db.query(CDRRecord).filter(CDRRecord.direction == 'outbound').count()
print(f'\nTotal Outbound records: {outbound_count}')
for rec in outbound:
    print(f'  extension_uuid: {rec.extension_uuid}, dest: {rec.destination_number}')

db.close()

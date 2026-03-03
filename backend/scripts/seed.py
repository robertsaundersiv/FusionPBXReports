"""
Seed script - initialize database with test data and admin user
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal, engine
from app.models import User
from app.auth import hash_password

def seed_database():
    """Initialize database with seed data"""
    # Ensure users table exists without forcing full metadata/table creation.
    # This avoids failures when legacy queue/agent schemas differ.
    User.__table__.create(bind=engine, checkfirst=True)
    
    db = SessionLocal()
    
    try:
        # Check if already seeded
        existing_user = db.query(User).filter(User.username == os.getenv("ADMIN_USERNAME", "admin")).first()
        if existing_user:
            print("✓ Database already seeded - skipping")
            return
        
        # Create admin user
        # Truncate password to 72 bytes for bcrypt compatibility
        admin_password = os.getenv("ADMIN_PASSWORD")
        if not admin_password:
            raise ValueError("ADMIN_PASSWORD environment variable must be set")
        if len(admin_password.encode('utf-8')) > 72:
            admin_password = admin_password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
        
        admin = User(
            username=os.getenv("ADMIN_USERNAME", "admin"),
            email=os.getenv("ADMIN_EMAIL", "admin@example.com"),
            hashed_password=hash_password(admin_password),
            role="admin",
            can_view_unmasked_numbers=True,
        )
        db.add(admin)
        
        db.commit()
        print("✓ Database seeded successfully")
        print(f"✓ Admin user created: {admin.username}")
        print("  Note: Run sync_fusionpbx_data.py to populate queues and agents from FusionPBX")
        
    except Exception as e:
        db.rollback()
        print(f"✗ Error seeding database: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()

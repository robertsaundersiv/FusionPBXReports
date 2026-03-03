"""
Seed script - initialize database with test data and admin user
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal, engine
from app.models import User
from app.auth import hash_password


def _bcrypt_safe_password(password: str) -> str:
    if len(password.encode('utf-8')) > 72:
        return password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
    return password


def _upsert_user(db, username: str, email: str, password: str, role: str = "user", can_view_unmasked_numbers: bool = False):
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        return False

    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(_bcrypt_safe_password(password)),
        role=role,
        enabled=True,
        can_view_unmasked_numbers=can_view_unmasked_numbers,
    )
    db.add(user)
    return True


def _parse_extra_seed_users(raw_value: str):
    """
    Parse EXTRA_SEED_USERS env var in format:
    username:password[:role[:email]];username2:password2[:role[:email]]
    """
    users = []
    if not raw_value:
        return users

    entries = [entry.strip() for entry in raw_value.split(';') if entry.strip()]
    for entry in entries:
        parts = [part.strip() for part in entry.split(':')]
        if len(parts) < 2:
            continue

        username = parts[0]
        password = parts[1]
        role = parts[2] if len(parts) >= 3 and parts[2] else "user"
        email = parts[3] if len(parts) >= 4 and parts[3] else f"{username.lower()}@local"

        users.append({
            "username": username,
            "password": password,
            "role": role,
            "email": email,
        })
    return users

def seed_database():
    """Initialize database with seed data"""
    # Ensure users table exists without forcing full metadata/table creation.
    # This avoids failures when legacy queue/agent schemas differ.
    User.__table__.create(bind=engine, checkfirst=True)
    
    db = SessionLocal()
    
    try:
        created_users = []

        # Create admin user if missing
        admin_password = os.getenv("ADMIN_PASSWORD")
        if not admin_password:
            raise ValueError("ADMIN_PASSWORD environment variable must be set")
        admin_username = os.getenv("ADMIN_USERNAME", "admin")
        admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")

        if _upsert_user(
            db,
            username=admin_username,
            email=admin_email,
            password=admin_password,
            role="admin",
            can_view_unmasked_numbers=True,
        ):
            created_users.append(admin_username)

        # Create any additional configured users
        extra_users = _parse_extra_seed_users(os.getenv("EXTRA_SEED_USERS", ""))
        for extra_user in extra_users:
            if _upsert_user(
                db,
                username=extra_user["username"],
                email=extra_user["email"],
                password=extra_user["password"],
                role=extra_user["role"],
                can_view_unmasked_numbers=False,
            ):
                created_users.append(extra_user["username"])

        db.commit()

        if created_users:
            print("✓ Database seeded successfully")
            print(f"✓ Users created: {', '.join(created_users)}")
        else:
            print("✓ Database already seeded - no new users created")

        print(
            "  Note: EXTRA_SEED_USERS format is "
            "username:password[:role[:email]];username2:password2[:role[:email]]"
        )
        print("  Note: Run sync_fusionpbx_data.py to populate queues and agents from FusionPBX")
        
    except Exception as e:
        db.rollback()
        print(f"✗ Error seeding database: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()

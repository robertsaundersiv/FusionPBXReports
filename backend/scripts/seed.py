"""
Seed script - initialize database with test data and admin user
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import inspect, text
from sqlalchemy.exc import ProgrammingError
from app.database import SessionLocal, engine
from app.models import User
from app.auth import hash_password


def ensure_user_columns():
    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        return
    cols = [col["name"] for col in insp.get_columns("users")]
    if "branch_id" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN branch_id INTEGER"))

    # create branches table if missing
    if "branches" not in insp.get_table_names():
        with engine.begin() as conn:
            conn.execute(text(
                """
                CREATE TABLE IF NOT EXISTS branches (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(256) NOT NULL UNIQUE,
                    description TEXT,
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now(),
                    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now()
                )
                """
            ))

    # add agent branch assignment column if missing
    if "agents" in insp.get_table_names():
        agent_cols = [col["name"] for col in insp.get_columns("agents")]
        if "branch_id" not in agent_cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE agents ADD COLUMN branch_id INTEGER"))

    # create agent group rules table if missing
    if "agent_group_rules" not in insp.get_table_names():
        with engine.begin() as conn:
            conn.execute(text(
                """
                CREATE TABLE IF NOT EXISTS agent_group_rules (
                    id SERIAL PRIMARY KEY,
                    match_value VARCHAR(256) NOT NULL,
                    branch_id INTEGER NOT NULL REFERENCES branches(id),
                    enabled BOOLEAN DEFAULT TRUE,
                    priority INTEGER DEFAULT 100,
                    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now(),
                    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now()
                )
                """
            ))


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
        # Ensure DB schema has branch_id and branches table before we query user role
        try:
            ensure_user_columns()
        except ProgrammingError:
            # If this fails, rollback and continue; the later seeds may still succeed
            db.rollback()
        # Create initial admin or super_admin user if missing
        admin_password = os.getenv("ADMIN_PASSWORD")
        if not admin_password:
            raise ValueError("ADMIN_PASSWORD environment variable must be set")
        admin_username = os.getenv("ADMIN_USERNAME", "admin")
        admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
        admin_role = os.getenv("ADMIN_ROLE", "super_admin")
        if admin_role not in ["super_admin", "admin", "operator"]:
            admin_role = "super_admin"

        # Ensure at least one super_admin exists
        existing_super = db.query(User).filter(User.role == "super_admin").first()
        if not existing_super:
            role_to_create = "super_admin"
        else:
            role_to_create = admin_role if admin_role in ["admin", "operator"] else "admin"

        if _upsert_user(
            db,
            username=admin_username,
            email=admin_email,
            password=admin_password,
            role=role_to_create,
            can_view_unmasked_numbers=True,
        ):
            created_users.append(f"{admin_username} ({role_to_create})")
        elif not existing_super:
            # User already exists but has no super_admin in the system — upgrade them
            existing_admin = db.query(User).filter(User.username == admin_username).first()
            if existing_admin and existing_admin.role != "super_admin":
                existing_admin.role = "super_admin"
                created_users.append(f"{admin_username} (upgraded to super_admin)")

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

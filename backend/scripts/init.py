"""
Initialization script - prepare environment and database
"""
import os
import sys
import subprocess

def setup_environment():
    """Setup environment and dependencies"""
    print("=" * 60)
    print("FusionPBX Analytics Dashboard - Environment Setup")
    print("=" * 60)
    
    # Check environment variables
    print("\n1. Checking environment variables...")
    required_vars = ['FUSIONPBX_HOST', 'FUSIONPBX_API_KEY', 'DB_PASSWORD', 'JWT_SECRET']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"⚠ Missing environment variables: {', '.join(missing_vars)}")
        print("  Please set these in .env file")
    else:
        print("✓ All required environment variables set")
    
    # Check database
    print("\n2. Checking database connectivity...")
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("✗ DATABASE_URL environment variable is required")
        return False
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(db_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✓ Database connection successful")
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return False
    
    # Run migrations
    print("\n3. Running database migrations...")
    try:
        backend_dir = os.path.dirname(os.path.dirname(__file__))
        subprocess.run(
            [sys.executable, '-m', 'alembic', 'upgrade', 'head'],
            cwd=backend_dir,
            check=True,
        )
        print("✓ Migrations completed")
    except subprocess.CalledProcessError as e:
        print(f"⚠ Migration warning: {e}")
    
    # Seed database
    print("\n4. Seeding initial data...")
    try:
        from scripts.seed import seed_database
        seed_database()
    except Exception as e:
        print(f"⚠ Seeding warning: {e}")
    
    print("\n" + "=" * 60)
    print("Setup complete! Ready to start application.")
    print("=" * 60)
    return True


if __name__ == "__main__":
    sys.exit(0 if setup_environment() else 1)

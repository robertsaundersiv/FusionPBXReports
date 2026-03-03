"""Add queue_extension and queue_context columns to queues table"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import engine
from sqlalchemy import text

def add_columns():
    """Add new columns to queues table"""
    with engine.connect() as conn:
        try:
            # Add queue_extension column
            conn.execute(text("ALTER TABLE queues ADD COLUMN IF NOT EXISTS queue_extension VARCHAR(50)"))
            print("✓ Added queue_extension column")
        except Exception as e:
            print(f"Note: queue_extension column may already exist: {e}")
        
        try:
            # Add queue_context column
            conn.execute(text("ALTER TABLE queues ADD COLUMN IF NOT EXISTS queue_context VARCHAR(256)"))
            print("✓ Added queue_context column")
        except Exception as e:
            print(f"Note: queue_context column may already exist: {e}")
        
        conn.commit()
        print("✓ Database schema updated successfully")

if __name__ == "__main__":
    add_columns()

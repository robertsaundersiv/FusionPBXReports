# import sqlite3

# conn = sqlite3.connect('phone_reports.db')
# cursor = conn.cursor()

# # Get all tables
# cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
# print("Tables in database:")
# for row in cursor.fetchall():
#     print(f"  - {row[0]}")

# conn.close()

from sqlalchemy import text
result = db.execute(text("SELECT id, rtp_audio_in_mos FROM cdr_record LIMIT 5")).fetchall()
print(result)
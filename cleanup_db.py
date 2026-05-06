import sqlite3
import os

db_path = "/home/dave/.openclaw/workspace/projects/beat-manager/state.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 1. Fix IDs with quotes
cursor.execute("SELECT id, rowid FROM library_assets")
rows = cursor.fetchall()
count_id = 0
for old_id, rowid in rows:
    if old_id and (old_id.startswith("'") or old_id.endswith("'") or old_id.startswith('"')):
        new_id = old_id.strip("'").strip('"')
        cursor.execute("UPDATE library_assets SET id = ? WHERE rowid = ?", (new_id, rowid))
        count_id += 1

# 2. Fix NULL asset_types
cursor.execute("UPDATE library_assets SET asset_type = 'raw' WHERE asset_type IS NULL AND data_type = 'audio'")
cursor.execute("UPDATE library_assets SET asset_type = 'cover' WHERE asset_type IS NULL AND data_type = 'image'")
cursor.execute("UPDATE library_assets SET asset_type = 'beat' WHERE asset_type IS NULL AND name LIKE 'beat%'")

conn.commit()
print(f"Cleaned up {count_id} IDs and filled NULL asset types.")

# 3. Final verification print
cursor.execute("SELECT asset_type, count(*) FROM library_assets GROUP BY asset_type")
print("Counts by type:", cursor.fetchall())
conn.close()

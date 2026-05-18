#!/usr/bin/env python3
"""Debug: Check if routing decisions are being persisted."""
import sqlite3
from pathlib import Path
from datetime import datetime

db_path = Path.home() / '.hermes' / 'plugins' / 'hermes-smart-router' / 'router_state.db'

print(f"Database path: {db_path}")
print(f"Database exists: {db_path.exists()}")
if db_path.exists():
    print(f"Database size: {db_path.stat().st_size} bytes")
    print(f"Last modified: {datetime.fromtimestamp(db_path.stat().st_mtime)}")

try:
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Count total routing runs
    cursor.execute("SELECT COUNT(*) FROM routing_runs")
    count = cursor.fetchone()[0]
    print(f"\nTotal routing runs in database: {count}")
    
    # Get latest timestamp
    cursor.execute("SELECT MAX(timestamp) FROM routing_runs")
    latest = cursor.fetchone()[0]
    print(f"Latest timestamp: {latest}")
    
    # List all prompts
    cursor.execute("SELECT timestamp, prompt FROM routing_runs ORDER BY timestamp DESC")
    print("\nAll routing runs (newest first):")
    for ts, prompt in cursor.fetchall():
        print(f"  {ts}: {prompt[:60]}")
    
    conn.close()
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

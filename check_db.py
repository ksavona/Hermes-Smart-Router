#!/usr/bin/env python3
"""Check routing runs in the database."""
import sqlite3
from pathlib import Path

db_path = Path.home() / '.hermes' / 'plugins' / 'hermes-smart-router' / 'router_state.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get count
cursor.execute("SELECT COUNT(*) FROM routing_runs")
count = cursor.fetchone()[0]
print(f"Total routing runs recorded: {count}\n")

# Get recent runs
cursor.execute("""
    SELECT timestamp, prompt, selected_model 
    FROM routing_runs 
    ORDER BY timestamp DESC 
    LIMIT 10
""")

for i, (ts, prompt, model) in enumerate(cursor.fetchall(), 1):
    print(f"{i}. [{ts}] {prompt[:50]} → {model}")

conn.close()

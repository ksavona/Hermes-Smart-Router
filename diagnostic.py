#!/usr/bin/env python3
"""Comprehensive test of the routing system."""

import sys
import json
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

print("=" * 80)
print("HERMES SMART ROUTER - DIAGNOSTIC TEST")
print("=" * 80)

# Step 1: Check database file
db_path = Path.home() / '.hermes' / 'plugins' / 'hermes-smart-router' / 'router_state.db'
print(f"\n1. Database File Check:")
print(f"   Path: {db_path}")
print(f"   Exists: {db_path.exists()}")
if db_path.exists():
    stat = db_path.stat()
    print(f"   Size: {stat.st_size} bytes")
    print(f"   Modified: {datetime.fromtimestamp(stat.st_mtime)}")

# Step 2: Check SQLite contents
print(f"\n2. SQLite Database Contents:")
try:
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM routing_runs")
    count = cursor.fetchone()[0]
    print(f"   Total routing runs: {count}")
    
    cursor.execute("SELECT MAX(timestamp) FROM routing_runs")
    latest_ts = cursor.fetchone()[0]
    print(f"   Latest timestamp: {latest_ts}")
    
    cursor.execute("SELECT timestamp, prompt_preview FROM routing_runs ORDER BY id DESC LIMIT 3")
    print(f"   Latest 3 prompts:")
    for ts, prompt in cursor.fetchall():
        print(f"     - {ts}: {prompt[:50]}")
    
    conn.close()
except Exception as e:
    print(f"   ERROR: {e}")

# Step 3: Test the route tool directly
print(f"\n3. Direct Route Tool Test:")
try:
    from hermes_smart_router.tools import route
    
    test_prompt = f"Test prompt at {datetime.now().isoformat()}"
    print(f"   Test prompt: {test_prompt}")
    
    result_json = route({"prompt": test_prompt, "context": {}})
    result = json.loads(result_json)
    
    if "error" in result:
        print(f"   ERROR: {result['error']}")
    else:
        print(f"   Selected model: {result.get('selected_model')}")
        print(f"   Confidence: {result.get('confidence')}%")
        
except Exception as e:
    print(f"   ERROR: {e}")
    import traceback
    traceback.print_exc()

# Step 4: Check if new routing run was added
print(f"\n4. Database Check After Route Tool Call:")
try:
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM routing_runs")
    count = cursor.fetchone()[0]
    print(f"   Total routing runs: {count}")
    
    cursor.execute("SELECT prompt_preview FROM routing_runs ORDER BY id DESC LIMIT 1")
    latest_prompt = cursor.fetchone()[0]
    print(f"   Latest prompt: {latest_prompt}")
    
    conn.close()
except Exception as e:
    print(f"   ERROR: {e}")

print("\n" + "=" * 80)
print("DIAGNOSTIC TEST COMPLETE")
print("=" * 80)

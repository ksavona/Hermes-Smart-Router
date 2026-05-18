#!/usr/bin/env python3
"""Test if the route tool is being invoked and persisting data."""

import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent / 'src'))

print("=" * 80)
print("DIRECT ROUTE TOOL TEST")
print("=" * 80)

# Import and test the route function
from hermes_smart_router.tools import route

# Test with a unique identifier
test_id = datetime.now().strftime("%Y%m%d-%H%M%S")
test_prompt = f"[TEST-{test_id}] What is the capital of France?"

print(f"\n1. Calling route() directly with: {test_prompt}")
print("-" * 80)

try:
    result_json = route({
        "prompt": test_prompt,
        "context": {}
    })
    result = json.loads(result_json)
    
    if "error" in result:
        print(f"ERROR: {result['error']}")
    else:
        print(f"✓ Route returned successfully")
        print(f"  Selected: {result.get('selected_provider')} {result.get('selected_model')}")
        print(f"  Fallback: {result.get('fallback_provider')} {result.get('fallback_model')}")
        print(f"  Confidence: {result.get('confidence')}%")
        
except Exception as e:
    print(f"✗ ERROR calling route: {e}")
    import traceback
    traceback.print_exc()

# Check if it was persisted
print(f"\n2. Checking if routing decision was persisted to database")
print("-" * 80)

try:
    import sqlite3
    db_path = Path.home() / '.hermes' / 'plugins' / 'hermes-smart-router' / 'router_state.db'
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Count total runs
    cursor.execute("SELECT COUNT(*) FROM routing_runs")
    total_count = cursor.fetchone()[0]
    print(f"Total routing runs in DB: {total_count}")
    
    # Check if our test prompt is there
    cursor.execute(
        "SELECT COUNT(*) FROM routing_runs WHERE prompt_preview LIKE ?",
        (f"%TEST-{test_id}%",)
    )
    found_count = cursor.fetchone()[0]
    
    if found_count > 0:
        print(f"✓ TEST PROMPT FOUND in database!")
        cursor.execute(
            "SELECT timestamp, prompt_preview FROM routing_runs WHERE prompt_preview LIKE ? LIMIT 1",
            (f"%TEST-{test_id}%",)
        )
        ts, prompt = cursor.fetchone()
        print(f"  Timestamp: {ts}")
        print(f"  Prompt: {prompt}")
    else:
        print(f"✗ TEST PROMPT NOT FOUND in database!")
        print(f"  This means the route() function is NOT persisting data.")
    
    # Show latest 3 prompts
    print(f"\nLatest 3 prompts in database:")
    cursor.execute(
        "SELECT timestamp, prompt_preview FROM routing_runs ORDER BY id DESC LIMIT 3"
    )
    for i, (ts, prompt) in enumerate(cursor.fetchall(), 1):
        print(f"  {i}. {ts}: {prompt[:50]}")
    
    conn.close()
    
except Exception as e:
    print(f"✗ ERROR checking database: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)

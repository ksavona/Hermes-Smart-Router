#!/usr/bin/env python3
"""Test if routing decisions are being persisted when called directly."""
import sys
sys.path.insert(0, 'src')

from hermes_smart_router.tools import route
from pathlib import Path
import json

# Test prompts
test_prompts = [
    "Write me a haiku about evening",
    "What is Python?",
    "How do neural networks work?",
]

print("Testing route tool directly...\n")

for i, prompt in enumerate(test_prompts, 1):
    print(f"Test {i}: {prompt}")
    result_json = route({"prompt": prompt, "context": {}})
    result = json.loads(result_json)
    
    if "error" in result:
        print(f"  ERROR: {result['error']}\n")
    else:
        print(f"  Selected: {result.get('selected_model')}")
        print(f"  Confidence: {result.get('confidence')}%\n")

# Now check if they were persisted
print("\nChecking database for routing runs...\n")
import sqlite3
db_path = Path.home() / '.hermes' / 'plugins' / 'hermes-smart-router' / 'router_state.db'
conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

cursor.execute("SELECT COUNT(*) FROM routing_runs")
count = cursor.fetchone()[0]
print(f"Total routing runs in database: {count}")

cursor.execute("SELECT prompt_preview FROM routing_runs ORDER BY id DESC LIMIT 5")
print("\nLatest 5 prompts:")
for i, (prompt,) in enumerate(cursor.fetchall(), 1):
    print(f"  {i}. {prompt[:60]}")

conn.close()

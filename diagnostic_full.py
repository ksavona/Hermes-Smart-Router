#!/usr/bin/env python3
"""Comprehensive diagnostic of the hook system and routing."""

import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, 'src')

print("=" * 100)
print(" HERMES SMART ROUTER - COMPREHENSIVE DIAGNOSTIC ".center(100, "="))
print("=" * 100)

# SECTION 1: Plugin Import & Registration
print("\n[1] PLUGIN REGISTRATION TEST")
print("-" * 100)

try:
    from hermes_smart_router import register, _pre_llm_call_route
    
    class MockContext:
        def __init__(self):
            self.registered_items = {"tools": [], "hooks": []}
            self.plugin_info = None
        
        def register_tool(self, **kwargs):
            self.registered_items["tools"].append(kwargs['name'])
        
        def register_hook(self, hook_name, handler):
            self.registered_items["hooks"].append((hook_name, handler.__name__))
    
    ctx = MockContext()
    register(ctx)
    
    print(f"✓ Plugin import successful")
    print(f"  - Tools registered: {ctx.registered_items['tools']}")
    print(f"  - Hooks registered: {[h[0] for h in ctx.registered_items['hooks']]}")
    
except Exception as e:
    print(f"✗ Plugin import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# SECTION 2: Hook Function Test
print("\n[2] HOOK FUNCTION TEST")
print("-" * 100)

try:
    test_prompt = f"[DIAGNOSTIC-{datetime.now().isoformat()}] Test prompt for routing"
    
    print(f"Calling _pre_llm_call_route() with test prompt...")
    result = _pre_llm_call_route(
        user_message=test_prompt,
        session_id="diag-session-001",
        context={},
        model="gpt-4",
        is_first_turn=True
    )
    
    if result:
        print(f"✓ Hook executed successfully")
        print(f"  - Returned type: {type(result)}")
        print(f"  - Keys: {list(result.keys())}")
        if 'context' in result:
            context_len = len(result['context'])
            print(f"  - Context length: {context_len} chars")
            print(f"  - Context preview: {result['context'][:80]}...")
    else:
        print(f"✗ Hook returned None (unexpected)")

except Exception as e:
    print(f"✗ Hook execution failed: {e}")
    import traceback
    traceback.print_exc()

# SECTION 3: Database State Check
print("\n[3] DATABASE STATE CHECK")
print("-" * 100)

try:
    import sqlite3
    
    db_path = Path.home() / '.hermes' / 'plugins' / 'hermes-smart-router' / 'router_state.db'
    
    if not db_path.exists():
        print(f"✗ Database not found at {db_path}")
        sys.exit(1)
    
    print(f"✓ Database found: {db_path}")
    print(f"  - Size: {db_path.stat().st_size} bytes")
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Total runs
    cursor.execute("SELECT COUNT(*) FROM routing_runs")
    total_runs = cursor.fetchone()[0]
    print(f"\n  Total routing runs: {total_runs}")
    
    # Latest runs
    print(f"\n  Latest 5 routing runs:")
    cursor.execute("""
        SELECT id, timestamp, prompt_preview, selected_model 
        FROM routing_runs 
        ORDER BY id DESC 
        LIMIT 5
    """)
    
    for i, (id, ts, prompt, model) in enumerate(cursor.fetchall(), 1):
        print(f"    {i}. [{id:3d}] {ts}: {prompt[:45]:45s} → {model}")
    
    # Check if diagnostic prompt is there
    cursor.execute("""
        SELECT COUNT(*) FROM routing_runs 
        WHERE prompt_preview LIKE '%DIAGNOSTIC%'
    """)
    diag_count = cursor.fetchone()[0]
    print(f"\n  Diagnostic prompts in database: {diag_count}")
    
    conn.close()

except Exception as e:
    print(f"✗ Database check failed: {e}")
    import traceback
    traceback.print_exc()

# SECTION 4: Hermes Integration Status
print("\n[4] HERMES INTEGRATION STATUS")
print("-" * 100)

print(f"To verify hook is being called by Hermes:")
print(f"  1. Run: hermes chat")
print(f"  2. Send a test prompt")
print(f"  3. Re-run this diagnostic")
print(f"  4. Check if new routing runs appear in the database")
print(f"  5. Check Hermes logs for [ROUTE-HOOK] messages")
print(f"")
print(f"Hermes logs location:")
print(f"  journalctl --user-unit hermes-gateway -n 100 --no-pager | grep ROUTE")

print("\n" + "=" * 100)
print(" DIAGNOSTIC COMPLETE ".center(100, "="))
print("=" * 100)

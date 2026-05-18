#!/usr/bin/env python3
"""Test if the pre_llm_call hook is working."""

import sys
sys.path.insert(0, 'src')

print("=" * 80)
print("TESTING PRE_LLM_CALL HOOK REGISTRATION")
print("=" * 80)

# Test 1: Can we import and call register?
print("\n1. Testing plugin registration...")
try:
    from hermes_smart_router import register
    
    class MockContext:
        def __init__(self):
            self.tools = []
            self.hooks = []
            self.plugin_info = None
        
        def register_tool(self, **kwargs):
            self.tools.append(kwargs)
            print(f"   ✓ Tool registered: {kwargs.get('name')}")
        
        def register_hook(self, hook_name, handler):
            self.hooks.append((hook_name, handler))
            print(f"   ✓ Hook registered: {hook_name}")
        
    ctx = MockContext()
    register(ctx)
    
    print(f"\n   Total tools registered: {len(ctx.tools)}")
    print(f"   Total hooks registered: {len(ctx.hooks)}")
    
    if ctx.hooks:
        for hook_name, handler in ctx.hooks:
            print(f"     - {hook_name}: {handler.__name__}")
    
except Exception as e:
    print(f"   ✗ ERROR: {e}")
    import traceback
    traceback.print_exc()

# Test 2: Can we call the hook function directly?
print("\n2. Testing hook function directly...")
try:
    from hermes_smart_router import _pre_llm_call_route
    
    result = _pre_llm_call_route(
        user_message="test prompt",
        session_id="test-session-123",
        context={}
    )
    
    if result:
        print(f"   ✓ Hook returned: {list(result.keys())}")
        if 'context' in result:
            print(f"   ✓ Context provided: {result['context'][:50]}...")
    else:
        print(f"   ⚠ Hook returned None")
        
except Exception as e:
    print(f"   ✗ ERROR: {e}")
    import traceback
    traceback.print_exc()

# Test 3: Check if routing persisted
print("\n3. Checking if routing was persisted to database...")
try:
    import sqlite3
    from pathlib import Path
    
    db_path = Path.home() / '.hermes' / 'plugins' / 'hermes-smart-router' / 'router_state.db'
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM routing_runs WHERE prompt_preview LIKE ?", ("%test prompt%",))
    count = cursor.fetchone()[0]
    
    if count > 0:
        print(f"   ✓ Test prompt found in database: {count} runs")
    else:
        print(f"   ⚠ Test prompt NOT found in database")
        print(f"   Recent prompts:")
        cursor.execute("SELECT prompt_preview FROM routing_runs ORDER BY id DESC LIMIT 3")
        for prompt, in cursor.fetchall():
            print(f"     - {prompt[:60]}")
    
    conn.close()
    
except Exception as e:
    print(f"   ✗ ERROR: {e}")

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)

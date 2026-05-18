#!/usr/bin/env python3
"""Direct test of the hermes_smart_router plugin."""
import sys
import json
from pathlib import Path

# Test 1: Can we import the module?
try:
    from hermes_smart_router import register, schemas, tools
    print("✓ Successfully imported hermes_smart_router module")
except ImportError as e:
    print(f"✗ Failed to import hermes_smart_router: {e}")
    sys.exit(1)

# Test 2: Check the ROUTE schema
try:
    assert hasattr(schemas, 'ROUTE'), "ROUTE schema not found"
    assert schemas.ROUTE['name'] == 'route', f"Schema name is {schemas.ROUTE['name']}, expected 'route'"
    print(f"✓ ROUTE schema is valid: {schemas.ROUTE['name']}")
except AssertionError as e:
    print(f"✗ ROUTE schema invalid: {e}")
    sys.exit(1)

# Test 3: Can we call the route handler directly?
try:
    # Create a mock context object
    class MockContext:
        def __init__(self):
            self.registered_tools = []
        
        def register_tool(self, name, toolset, schema, handler):
            self.registered_tools.append({
                'name': name,
                'toolset': toolset,
                'schema': schema,
                'handler': handler
            })
    
    ctx = MockContext()
    register(ctx)
    
    assert len(ctx.registered_tools) > 0, "No tools registered"
    assert ctx.registered_tools[0]['name'] == 'route', f"Tool name is {ctx.registered_tools[0]['name']}, expected 'route'"
    print(f"✓ register(ctx) successfully registered tool: {ctx.registered_tools[0]['name']}")
except Exception as e:
    print(f"✗ Failed to call register(ctx): {e}")
    sys.exit(1)

# Test 4: Can we call the route handler?
try:
    result = tools.route({
        'prompt': 'What is 2+2?',
        'context': {}
    })
    result_dict = json.loads(result)
    print(f"✓ route handler returned valid JSON: {list(result_dict.keys())}")
except Exception as e:
    print(f"✗ Failed to call route handler: {e}")
    sys.exit(1)

print("\n✓ All tests passed! Plugin is functional.")
print("\nNext steps:")
print("1. Restart Hermes gateway: hermes gateway restart")
print("2. Verify plugin is loaded: hermes plugins list")
print("3. Test in Hermes CLI: hermes chat")

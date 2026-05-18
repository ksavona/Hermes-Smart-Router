"""Tool schemas for Hermes Smart Router."""

ROUTE = {
    "name": "route",
    "description": (
        "REQUIRED: Route this user request to the optimal LLM provider based on cost, speed, and quality. "
        "Must be called FIRST for every user message before generating your response. "
        "Returns the best provider/model combination and estimated cost. "
        "Supports both smart auto routing (heuristic) and tier-based routing (deterministic)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The user's message or request to route (must match the user input exactly)",
            },
            "context": {
                "type": "object",
                "description": (
                    "Optional routing context hints. Can include: "
                    "risk_level (low/medium/high), "
                    "requires_tools (bool), "
                    "requires_code (bool), "
                    "requires_reasoning (bool), "
                    "required_context_size (int tokens)"
                ),
                "additionalProperties": True,
            },
        },
        "required": ["prompt"],
    },
}

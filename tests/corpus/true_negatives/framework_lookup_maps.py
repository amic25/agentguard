"""A local variable named `function_map` is not AutoGen's function_map parameter.

Measured false positive in openai-agents-python: realtime/session.py:954 and
run_internal/turn_resolution.py:1744. AG003 matches a bare `function_map\\s*=`.
"""

from typing import Any


def build(tools: list[Any], handoffs: list[Any]) -> dict[str, Any]:
    function_map = {tool.name: tool for tool in tools}
    handoff_map = {handoff.tool_name: handoff for handoff in handoffs}
    return {**function_map, **handoff_map}

"""exec over a module-level constant reaches no attacker-controlled value.

Measured false positive in browser-use (mcp/cli_mcp.py:105). Distinct from
eval_on_literal.py: the argument is a Name, not a literal, so literal-argument detection
does not catch it.
"""

_NAMESPACE_IMPORTS = "import json\nimport os\n"


def build_namespace() -> dict[str, object]:
    namespace: dict[str, object] = {}
    exec(_NAMESPACE_IMPORTS, namespace)
    return namespace

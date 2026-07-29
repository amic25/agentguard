"""eval over a compile-time constant reaches no attacker-controlled value."""

SETTINGS = eval("{'retries': 3}")
LIMIT = eval("2 + 2")

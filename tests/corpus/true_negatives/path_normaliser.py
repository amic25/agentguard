"""Prefixing a leading slash is normalisation, not granting a filesystem root.

Measured false positive in crewAI (memory/utils.py:61). AG005's broad-root pattern
matches `path = "/"` and does not distinguish it from `path = "/" + path`.
"""

import re


def normalise(path: str) -> str:
    if not path:
        return "/"
    path = re.sub(r"/+", "/", path)
    if not path.startswith("/"):
        path = "/" + path
    return path.rstrip("/") if len(path) > 1 else path

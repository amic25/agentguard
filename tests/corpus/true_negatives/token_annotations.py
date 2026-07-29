"""A type annotation is not a credential.

Measured false positive in openai-agents-python (tracing/scope.py:34 and :47).
"""

import contextvars
from typing import Any


class Scope:
    @classmethod
    def reset_current_span(cls, token: "contextvars.Token[Any]") -> None:
        return None

    @classmethod
    def reset_current_trace(cls, token: "contextvars.Token[Any]") -> None:
        return None

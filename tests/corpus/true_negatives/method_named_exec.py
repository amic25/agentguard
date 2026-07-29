"""`.exec()` on an object is not the builtin `exec`.

Measured false positive in openai-agents-python (sandbox/sandboxes/docker.py).
"""


class Sandbox:
    async def run(self, *command: str) -> str:
        return await super().exec(*command)

    def evaluate(self, expression: str) -> object:
        return self.client().eval(expression)

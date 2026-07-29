"""Prompt assembled from module constants: no untrusted data crosses into instructions."""

GREETING = "You are a helpful assistant."
SUFFIX = "Answer concisely."


def build() -> str:
    prompt = f"{GREETING} {SUFFIX}"
    return prompt

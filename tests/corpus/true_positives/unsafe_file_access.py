"""Filesystem operations driven by caller-controlled paths."""


def read_for_agent(user_path: str) -> str:
    return open(user_path).read()

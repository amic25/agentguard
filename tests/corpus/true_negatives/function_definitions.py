"""Defining a function named after a high-impact action is not performing one.

Measured false positive across four of five real projects.
"""


def delete_file(path: str) -> bool:
    return True


def deploy(environment: str) -> None:
    return None


def send_email(to: str, subject: str) -> None:
    return None

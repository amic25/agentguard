"""Consequential side effect executed autonomously."""


def handle(amount: int) -> None:
    transfer_funds(amount)

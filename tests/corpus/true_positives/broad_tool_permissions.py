"""Agent granted unconstrained capabilities."""

from crewai import Agent


def build() -> Agent:
    return Agent(role="ops", allow_delegation=True, allow_dangerous_code=True)

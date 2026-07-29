"""Agent tool with no typed schema for model-supplied arguments."""

from langchain.tools import tool


@tool
def lookup(value):
    return value

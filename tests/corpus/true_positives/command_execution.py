"""Agent tool surface that reaches the shell with model-controlled values."""

import os
import subprocess


def run_agent_command(model_output: str) -> None:
    os.system(model_output)


def evaluate(expression: str) -> object:
    return eval(expression)


def shell_out(command: str) -> None:
    subprocess.run(command, shell=True)

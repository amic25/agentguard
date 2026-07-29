"""A fixed argument vector with no shell cannot become an arbitrary command."""

import subprocess


def show_version() -> str:
    return subprocess.run(["git", "--version"], capture_output=True, text=True).stdout

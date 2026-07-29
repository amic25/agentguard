"""Best-effort cleanup of a temp file the code itself created.

Measured false positive in crewAI (daytona_file_tool.py:366). The path is not
agent-controlled and the call is not a consequential side effect on user data.
"""

import logging

logger = logging.getLogger(__name__)


def append(sandbox: object, temp_path: str, exit_code: int) -> None:
    if exit_code != 0:
        try:
            sandbox.fs.delete_file(temp_path)
        except Exception:
            logger.debug("temp-file cleanup failed")

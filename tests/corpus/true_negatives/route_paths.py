"""An HTTP route is not a filesystem root.

Measured false positive in modelcontextprotocol/python-sdk (8 occurrences).
"""

from starlette.routing import Mount


def build(mcp: object) -> list[Mount]:
    # streamable_http_path="/" means the endpoint is served at the mount prefix
    return [Mount("/api", app=mcp.streamable_http_app(streamable_http_path="/"))]

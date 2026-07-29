"""An outbound call to a compile-time host, over TLS, with a timeout.

Measured false positive in crewAI (contextual_query_tool.py:49,
merge_agent_handler_tool.py:97). AG006's dynamic-URL pattern matches any first argument
named `url`, regardless of how the value was built.
"""

import requests


def list_documents(datastore_id: str, api_key: str) -> object:
    url = f"https://api.contextual.ai/v1/datastores/{datastore_id}/documents"
    headers = {"Authorization": f"Bearer {api_key}"}
    return requests.get(url, headers=headers, timeout=30)

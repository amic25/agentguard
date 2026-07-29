"""Documentation examples are not committed credentials."""


def sign(private_key_pem: str) -> bytes:
    """Sign a payload.

    Example:
        >>> sign(private_key_pem="-----BEGIN PRIVATE KEY-----...")
        b'...'
    """
    return b""


def call_api(crew_bearer_token: str) -> None:
    """Invoke the automation API.

    Example:
        >>> call_api(crew_bearer_token="[Your token: abcdef012345]")
    """

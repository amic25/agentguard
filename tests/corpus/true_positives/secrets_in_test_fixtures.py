"""A test module. Credential-shaped literals here are fixtures, not credentials.

This is the single largest false-positive source measured against real projects.
"""


def test_client_authenticates() -> None:
    client = build_client(api_key="explicit-key")
    assert client.token == "expired_token"


def test_rejects_bad_password() -> None:
    assert not login(password="invalid_password")

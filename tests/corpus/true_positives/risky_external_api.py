"""Plaintext and caller-controlled outbound requests."""

import requests


def fetch_insecure() -> object:
    return requests.get("http://internal.service.invalid/api")

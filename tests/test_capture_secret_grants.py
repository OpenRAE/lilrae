"""Granted credential values cannot survive text or nested JSON capture."""

import json


def test_known_secret_values_are_removed_with_existing_redaction():
    from aptl.utils.redaction import redact_granted_secrets

    secret = 'private"credential'
    value = {
        "content": "echo " + secret,
        "nested": json.dumps({"text": secret}),
        "api_key": "another-secret",
        "input_tokens": 12,
    }
    safe = redact_granted_secrets(value, (secret,))
    assert secret not in safe["content"]
    assert secret not in json.loads(safe["nested"])["text"]
    assert safe["api_key"] == "[REDACTED]"
    assert safe["input_tokens"] == 12

"""Registry digests for the third-party helper images lab start runs by tag.

Lab start runs the Wazuh certificate generator and the Suricata seeder by their
tags, which is also how the sealed appliance stages them for an offline start.
Before an online start runs either, ``pull_images`` points the tag at the digest
pinned here, so an upstream re-tag never changes what runs.
"""

from __future__ import annotations

CERT_GENERATOR_IMAGE = "wazuh/wazuh-certs-generator:0.0.2"
SURICATA_SEEDER_IMAGE = "jasonish/suricata:7.0"

PINNED_HELPER_IMAGES: dict[str, str] = {
    CERT_GENERATOR_IMAGE: (
        f"{CERT_GENERATOR_IMAGE}@sha256:"
        "88c4b30ad9b8320ba29f0a891761ad8000866c15c844d27b04974f5cb427c8f0"
    ),
    SURICATA_SEEDER_IMAGE: (
        f"{SURICATA_SEEDER_IMAGE}@sha256:"
        "0364b6f31192bc27a84dd471f60de22781d88e4d9511fbd3413e56ba4e150ac8"
    ),
}

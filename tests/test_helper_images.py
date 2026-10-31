"""Guard: lab start's third-party helper images have one pinned digest each.

The certificate generator and the Suricata seeder run by tag, online and in the
sealed appliance. ``aptl.core.helper_images`` is the one place their digests are
pinned; every runtime use names a pinned tag, and the appliance inventory uses
the same pins.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from aptl.core.helper_images import (
    CERT_GENERATOR_IMAGE,
    PINNED_HELPER_IMAGES,
    SURICATA_SEEDER_IMAGE,
)

ROOT = Path(__file__).resolve().parents[1]


def test_each_pin_is_its_tag_at_one_sha256_digest() -> None:
    """A pin keeps the runtime tag and adds exactly one registry digest."""
    for tag, pinned in PINNED_HELPER_IMAGES.items():
        assert re.fullmatch(re.escape(tag) + r"@sha256:[0-9a-f]{64}", pinned), pinned


def test_every_runtime_use_names_a_pinned_tag() -> None:
    """The generator's Compose file and the seeder constants use pinned tags."""
    from aptl.core.deployment._compose_content_realization import (
        CONTENT_SEEDER_IMAGE,
    )
    from aptl.core.lab import SURICATA_IMAGE
    from aptl.core.suricata_seed import _SURICATA_SEEDER_IMAGE

    compose = yaml.safe_load((ROOT / "generate-indexer-certs.yml").read_text())
    assert compose["services"]["generator"]["image"] == CERT_GENERATOR_IMAGE
    seeder_tags = {SURICATA_IMAGE, CONTENT_SEEDER_IMAGE, _SURICATA_SEEDER_IMAGE}
    assert seeder_tags == {SURICATA_SEEDER_IMAGE}
    assert set(PINNED_HELPER_IMAGES) == {CERT_GENERATOR_IMAGE, SURICATA_SEEDER_IMAGE}


def test_the_appliance_inventory_uses_the_same_pins() -> None:
    """The sealed appliance bakes exactly the digests an online start runs."""
    from aptl.appliance.input_images import _pin_third_party

    for tag, pinned in PINNED_HELPER_IMAGES.items():
        assert _pin_third_party(tag) == pinned

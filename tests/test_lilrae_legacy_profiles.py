"""Undriven services do not remain in the generic Compose inventory."""
from pathlib import Path
import yaml


def test_generic_compose_has_no_undriven_mail_or_reverse_profile():
    root = Path(__file__).resolve().parents[1]
    model = yaml.safe_load((root / 'docker-compose.yml').read_text())
    assert 'mailserver' not in model['services']
    assert 'reverse' not in model['services']
    profiles = {profile for service in model['services'].values() for profile in service.get('profiles', ())}
    assert not {'mail', 'reverse'} & profiles

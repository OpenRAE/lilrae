# Why red-side capture stays outside the SIEM

This Explanation describes the non-contamination decision.
See the [Kali reference](kali-redteam.md) for the current capture mechanism.

## Why no SIEM integration

Prior revisions of this container ran a Wazuh agent and forwarded
red-side activity to the Wazuh manager via rsyslog + the
`kali_redteam_rules.xml` decoder. That gave the blue stack an
artificial picture of red activity that no real defender would have.
Under [ADR-033](../adrs/adr-033-agent-reasoning-trace-boundary.md)
that forwarding path is removed: blue's perception layer must reflect only what
blue's own sensors detect, not what the attacker self-reports.

If a future requirement wants blue to learn red activity, that requires a separately designed research-data or summary interface.
It does not authorize direct red-to-SIEM forwarding.

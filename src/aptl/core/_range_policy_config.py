"""Exact operator grants for native range egress."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RangeEgressAllowance(BaseModel):
    """Operator-declared exact external destination and transport port."""

    model_config = ConfigDict(extra="forbid", strict=True)
    destination: str
    protocol: Literal["tcp", "udp"]
    port: int = Field(ge=1, le=65535)

    @field_validator("destination")
    @classmethod
    def validate_destination(cls, value: str) -> str:
        from ipaddress import ip_address

        address = ip_address(value)
        if address.is_loopback or address.is_multicast or address.is_unspecified:
            raise ValueError("egress destination must be an exact unicast IP address")
        return str(address)

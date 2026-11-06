# Why TechVault has a backend adapter

This Explanation describes scenario ownership and generic backend responsibilities.
See the [adapter reference](https://github.com/OpenRAE/lilrae/blob/dev/src/aptl_techvault/README.md).

## Why it lives here

The adapter binds portable scenario declarations to LilRAE's native resources and operator groups.
It names resources such as `aptl-kali` and `aptl-wazuh-manager` because its verification concerns this scenario on this backend.
Another backend needs its own native bindings and qualification evidence.

The adapter currently ships inside the `lilrae` distribution. Its bundled
location is a delivery choice. An independently released adapter can own the
same behavior through the [public family contract](../reference/family-adapters.md).
RPT owns its TechVault-family implementation and qualification evidence.
LilRAE keeps generic admission, lifecycle, capture and verification machinery.

The bundled adapter keeps its existing exact-release qualification. It does
not automatically qualify an RPT family or its admitted variations. Family
trials select providers that explicitly declare the public family API and the
exact family/release/backend target. Bundled legacy providers cannot satisfy
that qualification or mask a missing family capability.

# Curated scenario fixture reference

These fixtures belong to checkout-only backend research and the explicit guided participant profile.
They are excluded from default wheel assets and ordinary acquired-pack selection.
`scenarios/catalog.json` binds their identities and metadata.

| Catalog id | Includes | Omits | Selected profiles |
| --- | --- | --- | --- |
| `techvault-attacker-target` | Kali, monitored victim, Wazuh manager and indexer | Enterprise tier and wider SOC | `kali`, `victim`, `wazuh` |
| `techvault-enterprise-web` | Webapp, database, AD, workstation, Wazuh core | Attacker and wider SOC | `enterprise`, `wazuh` |
| `techvault-defensive-min` | Wazuh manager, indexer, dashboard | Attacker, enterprise, wider SOC | `wazuh` |

Profiles come from declared node content and dependency closure.
The enabled configuration gates the result.
Equivalent content must keep its realization after a scenario rename.

Compose can activate dependency services beyond explicitly declared nodes.
The provisioner validates the generated project before startup.
An excluded `depends_on` target produces `aptl.provisioner.compose-project-invalid`.
The enterprise fixture includes Wazuh because the workstation needs the manager.

Capture and OTel are backend apparatus, selected only after evidence and scope admission.
They are not authored scenario nodes.
A historical OTel proof does not establish current apparatus admission.

Use [author and validate a fixture](techvault-curated-variants.md) for operating steps.
The [historical live record](../raes/techvault-curated-live-validation-gate.md) keeps its original dates, counts, commands, and limitations.

## Source owners

| Surface | Owner |
| --- | --- |
| SDL semantics | Installed RAES parser and compiler |
| Realization and Compose profiles | `aptl.backends.raes_realization` and `raes_profiles` |
| Support dependencies | `aptl.backends.raes_dependency_closure` |
| Fixture identity | Existing research catalog contract in `scenarios/catalog.json` |
| Participant admission | Explicit profile path and digest bindings |

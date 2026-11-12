# Parser test boundaries

This Reference identifies canonical owners for parser property tests.
Follow [Add parser property tests](../testing/property-based-parser-tests.md) for the procedure.

| Boundary | Owner | Contract |
| --- | --- | --- |
| Durable configuration | `src/aptl/core/config.py`: `AptlConfig`, `load_config()` | Pydantic owns strict shape and supported values. |
| Environment input | `src/aptl/core/env.py`: `load_dotenv()`, `env_vars_from_dict()` | The production parser owns syntax and required variables. |
| Credential rendering | `src/aptl/core/credentials.py`: `sync_dashboard_config()`, `sync_manager_config()` | Project-root containment, no-symlink generated paths, XML/YAML escaping, and atomic writes. Public errors include `CredentialRenderError` and `PathContainmentError`. |
| Secret serialization | `src/aptl/utils/redaction.py`: `redact()` | ADR-029 owns the secret-handling boundary. |
| Scenario paths | `src/aptl/core/scenario_catalog.py` | RAES owns SDL parsing and its public error types. |

`pyproject.toml` excludes `fuzz`, `live_lab`, and `containment` from default test selection.
Explicit marker selection does not approve the workstation as a test host.

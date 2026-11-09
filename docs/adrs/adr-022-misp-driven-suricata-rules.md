# ADR-022: MISP-driven Suricata rules via a tag-graduated sync service

## Status

accepted

## Date

2026-05-03

## Reader boundary

This Explanation records design reasons and constraints.
Dated examples, versions, estimates, and measurements describe their stated revision.
They do not establish current interface support or installed qualification.
The [defensive posture](../components/default-defensive-posture.md) describes maintained use.
The record's status and amendments still determine its decision scope.

## Context

[Issue #250](https://github.com/Brad-Edwards/aptl/issues/250) connected MISP indicators with Suricata rules. Previously, MISP intelligence and operator-authored network detection were separate. Newly added indicators did not automatically produce rules. The design selected a common integration pattern. An analyst or feed adds intelligence, automation updates detection, and matching traffic produces an observation. The lab needs the same loop so blue's
threat-intel work composes with detection on the wire.

Two adjacent decisions constrain the design:

- **[ADR-019](adr-019-suricata-ids-only-prevention-via-wazuh-ar.md)**: Suricata stays IDS-only. Packet-level prevention is delivered by Wazuh
  active-response. The pipeline must produce `alert` rules. Under this IDS design, generated `drop` or `reject` rules would falsely imply packet enforcement.
- **[ADR-008](adr-008-soc-stack-integration.md)**: MISP is the canonical
  IOC store and the SOC stack's intel hub. The new sync component does not
  fork or duplicate that role; it consumes MISP and emits Suricata rules,
  nothing more.

## Decision

Ship a small, single-purpose Python service `aptl-misp-suricata-sync`
under the `soc` compose profile. Architecture and invariants:

1. **Tag-graduated enforcement.** The service polls MISP's
   `POST /attributes/restSearch` filtered by a configurable tag
   (`IOC_TAG_FILTER`, default `aptl:enforce`). An untagged MISP attribute remains intelligence only. The selected tag explicitly promotes it into detection. The original default ran the service with no tagged indicators. Blue participants supplied and promoted indicators during their iterations.
2. **Alert-only rules per ADR-019.** The translator hard-codes `alert`
   as the rule action across every IOC type. Any future "drop" semantics
   would require a follow-up ADR overriding ADR-019; the translator's
   `test_action_is_always_alert_never_drop` is the regression guard.
3. **Dedicated rule file.** Generated rules go to
   `/var/lib/suricata/rules/misp/misp-iocs.rules`—under Suricata's
   `default-rule-path` so the file's `filemd5`/`filesha1`/`filesha256`
   directives can reference their hash-list sidecars via documented
   relative paths. The host bind mount is `./config/suricata/rules/misp/
   → /var/lib/suricata/rules/misp` shared between the Suricata
   container and the sync service. The original tree supplied `misp-iocs.rules` and empty `misp-{md5,sha1,sha256}.list` files. They let Suricata load its paths before the first synchronization. The bind mount also avoided an initialization race. Suricata could start before synchronization without encountering a missing rule path.
   The operator-authored `local.rules` is never touched. The two files
   are concatenated by Suricata at runtime via the `rule-files:` list
   in `config/suricata/suricata.yaml`. Mixing them was rejected: it
   would conflate hand-written and intel-driven rules in `git blame`,
   in run archives, and in any operator inspection.
4. **Deterministic SID allocation.** SID is computed as
   `SID_BASE + (zlib.crc32(f"{type}|{value}") & 0x7FFFFFF)`. CRC32 over a stable composite key supplies a deterministic SID. Unlike list positions, this identity does not shift when other indicators change. On collision, the translator omits the second occurrence and logs a warning. Duplicate SIDs could prevent Suricata startup. `SID_BASE`
   defaults to `2_000_000`, well clear of the operator's hand-written
   range (current max `1000091` in `local.rules`) and well clear of ET
   Open's reserved 2.x ranges.
5. **Idempotent file writes.** ``rule_writer.write_if_changed`` reads
   the existing file (if any), compares to the would-be content, and
   only writes—atomically via `<path>.tmp` + `Path.replace`—on
   change. The header records the MISP URL, tag filter, `sid_base`, and count without a timestamp. A timestamp would change identical output and cause unnecessary reloads. The writer also produces the hash-list sidecars. A reload requires an actual rule-file or list-file change.
6. **Live reload via the unix-command socket.** `suricata.yaml` enables
   the unix-command interface at
   `/var/run/suricata/suricata-command.socket`. The sync service mounts
   the same `suricata_command_socket` named volume and speaks the
   handshake-then-`reload-rules` JSON protocol directly (~30 lines in
   `suricata_reloader.py`). This avoids dragging the `suricata` apt
   package onto the sync container just for `suricatasc`. The container
   restart that would otherwise be needed to load new rules is avoided—
   important for an interval-driven service.
7. **MISP-down preservation.** If MISP is unreachable or returns
   malformed data, the loop logs and exits the tick without writing to
   disk. The previous rule file stays in place, so a transient MISP
   outage does not collapse Suricata's intel-driven detection.
8. **Hash-content escaping.** Bytes outside `[A-Za-z0-9._-/?=&]` are
   hex-escaped via Suricata's `|XX|` notation in any `content:` value.
   The threat model covers poisoned public feeds rather than a hostile lab operator. Escaping prevents those values from becoming rule syntax. `test_rejects_quote_or_semicolon_in_value_via_escape` protects that boundary.

9. **Validation at the IOC boundary.** IPs are validated via
   :mod:`ipaddress` before insertion into rule headers. A malformed value could prevent a reload. Hash validation requires hexadecimal values of exact length: md5 32, sha1 40, and sha256 64. Invalid hash content could make a list unloadable. Invalid IOCs are
   skipped with a warning rather than poisoning the output.

10. **URL parsing via stdlib.** ``urllib.parse.urlparse`` handles
    credentials, ports, fragments, query strings, IPv6 hosts, and
    schemeless inputs correctly—none of which a hand-rolled splitter
    gets right. Hosts become lowercase without user information or ports. Paths keep query strings so indicators with different queries remain distinct.

11. **Anchored domain / host matching.** ``dns.query`` and ``http.host``
    matches use the ``dotprefix`` modifier so an IOC for ``bad.com``
    matches ``bad.com`` and ``sub.bad.com`` but not ``notbad.com``.
    Without ``dotprefix``, ``content:`` can match unrelated domains that share the indicator suffix. The transformation prevents that avoidable false positive.

12. **Reload retry on failure.** ``SyncRunner`` carries a
    ``reload_pending`` flag across ticks. A failed reload remains pending for the next tick, even if the files stay unchanged. This covers an unavailable startup socket or transient signal failure.

13. **Transactional file ordering.** Per-type hash list files
    (``misp-<type>.list``) are written *before* ``misp-iocs.rules`` on
    each tick. Hash lists are written before the rules that reference them. Reload then uses the new list content.

14. **MISP envelope drift preservation.** ``MispClient`` returns
    ``None`` for both transport failures *and* malformed envelope
    structures (missing ``response`` key, non-list ``Attribute``,
    etc.), and only returns ``[]`` for a structurally valid empty IOC
    set. Treating drift as ``[]`` would wipe the rule file on API
    changes; treating it as ``None`` preserves the last-known-good
    file.

15. **MISP API key sourced from .env.** ``MISP_API_KEY`` is required
    (no hardcoded default) for both the MISP server (as
    ``ADMIN_KEY``) and the sync service. Both compose entries
    resolve the same ``${MISP_API_KEY:?...}`` reference, satisfying
    SEC-005 for the IOC pipeline. The previous hardcoded default was
    flagged by codex security review of issue #250 and removed in the
    same PR.

16. **TLS verification posture and the `MISP_CA_CERT_PATH` hook.**
    ``MispClient`` honors three TLS modes:
    * ``MISP_VERIFY_SSL=false`` → ``curl -k`` (skip verification).
    * ``MISP_VERIFY_SSL=true`` + ``MISP_CA_CERT_PATH`` set → ``curl
      --cacert <path>`` (verify against the supplied CA bundle).
    * ``MISP_VERIFY_SSL=true`` + no path → curl's system trust store.

    The original default used the first mode because MISP self-signed at first boot. The later ADR-034 amendment supplies the lab-managed CA. SEC-006 and [issue #258](https://github.com/Brad-Edwards/aptl/issues/258) owned its broader rollout.
That rollout extended INF-005 certificate generation to MISP, TheHive, Cortex, and Shuffle.
It also covered this service, SOC MCP clients, and `aptl.core.collectors`.
SEC-006 was DRAFT in that original record.
Later ADR-034 amendments define the selected verification boundary.

    ``MISP_CA_CERT_PATH`` supplies consumer-side CA selection. Issue #258 used that existing input when enabling lab CA verification.

### Translator IOC matrix

| MISP type      | Generated rule shape                                                                       |
| -------------- | ------------------------------------------------------------------------------------------ |
| `ip-src`       | `alert ip <ioc> any -> any any (...)`—matches source IP                                  |
| `ip-dst`       | `alert ip any any -> <ioc> any (...)`—matches destination IP                             |
| `domain`/`hostname` | `alert dns ... dns.query; content:"<escaped>"; nocase`                                |
| `url`          | `alert http ... http.host; content:"<host>"; nocase[; http.uri; content:"<path>"; nocase]` |
| `sha256`/`sha1`/`md5` | one rule per type, referencing a sidecar list file via Suricata's documented relative-path lookup: `... file.data; filesha256:misp/misp-sha256.list; ...` |
| anything else  | skipped with a warning log                                                                 |

Hash IOCs are aggregated rather than rendered one-rule-per-IOC because
Suricata's `filemd5` / `filesha1` / `filesha256` keywords take a *file
of hashes* as their argument, not an inline digest. The translator
therefore emits one rule per non-empty hash type and writes the digests
themselves to `misp-<type>.list` files alongside the rule file. This is
both syntactically correct (the inline-content form Suricata would
reject) and operationally efficient (one reload regardless of how many
hashes ship).

URLs match `http.host` for the host component and `http.uri` only when
the path is non-trivial; host-only URLs do not emit a `content:"/"` URI
match (which would broadly false-positive against ordinary traffic).

### Service shape

The service is the lab's first long-running Python daemon. Layout under
`src/aptl/services/misp_suricata_sync/` is intentionally narrow so the
package can serve as a template for future services:

- `config.py`: Pydantic v2 `ServiceConfig.from_env()` mirroring
  `aptl.api.deps`'s env-then-validate pattern (no `pydantic-settings`).
- `models.py`: `MispAttribute` DTO + `RenderedRule`.
- `misp_client.py`: curl-subprocess client matching
  `aptl.core.collectors._curl_json` semantics: never raises, returns
  `None` on failure, never logs the API key.
- `translator.py`: pure: `IocTranslator.translate(...) -> list[RenderedRule]`,
  plus `render_rules_file(...)` that adds the file header.
- `rule_writer.py`: atomic, idempotent `write_if_changed`.
- `suricata_reloader.py`: unix-command socket client.
- `main.py`: `run_once`, `run_loop`, `main`. SIGTERM/SIGINT-aware.

The container is `python:3.11-slim` + `curl` + the aptl wheel installed
via `pip install .` (no extras, no PyMISP, no suricatasc). Console
script `aptl-misp-suricata-sync` is the entrypoint.

## Consequences

### Positive

- Closes the MISP→detection loop without touching ADR-019's IDS-only
  posture. Blue's threat-intel work via `aptl-threatintel` MCP now has
  a visible effect on the wire within one sync interval.
- Stable SIDs mean Suricata's reload is a no-op when MISP is quiet.
- Tag-graduated enforcement gives blue a deliberate "promote to detect"
  step instead of every MISP indicator silently becoming a rule.
- Sync service is stateless across restarts (CRC32 SID is a function of
  IOC content, not insertion order), so container restarts do not
  resequence rules and do not trigger spurious Suricata reloads.
- The service container is small (`python:3.11-slim` + curl + the aptl
  wheel) and short—the entire service is < 400 LOC of Python.

### Negative

- The lab now has a unix-command socket on the Suricata container.
  Modest attack surface: it is bound to a unix socket on a private
  Docker volume, not exposed on any network. Only the sync service
  container mounts the same volume.
- Every IOC matches Suricata's IDS-only posture—`alert`, not `drop`.
  Blue cannot author MISP IOCs that *block* traffic. Real prevention
  remains the Wazuh AR path (#248/#249). This ADR makes that boundary
  explicit so blue does not expect MISP-driven blocking.
- The service is the lab's first Python daemon, so the supervisord /
  in-process pattern that exists for Wazuh agents does not apply. New
  service is a single foreground process under restart=unless-stopped.

### Risks

- **Rule churn from a noisy upstream MISP feed.** If a feed graduates
  thousands of IOCs in a short window, Suricata will reload often.
  Mitigation: the `aptl:enforce` tag is opt-in per indicator. Lab
  default is empty. Future work could batch reloads.
- **Tag misuse.** If the wrong tag is applied to a high-traffic IOC
  (`tlp:white` instead of `aptl:enforce`, etc.), a flood of false
  positives is possible. Mitigation: the documented default is `aptl:enforce`. A general `tlp:white` tag does not promote an indicator accidentally.
- **Suricata socket protocol drift.** The handshake currently uses
  `version: 0.2`. A protocol change can produce `return: NOK` from `_send_command`. The reloader reports the failure and skips reload. The file still updates, and container restart loads it. Detection
  degrades to "rules apply on next restart," which is acceptable until
  the protocol bump is addressed.

## Verification

- 52 pytest unit tests cover translator (per-type rendering, ADR-019
  alert-only invariant, deterministic SID, collision behavior, content
  escaping), rule writer (atomicity, idempotency, no-truncate-on-error),
  reloader (handshake, reload command, missing-socket failure mode),
  MISP client (auth header, tag filter, malformed-response tolerance,
  no-API-key-in-logs invariant), config (validators), and the sync
  loop (skip-on-fetch-error, skip-on-no-change).
- E2E lab recipe: `aptl lab stop -v && aptl lab start --profiles soc`, add an IOC through the historical `aptl-threatintel` MCP with `aptl:enforce`. Wait one synchronization interval. Examine `misp-iocs.rules` and matching `suricata_logs/eve.json` alerts. The recorded file command was `docker exec aptl-suricata cat /var/lib/suricata/rules/misp/misp-iocs.rules`.

## Related

- [ADR-008](adr-008-soc-stack-integration.md): MISP and Suricata
  selection rationale.
- [ADR-019](adr-019-suricata-ids-only-prevention-via-wazuh-ar.md): Suricata IDS-only constraint.
- [#247](https://github.com/Brad-Edwards/aptl/issues/247): closed in
  ADR-019; informs why this design produces `alert` rules only.
- [#248](https://github.com/Brad-Edwards/aptl/issues/248) /
  [#249](https://github.com/Brad-Edwards/aptl/issues/249)—host-side
  enforcement (Wazuh AR). Companion to this ADR's network-side
  detection path.
- [#250](https://github.com/Brad-Edwards/aptl/issues/250): implements
  this ADR.

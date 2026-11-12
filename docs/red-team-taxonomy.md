# Red Team Activity Taxonomy

This Reference describes the OCSF activity taxonomy emitted by the red MCP server.
The implementation is `mcp/mcp-red/src/classifier.ts`.
The table and regression tests must agree with that implementation.

OCSF-aligned vocabulary follows the Python detection and attack models in `src/aptl/core/detection.py` and `src/aptl/core/attacks.py`. This includes `severity_id` values 0–6 and OCSF class IDs.

The boundary that wires this taxonomy onto live MCP command execution is
captured in [ADR-027—Red Team Structured Logging Boundary](adrs/adr-027-red-team-structured-logging.md).

## Required base fields

Every OCSF red-team record produced by `logRedTeamCommand`
(`mcp/mcp-red/src/logger.ts`) carries these fields, regardless of which
activity row matched:

| Field | Type | Source |
|---|---|---|
| `time` | number (epoch ms) | `Date.now()` at emit time—OCSF `timestamp_t` is milliseconds since the Unix epoch |
| `severity_id` | 0–6 | The classifier gives the default. The logger increases it to MEDIUM on `success: false` |
| `category_uid` | number | OCSF event category (1 System, 3 IAM, 4 Network, 5 Discovery, 6 Application)—required by OCSF Base Event |
| `category_name` | string | OCSF category name |
| `class_uid` | number | classifier match |
| `class_name` | string | classifier match (OCSF class name) |
| `activity_id` | number | classifier match |
| `type_uid` | number | `class_uid * 100 + activity_id` |
| `metadata.product.name` | `aptl-mcp-red` | constant |
| `metadata.product.vendor_name` | `APTL` | constant |
| `process.cmd_line` | string (redacted) | Command processed by shared `redact()` from `aptl-mcp-common`. Non-numeric short-`-p` values are masked first. |
| `aptl.activity_type` | string | classifier match |
| `aptl.tool` | string | Leading executable basename for matched and unmatched commands. This distinguishes tools such as `curl`, `python`, and `bash`. |
| `aptl.tool_name` | string | MCP tool name (for example `kali_run_command`) |
| `aptl.agent_name` | string | `aptl-kali-red` |
| `aptl.exit_code` | number (optional) | command exit code, when known |
| `aptl.signal` | string (optional) | terminating signal name when the command was killed |

The extractor or caller's context can populate these optional fields:

- `attacks[]`: populated when the classification carries a MITRE technique
  (`{ technique: { uid: 'T1046' }, tactic: { name: 'Discovery' } }`).
- `dst_endpoint`: `{ ip?, hostname?, port?, ports?, port_range?, cidr? }`
  from the extractor. `port_range` carries the original spec string when a
  range expansion would exceed the cap (1024 ports).
- `actor.user.name`: `target_user` from the extractor (for example `ssh user@host`,
  `hydra -l user`). This field applies only when the flag names a target user: SSH, credential brute force, or host discovery. A curl `--user user:pass` pair is a local Basic-auth credential and does not enter this field.
- `http_request.url`: extracted URL (run through `redact()` before
  storage so query-string secrets are masked).
- `connection_info.protocol_name`: extracted URL scheme.
- `file.path`: wordlist or output file path. Scoped per tool family
  (web_discovery / credential_brute_force for `-w`, scanners for `-o`).
- `status_id`: OCSF normalized outcome: `1` (Success), `2` (Failure),
  `0` (Unknown).
- `status`: OCSF normalized outcome label (`Success` / `Failure`).
- `status_code`: source-specific outcome: numeric exit code (as a
  string) when known, or signal name for signal-terminated commands.
- `duration`: `duration_ms` from the caller.
- `aptl.session_id`: propagated from the MCP tool args.

<a id="activity-catalogue"></a>

## Activity catalog

| activity_type | OCSF category_uid | OCSF class_uid / class_name | activity_id | type_uid | MITRE technique | MITRE tactic | Default severity_id | Tools / patterns |
|---|---|---|---|---|---|---|---|---|
| `port_scan` | 4 Network Activity | 4001 Network Activity | 1 (Open) | 400101 | T1046 | Discovery | LOW (2) | `nmap`, `masscan`, `rustscan`, `unicornscan` |
| `network_connection` | 4 Network Activity | 4001 Network Activity | 6 (Traffic) | 400106 | T1095 | Command and Control | MEDIUM (3) | `nc`, `ncat`, `socat` |
| `ssh_login_attempt` | 3 IAM | 3002 Authentication | 1 (Logon) | 300201 | T1021.004 | Lateral Movement | LOW (2) | `ssh`, `plink` |
| `credential_brute_force` | 3 IAM | 3002 Authentication | 1 (Logon) | 300201 | T1110 | Credential Access | HIGH (4) | `hydra`, `medusa`, `patator`, `crowbar` |
| `password_cracking` | 1 System | 1007 Process Activity | 1 (Launch) | 100701 | T1110.002 | Credential Access | MEDIUM (3) | `john`, `hashcat` |
| `web_attack` | 6 Application | 6001 Web Resources Activity | 99 (Other) | 600199 | T1190 | Initial Access | MEDIUM (3) | `sqlmap`, `nikto`, `wpscan`, `xsstrike` |
| `web_discovery` | 6 Application | 6001 Web Resources Activity | 99 (Other) | 600199 | T1595.003 | Reconnaissance | LOW (2) | `gobuster`, `dirb`, `dirbuster`, `wfuzz`, `ffuf`, `feroxbuster` |
| `host_discovery` | 5 Discovery | 5001 Device Inventory Info | 1 (Inventory Info) | 500101 | T1018 | Discovery | LOW (2) | `enum4linux` / `enum4linux-ng`, `smbclient`, `smbmap`, `crackmapexec` / `cme` / `nxc`, `nbtscan`, `rpcclient`, `ldapsearch`, `kerbrute`, `bloodhound-python` / `bloodhound.py` / `sharphound`, `arping`, `fping`, `fierce`, `whatweb`, `wafw00f`, `dnsenum`, `dnsrecon`, `dig`, `host`, `nslookup`, `tcpdump`, `tshark` |
| `remote_execution` | 3 IAM | 3002 Authentication | 1 (Logon) | 300201 | T1021 | Lateral Movement | HIGH (4) | `evil-winrm`, impacket family (`psexec.py`, `smbexec.py`, `wmiexec.py`, `dcomexec.py`, `atexec.py`, `secretsdump.py`, `getuserspns.py`, `getnpusers.py`, `ntlmrelayx.py`, and the `impacket-*` aliases) |
| `network_poisoning` | 4 Network Activity | 4001 Network Activity | 6 (Traffic) | 400106 | T1557 | Credential Access | HIGH (4) | `responder`, `inveigh`, `mitm6` |
| `credential_dumping` | 1 System | 1007 Process Activity | 1 (Launch) | 100701 | T1003 | Credential Access | HIGH (4) | `mimikatz`, `pypykatz`, `lsassy`, `gosecretsdump` |
| `exploit_framework` | 1 System | 1007 Process Activity | 1 (Launch) | 100701 | T1059 | Execution | HIGH (4) | `msfconsole`, `msfvenom`, `setoolkit`, `searchsploit`, `cewl` |
| `process_execution` (fallback) | 1 System | 1007 Process Activity | 1 (Launch) | 100701 |—|—| INFO (1) | Unmatched commands. `aptl.tool` keeps the executable basename. |

**OCSF activity-id notes.** `web_attack` and `web_discovery` use `activity_id: 99` (Other). OCSF Web Resources Activity defines IDs 1–7 as Create/Read/Update/Delete/Send/Import/Export. None means attack or wordlist scan. The record uses Other with the MITRE technique in `attacks[]`.

This keeps activity labels accurate for SIEM consumers. For example, "Import" does not describe a sqlmap injection.

`host_discovery` uses class **5001 Device Inventory Info** under category **5 Discovery**. The prior class id `1009` was an invalid mix that schema-aware consumers could not normalize.

The classifier resolves the leading executable token with these operations:

1. It splits input on top-level shell separators (`&&`, `||`, `;`, `|`) with
   single- and double-quote awareness. This means
   `nmap … && nc … 4444` classifies as `port_scan`, not `network_connection`,
   and `echo "nmap is …"` does **not** classify as `port_scan`.
2. It removes a leading `sudo` and any `KEY=value` env assignments.
3. It uses the executable's basename, so `/usr/bin/nmap` matches `nmap`.

An unmatched executable uses `process_execution`. Under ADR-027, every command produces an OCSF record instead of `null` or an exception.

### Severity defaults

The `default_severity_id` column reflects the **best-guess sensitivity of
the activity itself**, not the success/failure of the individual run. The
logger applies one promotion rule on top:

> If `success === false` and the default is below `MEDIUM`, increase the
> emitted `severity_id` to `MEDIUM`.

Failed low-severity activities, such as `port_scan` and `web_discovery`, are promoted to MEDIUM. Activities already at MEDIUM or higher keep their default. These include `credential_brute_force` and `exploit_framework`.

## Metadata extraction contract

`mcp/mcp-red/src/extractor.ts` extracts OCSF object fields from the command
string with quote-aware tokenization. Behavior is intentionally
conservative. If the command shape does not surface a field, the extractor
omits that field. It does not invent a value.

The extractor accepts these shapes:

- For **IPv4**, the extractor accepts bare addresses and validates each octet.
  It rejects out-of-range octets, such as `999.0.0.1`.
- For **IPv4 CIDR**, the extractor accepts values such as `10.0.0.0/24`.
  An out-of-range prefix length, such as `/99`, removes the CIDR and keeps the bare IP.
- For **IPv6**, the extractor accepts `::1`, `2001:db8::1`, and full-form addresses. The pattern is conservative. The extractor skips ambiguous shapes. It does not infer their attribution.
- For **ports**, the extractor accepts `-p 22` and `--port 22` for an SSH-style connection.
  It accepts scanner lists and ranges, such as `-p 22,80,443` and `-p 1-1024`.
  It rejects ports above 65535 and port 0.
- For a **`host:port` positional pair**, the extractor gets both values from `nc 10.0.0.1 4444`.
- For **SSH-style `user@host[:port]`**, the extractor populates `target_user`, `dst_endpoint.ip` / `hostname`, and `dst_endpoint.port`.
- For **`-l <user>` / `--user <user>`**, the extractor populates `target_user`.
- For **`-w <path>` / `--wordlist <path>` / `-o <path>` / `--output <path>`**, the extractor populates `file.path`.
- **URLs**: `https?://host[:port]/path` extracts the URL, hostname, port,
  and protocol. The extractor applies this to `curl`, `sqlmap`, `nikto`, `gobuster`, `wfuzz`, `ffuf`, and `feroxbuster`.
- **Credential-tool protocol token**: `hydra … <host> ssh` records `ssh`
  as `protocol`. The recognized values are: `ssh`, `ftp`, `http`, `https`, `mysql`,
  `mssql`, `postgres`, `rdp`, `smb`, `telnet`, `vnc`, `imap`, `pop3`, `snmp`.

### Credential handling

Per ADR-027, **secret values are never lifted into structured fields**.

- `hydra -p hunter2 …`: the literal password value stays only in
  `process.cmd_line`, where the shared `redact()` helper masks it.
- `hydra -P /path/to/list.txt …`: the wordlist path goes to `file.path`.
  The extractor never reads or records the file's contents.
- `Authorization: Bearer X`, `--password X`, cookie headers, URL userinfo,
  PEM blocks: the shared helper redacts these at the `process.cmd_line` boundary.

The extractor cannot eliminate the risk that a secret token appears in an
unanticipated place. The `redact()` policy is the defense against that.
The extractor only surfaces non-secret structured fields.

## Sink and transport

Two channels run in parallel from the same `postToolHook`:

1. The **OCSF SIEM stream** (`logger.ts` + `stderrJsonlSink`) emits one JSONL line per command.
   Each line starts with the literal sentinel `[OCSF] `.
   External collectors can tail the MCP server's stderr and grep for
   the sentinel. They can ignore other stderr lines.
   The logger adds classifier and extractor output for SIEM correlation.

2. The **research-grade raw capture** writer (`capture.ts`) appends every tool call as a JSONL record to
   `<APTL_STATE_DIR>/runs/<run_id>/mcp-side/tool-calls.jsonl` with run scope.
   The writer also records calls from non-command tools.
   When no admitted run ID is available, the writer uses `_unbound`. The capture is intentionally minimal: timestamp, tool
   name, redacted args, redacted result/error, exit_code, signal,
   duration, session_id. Researchers can parse this stream independently. Analysis does not depend on the classifier's choices.

   ADR-033 removed the legacy `APTL_RED_CAPTURE_PATH` override. It mounted red capture into the Wazuh manager for SIEM ingestion. The non-contamination policy forbids that path.

Per ADR-027 *as amended by ADR-033*, the OCSF records are NOT
shipped to Wazuh / OpenSearch. The legacy `kali_redteam` syslog ingestion path is removed. Kali gives neither a Wazuh agent nor rsyslog forwarding to the SIEM. Deleted rule and decoder files belong to that historical path, with retirement noted on 2026-10-12. OCSF records land in the per-run
JSONL at `<state>/runs/<run_id>/mcp-side/ocsf.jsonl` alongside the
tool-call JSONL and the PTY tee, plus a stderr `[OCSF]` line for
local development visibility.

## Cross-references

- ADR-027—boundary, guardrails, and non-goals for OCSF schema
  work (amended by ADR-033).
- ADR-033—Red-Side Behavioural Capture and Non-Contamination
  Boundary (supersedes the SIEM-transport portion of ADR-027).
- `src/aptl/core/detection.py`: `SeverityId` enum (Python source of truth
  for the 0–6 scale).
- `src/aptl/core/attacks.py`: MITRE technique reference shape.
- `mcp/aptl-mcp-common/src/redaction.ts`: shared TypeScript redaction
  used by `process.cmd_line` serialization.

# Root Compose topology reference

This Reference describes declarations in the repository's root `docker-compose.yml`.
It does not describe every installed Scenario Pack or prove a running topology.
The admitted scenario and backend observations determine realized nodes and networks.
[Network architecture](../architecture/networking.md) explains this distinction.

`webapp`, `dns`, `ad`, `db`, `fileshare`, `victim`, `workstation`, and `kali` are compatibility stubs.
Scenario realization replaces them; their `debian:13-slim` fields do not select the deployed substrate.
The root file has no mail or reverse-engineering service declaration.
Their earlier addresses are not current root Compose contracts.

## Networks

| Network | Subnet | Purpose |
|---------|--------|---------|
| aptl-security | 172.20.0.0/24 | SOC stack (Wazuh, MISP, Shuffle, Suricata mgmt) |
| aptl-dmz | 172.20.1.0/24 | DMZ service declarations (webapp and DNS) |
| aptl-internal | 172.20.2.0/24 | Enterprise services (AD, DB, file server, victim, workstation) |
| aptl-redteam | 172.20.4.0/24 | Red team (Kali) |

## Container IPs

### Security Network (172.20.0.0/24)

| Container | IP | Service |
|-----------|----|---------|
| aptl-wazuh-manager | 172.20.0.10 | Log processing, rules, alerts |
| aptl-wazuh-dashboard | 172.20.0.11 | Web UI |
| aptl-wazuh-indexer | 172.20.0.12 | OpenSearch data storage |
| aptl-misp | 172.20.0.16 | Threat intelligence |
| aptl-misp-web | 172.20.0.16 (shares the `aptl-misp` network namespace) | MISP HTTPS web tier |
| aptl-misp-db | 172.20.0.17 | MISP database |
| aptl-shuffle-backend | 172.20.0.20 | SOAR backend |
| aptl-shuffle-frontend | 172.20.0.21 | SOAR frontend |
| aptl-dns | 172.20.0.25 | DNS (security interface) |
| aptl-suricata | 172.20.0.50 | IDS (security interface) |

### DMZ Network (172.20.1.0/24)

| Container | IP | Service |
|-----------|----|---------|
| aptl-wazuh-manager | 172.20.1.10 | Log collection from DMZ |
| aptl-webapp | 172.20.1.20 | Web application |
| aptl-dns | 172.20.1.22 | DNS (DMZ interface) |
| aptl-kali | 172.20.1.30 | Red team (DMZ access) |
| aptl-suricata | 172.20.1.50 | IDS (DMZ tap) |

### Internal Network (172.20.2.0/24)

| Container | IP | Service |
|-----------|----|---------|
| aptl-ad | 172.20.2.10 | Samba AD domain controller |
| aptl-db | 172.20.2.11 | PostgreSQL database |
| aptl-fileshare | 172.20.2.12 | Samba file server |
| aptl-victim | 172.20.2.20 | Rocky Linux target |
| aptl-webapp | 172.20.2.25 | Web app (internal interface) |
| aptl-dns | 172.20.2.27 | DNS (internal interface) |
| aptl-wazuh-manager | 172.20.2.30 | Log collection from internal |
| aptl-kali | 172.20.2.35 | Red team (internal access) |
| aptl-workstation | 172.20.2.40 | Developer workstation |
| aptl-suricata | 172.20.2.50 | IDS (internal tap) |

### Red Team Network (172.20.4.0/24)

| Container | IP | Service |
|-----------|----|---------|
| aptl-kali | 172.20.4.30 | Red-team workstation |

## Host Port Mappings

These are default publications declared by root Compose services.
Each listed SOC publication binds to `127.0.0.1`.
The corresponding `APTL_HP_*` variable can select another host port.
The startup owner can allocate a free port when an unpinned default is occupied.
The [deployment guide](../deployment.md) describes supported startup and endpoint discovery.

| Host port | Container port | Service | Port variable |
| --- | --- | --- | --- |
| 443 | 5601/tcp | Wazuh Dashboard | `APTL_HP_WAZUH_DASHBOARD_5601` |
| 514 | 514/udp | Wazuh Manager syslog | `APTL_HP_WAZUH_MANAGER_514` |
| 1514 | 1514/tcp | Wazuh agent traffic | `APTL_HP_WAZUH_MANAGER_1514` |
| 1515 | 1515/tcp | Wazuh enrollment | `APTL_HP_WAZUH_MANAGER_1515` |
| 55000 | 55000/tcp | Wazuh API | `APTL_HP_WAZUH_MANAGER_55000` |
| 9200 | 9200/tcp | Wazuh Indexer API | `APTL_HP_WAZUH_INDEXER_9200` |
| 8443 | 443/tcp | MISP | `APTL_HP_MISP_443` |
| 3443 | 443/tcp | Shuffle HTTPS | `APTL_HP_SHUFFLE_FRONTEND_443` |
| 3001 | 80/tcp | Shuffle HTTP | `APTL_HP_SHUFFLE_FRONTEND_80` |

The web profile has separate API and UI publications.
`APTL_WEB_BIND_ADDRESS` defaults to `127.0.0.1` and controls their bind address.
`APTL_HP_APTL_WEB_API_8400` defaults to 8400.
`APTL_HP_APTL_WEB_UI_3000` defaults to 3000.
The [web reference](web.md) describes their authentication and deployment contracts.

Operator SSH relays belong to interactive access realization, not these root service declarations.
[Host MCP access](host-mcp-access.md) and [Kali operations](../components/kali-operations.md) describe the supported access paths.

## Sources

The root Compose file supplies the networks, stubs, addresses, and publications above.
The CLI startup and deployment owners supply port allocation and realized endpoint reporting.
These declarations do not establish installed-lab qualification.

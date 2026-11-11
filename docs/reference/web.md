# Web Interface Reference

The APTL web interface is the local operator control plane for one lab project.
It is separate from the intentionally vulnerable target web application and
from third-party SOC interfaces such as the Wazuh Dashboard. `lilrae lab info` reports the observed URLs.

## Supported Delivery

The supported direct command is:

```shell
lilrae web serve
```

It serves the built single-page application and FastAPI control plane from one
origin. The command prints a one-time login URL. The private launch URL is exchanged for a two-part browser session.
It is a secret-bearing access value.
See [run the web control plane](web-proxy.md#start-the-local-interface) for operating steps.

The command requires the Python `web` extra and built frontend assets. A source
or initialized lab project can build the frontend with its locked Node package
metadata. The Compose `web` profile gives the other supported delivery: a
static UI container and an API container behind one same-origin proxy. A supported web deployment is scenario-realized or an explicitly started local development setup.

## Serve Defaults

| Setting | Default | Supported behavior |
| --- | --- | --- |
| Bind address | `127.0.0.1` | Keeps the operator control plane on loopback. |
| Port | `8400` | Serves the single-origin UI and API when available. |
| Browser login | one-time URL | Exchanges a terminal-visible launch token for a two-part session. |
| Workers | `1` | Keeps the in-process session and terminal-ticket stores consistent. |

`lilrae web serve --help` lists the installed options.
`--api-only` is for the split Compose delivery behind its static UI proxy. It
does not give a browser interface by itself.

The split delivery's API container runs as the project owner rather than root.
`APTL_WEB_API_USER` identifies the owner's `uid:gid`.
`APTL_DOCKER_SOCKET_GID` identifies the Docker socket group.

Both values are required. An unset value prevents container startup.
The account can read private `.aptl/` state and access the selected daemon without another privilege grant.
See [configure split delivery](web-proxy.md#configure-split-delivery).

## Operator Surfaces

| Browser route | Supported behavior |
| --- | --- |
| `/` | Lab readiness, lifecycle controls, realized containers, and scenario entry points. |
| `/scenarios/<id>` | Details for a scenario returned by the validated catalog API. |
| `/terminal/<container>` | A terminal for a server-approved realized container after confirmation. |
| `/config` | A redacted, read-only projection of non-secret project and web status. |

The UI can start, stop, and emergency-kill the local lab through the same typed
core boundaries as the CLI. Destructive controls remain explicit. The browser
does not receive the API bearer token, and v1 does not persist terminal input,
terminal output, or operator notes.

## Supported API Surface

These routes support the shipped UI. They are not an unauthenticated public
automation API. Except for the one-time login exchange, HTTP routes require the
web control-plane authentication boundary. Mutating browser requests also pass
the same-origin gate.

| Method and path | Purpose |
| --- | --- |
| `GET /api/health` | Authenticated API liveness. |
| `GET /api/auth/login` | One-time launch-token exchange and browser-session bootstrap. |
| `GET /api/lab/status` | Current running, error, and container state. |
| `POST /api/lab/start` | Start the selected project scenario. |
| `POST /api/lab/stop` | Stop the project and keep its volumes. The route takes no parameters. `lilrae lab stop -v` removes volumes. |
| `GET /api/lab/events` | Server-sent lifecycle updates. |
| `POST /api/lab/kill` | Emergency project process or container termination. |
| `GET /api/config` | Redacted non-secret configuration projection. |
| `GET /api/scenarios` | Validated scenario summaries. |
| `GET /api/scenarios/{scenario_id}` | One validated scenario summary. |
| `GET /api/terminal/ticket` | Short-lived ticket for an allowed terminal target. |
| `WEBSOCKET /api/terminal/ws/{container}` | Bounded terminal session for a server-approved container. |

These routes serve the browser client.
Direct development consumers remain subject to the same typed contracts and authentication.

## Safe Exposure

See [configure a web control-plane proxy](web-proxy.md).
Loopback remains the default operator boundary.

For design rationale and contributor contracts, see the
[web GUI specification](../specs/web-gui-design.md) and
[authentication ADR](../adrs/adr-039-web-control-plane-authentication.md).

## Proxy configuration

| Setting | Contract |
| --- | --- |
| `--public-origin`, `APTL_WEB_PUBLIC_ORIGIN` | Browser-facing origin used in the printed launch URL. |
| `APTL_ALLOWED_HOSTS` | Comma-separated hostnames without ports. This setting has no CLI option. |
| Built-in hosts | `127.0.0.1`, `localhost`, and `::1` remain allowed. |
| Proxy location | TLS termination is on the same host. The API remains on loopback. |
| Forwarded host | The API uses the received `Host` to build its origin for mutating-request checks. |

## Proxy failures

| Observation | Meaning |
| --- | --- |
| HTTP 403 with `Host not allowed` | The forwarded hostname is absent from the allowed-host list. |
| HTTP 403 with `Cross-origin API request rejected` | The browser's mutation origin differs from the origin built from the received host. |

A proxy that rewrites `Host` to loopback can cause the second failure.
CORS does not establish authorization.
A non-loopback plain HTTP bind does not replace the supported TLS proxy boundary.

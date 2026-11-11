# Run the web control plane

Use the existing approved project and network boundary.
The [web reference](web.md) owns routes, authentication, defaults, settings, and failure responses.

## Start the local interface

1. Install the existing Python `web` extra and built frontend assets in the approved environment.
2. Select the intended project directory.
3. Start the supported interface:

```shell
lilrae web serve
```

4. Open the printed private login URL in the operator's browser.
5. Keep that URL out of chat, logs, issues, and other users' browsers.
6. Use the browser interface for normal lifecycle and terminal operations.
7. Use `lilrae lab info` for observed scenario URLs.

Use `--api-only` only for an explicitly selected API-only delivery.
It does not give a browser interface.

## Safe Exposure

Use this procedure only when the approved deployment requires access from another device.

1. Keep the API bound to loopback.
2. Place the approved same-host TLS proxy in front of it.
3. Set the browser-facing origin through `--public-origin` or `APTL_WEB_PUBLIC_ORIGIN`.
4. Set `APTL_ALLOWED_HOSTS` to the forwarded hostnames, without ports.
5. Keep the browser-facing `Host` header through the proxy.
6. Open the private login URL through that browser origin.
7. Before you do a mutating-request test, examine authenticated access.
8. Compare HTTP 403 responses with the [proxy failure reference](web.md#proxy-failures).

For an existing approved Tailscale deployment, the command shape is:

```shell
APTL_ALLOWED_HOSTS=<machine>.<tailnet>.ts.net lilrae web serve \
  --public-origin https://<machine>.<tailnet>.ts.net
```

Keep certificate verification and authentication enabled.
Do not place API bearer tokens in URLs.

## Configure split delivery

1. Examine the selected scenario's `web` delivery and same-origin proxy.
2. Determine the project owner's `uid:gid` through the existing host account procedure.
3. Determine the selected Docker socket's group.
4. Configure `APTL_WEB_API_USER` and `APTL_DOCKER_SOCKET_GID` in the project's private `.env`.
5. Use the existing commands in `.env.example` for these non-secret identity values.
6. Start the admitted delivery through the approved project lifecycle.
7. Before you change permissions, diagnose unset-value startup failures.

Do not run the API container as root to bypass private-state permissions.

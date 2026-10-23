"""Pure request builders for application account providers (issue #1273).

An application account provider makes one authored ``secret_fixture`` credential
true of one product, then proves it by authenticating with it. Every request
runs inside the container that serves the product, through
``curl --config -`` or ``php`` with the program text in argv and every value on
stdin: no credential reaches host or container argv, where
``/proc/<pid>/cmdline`` is world-readable (issue #1105). Requests target the
container's own loopback listener, so they never cross a network.

The module is pure. It renders curl configuration and stdin payloads, and it
parses the bounded status lines the programs print. The Compose mixin in
:mod:`aptl.core.deployment._compose_application_accounts` runs them.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Sequence
from dataclasses import dataclass, field

#: Image-owned bootstrap principal of the TheHive 5 image. It is a fact of the
#: product, not of any scenario, and the provider uses it only to create the
#: declared principal when that principal cannot authenticate yet.
THEHIVE_BOOTSTRAP_USER = "admin@thehive.local"
THEHIVE_BOOTSTRAP_PASSWORD = "secret"
#: The organisation and profile that TheHive 5 reserves for platform administrators.
THEHIVE_ADMIN_ORGANISATION = "admin"
THEHIVE_ADMIN_PROFILE = "admin"
#: Cortex reserves the ``cortex`` organisation for platform administrators.
CORTEX_ADMIN_ORGANISATION = "cortex"
CORTEX_ADMIN_ROLES = ("superadmin",)

_STATUS_FORMAT = "%{http_code}\\n"


@dataclass(frozen=True)
class CurlStep:
    """One HTTP request in a ``curl --config -`` program."""

    method: str
    path: str
    headers: tuple[str, ...] = field(default=(), repr=False)
    body: str | None = field(default=None, repr=False)


def basic_authorization(username: str, secret: str) -> str:
    """Return an HTTP Basic ``Authorization`` header line."""

    token = base64.b64encode(f"{username}:{secret}".encode()).decode("ascii")
    return f"Authorization: Basic {token}"


def json_body(payload: dict[str, object]) -> str:
    """Return a compact JSON request body."""

    return json.dumps(payload, separators=(",", ":"))


def curl_config(base_url: str, steps: Sequence[CurlStep]) -> str:
    """Render one curl configuration that runs ``steps`` in order.

    Values are JSON-quoted, which is valid curl configuration string syntax, so
    no value can end its line or inject an option. The cookie engine is on for
    every transfer, so a session cookie a login step sets reaches the next step
    in the same curl process. Each transfer prints only its HTTP status.
    """

    blocks: list[str] = []
    for step in steps:
        lines = [
            "silent",
            "insecure",
            'cookie = ""',
            'output = "/dev/null"',
            f"write-out = {json.dumps(_STATUS_FORMAT)}",
            "max-time = 30",
            f"request = {json.dumps(step.method)}",
            f"url = {json.dumps(base_url.rstrip('/') + step.path)}",
        ]
        headers = list(step.headers)
        if step.body is not None:
            headers.append("Content-Type: application/json")
            lines.append(f"data-raw = {json.dumps(step.body)}")
        lines.extend(f"header = {json.dumps(header)}" for header in headers)
        blocks.append("\n".join(lines))
    return "\nnext\n".join(blocks) + "\n"


def status_codes(stdout: str | None) -> tuple[int, ...]:
    """Parse the per-transfer status lines a curl program printed."""

    codes: list[int] = []
    for line in (stdout or "").splitlines():
        token = line.strip()
        codes.append(int(token) if token.isdigit() else 0)
    return tuple(codes)


def succeeded(code: int) -> bool:
    """Return whether an HTTP status is a 2xx success."""

    return 200 <= code < 300


# --- per-product request plans ---------------------------------------------


def opensearch_login(username: str, secret: str) -> tuple[CurlStep, ...]:
    """Prove an OpenSearch security-plugin user authenticates."""

    return (
        CurlStep(
            "GET",
            "/_plugins/_security/authinfo",
            (basic_authorization(username, secret),),
        ),
    )


def wazuh_api_login(username: str, secret: str) -> tuple[CurlStep, ...]:
    """Prove a Wazuh manager API user receives a session token."""

    return (
        CurlStep(
            "POST",
            "/security/user/authenticate",
            (basic_authorization(username, secret),),
        ),
    )


def shuffle_login(username: str, secret: str) -> tuple[CurlStep, ...]:
    """Prove a Shuffle user signs in through the API route."""

    return (
        CurlStep(
            "POST",
            "/api/v1/login",
            body=json_body({"username": username, "password": secret}),
        ),
    )


def thehive_login(username: str, secret: str) -> tuple[CurlStep, ...]:
    """Prove a TheHive user authenticates."""

    return (
        CurlStep(
            "GET",
            "/api/v1/user/current",
            (basic_authorization(username, secret),),
        ),
    )


def thehive_converge(
    username: str,
    secret: str,
    *,
    administrator: tuple[str, str] | None = None,
) -> tuple[CurlStep, ...]:
    """Create the declared administrator if absent, then set its password.

    Use an existing declared administrator when available, and the image's
    bootstrap administrator only during initial creation. The create returns
    a client error when the principal already exists; authentication readback
    decides whether the credential was applied.
    """

    authentication = (
        basic_authorization(
            *(administrator or (THEHIVE_BOOTSTRAP_USER, THEHIVE_BOOTSTRAP_PASSWORD))
        ),
    )
    return (
        CurlStep(
            "POST",
            "/api/v1/user",
            authentication,
            json_body(
                {
                    "login": username,
                    "name": username,
                    "organisation": THEHIVE_ADMIN_ORGANISATION,
                    "profile": THEHIVE_ADMIN_PROFILE,
                }
            ),
        ),
        *thehive_set_password(
            administrator or (THEHIVE_BOOTSTRAP_USER, THEHIVE_BOOTSTRAP_PASSWORD),
            username,
            secret,
        ),
    )


def thehive_set_password(
    administrator: tuple[str, str], username: str, secret: str
) -> tuple[CurlStep, ...]:
    """Set a user's password through TheHive's authenticated native API."""

    return (
        CurlStep(
            "POST",
            f"/api/v1/user/{_path_segment(username)}/password/set",
            (basic_authorization(*administrator),),
            json_body({"password": secret}),
        ),
    )


def cortex_migrate() -> tuple[CurlStep, ...]:
    """Initialize Cortex's native schema before its first user is written."""

    return (CurlStep("POST", "/api/maintenance/migrate", body="{}"),)


def cortex_login(username: str, secret: str) -> tuple[CurlStep, ...]:
    """Prove a Cortex user signs in and reads its own session."""

    return (
        CurlStep(
            "POST",
            "/api/login",
            body=json_body({"user": username, "password": secret}),
        ),
        CurlStep("GET", "/api/user/current"),
    )


def cortex_first_administrator(username: str, secret: str) -> tuple[CurlStep, ...]:
    """Create the declared administrator in Cortex's first-run window.

    Cortex accepts one unauthenticated user creation while its user index is
    empty. Creating any user closes that window, so this succeeds only on a
    fresh datastore.
    """

    return (
        CurlStep(
            "POST",
            "/api/user",
            body=json_body(
                {
                    "login": username,
                    "name": username,
                    "organization": CORTEX_ADMIN_ORGANISATION,
                    "roles": list(CORTEX_ADMIN_ROLES),
                    "password": secret,
                }
            ),
        ),
    )


def misp_key_login(secret: str) -> tuple[CurlStep, ...]:
    """Prove a MISP API key authenticates."""

    return (
        CurlStep(
            "GET",
            "/servers/getVersion",
            (f"Authorization: {secret}", "Accept: application/json"),
        ),
    )


def _path_segment(value: str) -> str:
    """Percent-encode one URL path segment."""

    from urllib.parse import quote

    return quote(value, safe="")


# --- MISP database programs ------------------------------------------------
#
# MISP refuses a caller-chosen API key over its API, and has no API to prove a
# password. Both records are bcrypt (``password_hash``/``password_verify``), so
# these programs read MISP's own database configuration and converge the row.
# The program text is fixed; every value arrives as one JSON object on stdin.
# Each prints exactly one status word.

_MISP_DATABASE = r"""
require '/var/www/MISP/app/Config/database.php';
$c = (new DATABASE_CONFIG())->default;
$dsn = 'mysql:host=' . $c['host'] . ';dbname=' . $c['database']
    . (empty($c['port']) ? '' : ';port=' . $c['port']);
$db = new PDO($dsn, $c['login'], $c['password'],
    [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
$in = json_decode(stream_get_contents(STDIN), true);
"""

MISP_PASSWORD_PROGRAM = (
    _MISP_DATABASE
    + r"""
$q = $db->prepare('SELECT id, password FROM users WHERE email = ?');
$q->execute([$in['username']]);
$row = $q->fetch(PDO::FETCH_ASSOC);
if (!$row) { echo "absent\n"; exit(0); }
if (password_verify($in['secret'], $row['password'])) { echo "current\n"; exit(0); }
$u = $db->prepare('UPDATE users SET password = ?, change_pw = 0 WHERE id = ?');
$u->execute([password_hash($in['secret'], PASSWORD_BCRYPT), $row['id']]);
$q->execute([$in['username']]);
$row = $q->fetch(PDO::FETCH_ASSOC);
echo password_verify($in['secret'], $row['password']) ? "applied\n" : "unproven\n";
"""
)

MISP_KEY_PROGRAM = (
    _MISP_DATABASE
    + r"""
$owner = $db->prepare('SELECT id FROM users WHERE email = ?');
$owner->execute([$in['owner']]);
$id = $owner->fetchColumn();
if ($id === false) { echo "absent\n"; exit(0); }
$now = time();
$live = $db->prepare('SELECT id, authkey FROM auth_keys WHERE user_id = ? AND comment = ?'
    . ' AND read_only = 1 AND (expiration = 0 OR expiration > ?)');
$live->execute([$id, $in['comment'], $now]);
foreach ($live->fetchAll(PDO::FETCH_ASSOC) as $key) {
    if (password_verify($in['secret'], $key['authkey'])) { echo "current\n"; exit(0); }
}
$db->prepare('UPDATE auth_keys SET expiration = ? WHERE user_id = ? AND comment = ?'
    . ' AND (expiration = 0 OR expiration > ?)')->execute([$now, $id, $in['comment'], $now]);
$b = bin2hex(random_bytes(16));
$uuid = sprintf('%s-%s-4%s-%x%s-%s', substr($b, 0, 8), substr($b, 8, 4),
    substr($b, 13, 3), 8 | (hexdec($b[16]) & 3), substr($b, 17, 3), substr($b, 20, 12));
$db->prepare('INSERT INTO auth_keys (uuid, authkey, authkey_start, authkey_end, created,'
    . ' expiration, read_only, user_id, comment) VALUES (?, ?, ?, ?, ?, 0, 1, ?, ?)')
    ->execute([$uuid, password_hash($in['secret'], PASSWORD_BCRYPT),
        substr($in['secret'], 0, 4), substr($in['secret'], -4), $now, $id, $in['comment']]);
echo "applied\n";
"""
)


def misp_password_input(username: str, secret: str) -> str:
    """Return the stdin payload for :data:`MISP_PASSWORD_PROGRAM`."""

    return json.dumps({"username": username, "secret": secret})


def misp_key_input(owner: str, comment: str, secret: str) -> str:
    """Return the stdin payload for :data:`MISP_KEY_PROGRAM`."""

    return json.dumps({"owner": owner, "comment": comment, "secret": secret})


def program_status(stdout: str | None) -> str:
    """Return the single status word a database program printed."""

    lines = (stdout or "").strip().splitlines()
    return lines[-1].strip() if lines else ""


__all__ = (
    "CORTEX_ADMIN_ORGANISATION",
    "CORTEX_ADMIN_ROLES",
    "MISP_KEY_PROGRAM",
    "MISP_PASSWORD_PROGRAM",
    "THEHIVE_ADMIN_ORGANISATION",
    "THEHIVE_ADMIN_PROFILE",
    "THEHIVE_BOOTSTRAP_PASSWORD",
    "THEHIVE_BOOTSTRAP_USER",
    "CurlStep",
    "basic_authorization",
    "cortex_first_administrator",
    "cortex_login",
    "cortex_migrate",
    "curl_config",
    "json_body",
    "misp_key_input",
    "misp_key_login",
    "misp_password_input",
    "opensearch_login",
    "program_status",
    "shuffle_login",
    "status_codes",
    "succeeded",
    "thehive_converge",
    "thehive_login",
    "thehive_set_password",
    "wazuh_api_login",
)

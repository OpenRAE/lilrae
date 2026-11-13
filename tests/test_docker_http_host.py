"""The Docker socket client sends a valid Host header (Docker 29 refuses a path)."""

from aptl.core.deployment.lilrae_docker_http import _UnixConnection


def test_unix_connection_names_localhost_and_connects_to_the_socket_path():
    connection = _UnixConnection("/var/run/docker.sock", timeout=1)
    assert (connection.host, connection.socket_path) == ("localhost", "/var/run/docker.sock")

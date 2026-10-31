#!/usr/bin/env python3
"""Minimal transport target/probe used inside existing network namespaces."""

from __future__ import annotations

import argparse
import ipaddress
import socket


def _address(value: str) -> str:
    parsed = ipaddress.ip_address(value)
    if parsed.is_unspecified or parsed.is_multicast:
        raise argparse.ArgumentTypeError("probe address must be unicast")
    return str(parsed)


def _port(value: str) -> int:
    parsed = int(value)
    if not 0 < parsed <= 65535:
        raise argparse.ArgumentTypeError("probe port is invalid")
    return parsed


def _listen(
    address: str,
    port: int,
    timeout: float,
    *,
    protocol: str = "tcp",
) -> int:
    family = (
        socket.AF_INET6
        if ipaddress.ip_address(address).version == 6
        else socket.AF_INET
    )
    server = socket.socket(
        family,
        socket.SOCK_DGRAM if protocol == "udp" else socket.SOCK_STREAM,
    )
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    server.settimeout(timeout)
    try:
        server.bind((address, port))
        print("ready", flush=True)
        if protocol == "udp":
            payload, peer = server.recvfrom(64)
            if payload != b"aptl-boundary-probe":
                return 1
            server.sendto(payload, peer)
        else:
            server.listen(1)
            connection, _peer = server.accept()
            connection.close()
        return 0
    except OSError, TimeoutError:
        return 1
    finally:
        server.close()


def _connect(
    address: str,
    port: int,
    timeout: float,
    *,
    protocol: str = "tcp",
) -> int:
    if protocol == "udp":
        family = (
            socket.AF_INET6
            if ipaddress.ip_address(address).version == 6
            else socket.AF_INET
        )
        connection = socket.socket(family, socket.SOCK_DGRAM)
        connection.settimeout(timeout)
        try:
            payload = b"aptl-boundary-probe"
            connection.sendto(payload, (address, port))
            reply, _peer = connection.recvfrom(64)
            return 0 if reply == payload else 1
        except OSError, TimeoutError:
            return 1
        finally:
            connection.close()
    try:
        connection = socket.create_connection((address, port), timeout=timeout)
    except OSError, TimeoutError:
        return 1
    connection.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    listener = subcommands.add_parser("listen")
    listener.add_argument("--address", type=_address, required=True)
    listener.add_argument("--port", type=_port, required=True)
    listener.add_argument("--protocol", choices=("tcp", "udp"), default="tcp")
    listener.add_argument("--timeout", type=float, default=15.0)
    connector = subcommands.add_parser("connect")
    connector.add_argument("--address", type=_address, required=True)
    connector.add_argument("--port", type=_port, required=True)
    connector.add_argument("--protocol", choices=("tcp", "udp"), default="tcp")
    connector.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()
    if not 0.1 <= args.timeout <= 30:
        parser.error("probe timeout is invalid")
    if args.command == "listen":
        return _listen(
            args.address,
            args.port,
            args.timeout,
            protocol=args.protocol,
        )
    return _connect(
        args.address,
        args.port,
        args.timeout,
        protocol=args.protocol,
    )


if __name__ == "__main__":
    raise SystemExit(main())

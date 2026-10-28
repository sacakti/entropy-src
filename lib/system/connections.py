"""
Connection checks for the database migration target, the Redis cache and the
message queue, using only the standard library (no drivers).

Each check goes as far as the protocol allows without a client library and
says exactly what it verified:

- PostgreSQL: the server answers the SSL request (credentials not checked).
- Oracle: the listener port accepts a connection (TLS too, with TCPS).
- Redis: AUTH (when set), PING and SELECT, so credentials are checked.
- ActiveMQ: a STOMP CONNECT, so credentials are checked.
- MQTT: a 3.1.1 CONNECT, so credentials are checked.
- RabbitMQ: the AMQP 0-9-1 handshake starts (credentials not checked).
- Kafka: an ApiVersions request is answered (SASL credentials not checked).
"""

from __future__ import annotations

import socket
import ssl
import struct
from typing import Any, Callable, Dict, List, Optional

TIMEOUT_SECONDS = 6.0


class ConnectionCheckError(RuntimeError):
    """The server could not be reached or refused; the message says why."""


def _connect(values: Dict[str, Any], tls: bool) -> socket.socket:
    host, port = str(values["host"]), int(values["port"])
    if not host:
        raise ConnectionCheckError("Save a host name first.")
    try:
        raw = socket.create_connection((host, port), timeout=TIMEOUT_SECONDS)
    except socket.timeout:
        raise ConnectionCheckError(
            f"{host}:{port} did not answer within {TIMEOUT_SECONDS:.0f} seconds."
        ) from None
    except OSError as exc:
        raise ConnectionCheckError(
            f"Unable to reach {host}:{port}: {exc.strerror or exc}."
        ) from None
    if not tls:
        return raw
    context = ssl.create_default_context()
    if not values.get("verify_tls", True):
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    try:
        return context.wrap_socket(raw, server_hostname=host)
    except (ssl.SSLError, OSError) as exc:
        raw.close()
        raise ConnectionCheckError(f"TLS with {host}:{port} failed: {exc}.") from None


def _read(sock: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionCheckError("The server closed the connection.")
        data += chunk
    return data


def _read_until(sock: socket.socket, end: bytes, limit: int = 65536) -> bytes:
    data = b""
    while not data.endswith(end):
        chunk = sock.recv(1)
        if not chunk:
            break
        data += chunk
        if len(data) > limit:
            raise ConnectionCheckError("The server sent an unexpectedly long answer.")
    return data


def _result(summary: str, details: List[str]) -> Dict[str, Any]:
    return {"ok": True, "summary": summary, "details": details}


Check = Callable[[Dict[str, Any]], Dict[str, Any]]


def _guard(check: Check) -> Check:
    """Socket errors during a check become ConnectionCheckError."""

    def run(values: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return check(values)
        except socket.timeout:
            raise ConnectionCheckError("The server stopped answering.") from None
        except (ssl.SSLError, OSError) as exc:
            raise ConnectionCheckError(f"The connection failed: {exc}.") from None

    return run


# ----------------------------------------------------------------------
# Database migration target
# ----------------------------------------------------------------------


@_guard
def check_database(values: Dict[str, Any]) -> Dict[str, Any]:
    target = f"{values['host']}:{values['port']}"
    if values.get("engine") == "oracle":
        with _connect(values, bool(values.get("ssl"))):
            pass
        return _result(
            f"The Oracle listener at {target} accepts connections.",
            [
                "The service name and credentials are checked when a migration runs"
                " (needs the Oracle driver)."
            ],
        )
    with _connect(values, False) as sock:
        # SSLRequest: every PostgreSQL server answers it with S or N.
        sock.sendall(struct.pack("!ii", 8, 80877103))
        answer = _read(sock, 1)
    if answer not in (b"S", b"N"):
        raise ConnectionCheckError(f"{target} answered, but not as a PostgreSQL server.")
    details = [f"TLS {'offered' if answer == b'S' else 'not offered'} by the server."]
    if values.get("ssl") and answer == b"N":
        raise ConnectionCheckError(
            f"PostgreSQL at {target} does not offer TLS, but TLS is required here."
        )
    details.append(
        "The database name and credentials are checked when a migration runs"
        " (needs the PostgreSQL driver)."
    )
    return _result(f"PostgreSQL is answering at {target}.", details)


# ----------------------------------------------------------------------
# Redis
# ----------------------------------------------------------------------


def _resp(*parts: str) -> bytes:
    encoded = [part.encode("utf-8") for part in parts]
    return b"*%d\r\n" % len(encoded) + b"".join(
        b"$%d\r\n%s\r\n" % (len(part), part) for part in encoded
    )


def _redis_reply(sock: socket.socket) -> str:
    line = _read_until(sock, b"\r\n").decode("utf-8", "replace").strip()
    if line.startswith("-"):
        raise ConnectionCheckError(f"Redis refused: {line[1:]}")
    return line


@_guard
def check_cache(values: Dict[str, Any]) -> Dict[str, Any]:
    target = f"{values['host']}:{values['port']}"
    details: List[str] = []
    with _connect(values, bool(values.get("tls"))) as sock:
        if values.get("password"):
            user = str(values.get("username") or "")
            sock.sendall(
                _resp("AUTH", user, values["password"])
                if user
                else _resp("AUTH", values["password"])
            )
            _redis_reply(sock)
            details.append(f"Signed in{f' as {user}' if user else ''}.")
        sock.sendall(_resp("PING"))
        if _redis_reply(sock) != "+PONG":
            raise ConnectionCheckError(f"{target} answered, but not as Redis.")
        database = int(values.get("database") or 0)
        if database:
            sock.sendall(_resp("SELECT", str(database)))
            _redis_reply(sock)
            details.append(f"Database {database} selected.")
        sock.sendall(_resp("QUIT"))
    return _result(f"Redis is answering at {target}.", details)


# ----------------------------------------------------------------------
# Message queues
# ----------------------------------------------------------------------


def _stomp(values: Dict[str, Any]) -> Dict[str, Any]:
    target = f"{values['host']}:{values['port']}"
    headers = [
        "accept-version:1.2,1.1,1.0",
        f"host:{values.get('virtual_host') or values['host']}",
        "heart-beat:0,0",
    ]
    if values.get("username"):
        headers += [f"login:{values['username']}", f"passcode:{values.get('password') or ''}"]
    with _connect(values, bool(values.get("tls"))) as sock:
        sock.sendall(("CONNECT\n" + "\n".join(headers) + "\n\n\0").encode("utf-8"))
        frame = _read_until(sock, b"\0").decode("utf-8", "replace")
        command, _, rest = frame.lstrip("\r\n").partition("\n")
        if command.strip() == "ERROR":
            reason = next(
                (line[8:] for line in rest.splitlines() if line.startswith("message:")), "refused"
            )
            raise ConnectionCheckError(f"ActiveMQ refused the connection: {reason}")
        if command.strip() != "CONNECTED":
            raise ConnectionCheckError(
                f"{target} answered, but not as a STOMP broker"
                " (ActiveMQ's STOMP port is usually 61613)."
            )
        sock.sendall(b"DISCONNECT\n\n\0")
    version = next((line[8:] for line in rest.splitlines() if line.startswith("version:")), "")
    return _result(
        f"ActiveMQ (STOMP {version or '1.x'}) accepted the connection at {target}.",
        ["Signed in." if values.get("username") else "Connected without credentials."],
    )


def _mqtt_string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack("!H", len(encoded)) + encoded


def _mqtt_length(size: int) -> bytes:
    out = b""
    while True:
        byte, size = size % 128, size // 128
        out += bytes([byte | (0x80 if size else 0)])
        if not size:
            return out


MQTT_REFUSALS = {
    1: "the broker does not support MQTT 3.1.1",
    2: "the client ID was rejected",
    3: "the MQTT service is unavailable",
    4: "the user name or password is wrong",
    5: "the client is not authorised",
}


def _mqtt(values: Dict[str, Any]) -> Dict[str, Any]:
    target = f"{values['host']}:{values['port']}"
    flags = 0x02  # clean session
    payload = _mqtt_string(str(values.get("client_id") or "entropy") + "-check")
    if values.get("username"):
        flags |= 0x80
        payload += _mqtt_string(str(values["username"]))
        if values.get("password"):
            flags |= 0x40
            payload += _mqtt_string(str(values["password"]))
    variable = _mqtt_string("MQTT") + bytes([4, flags]) + struct.pack("!H", 30)
    body = variable + payload
    with _connect(values, bool(values.get("tls"))) as sock:
        sock.sendall(bytes([0x10]) + _mqtt_length(len(body)) + body)
        answer = _read(sock, 4)
        if answer[0] != 0x20:
            raise ConnectionCheckError(f"{target} answered, but not as an MQTT broker.")
        if answer[3]:
            raise ConnectionCheckError(
                "The MQTT broker refused the connection: "
                f"{MQTT_REFUSALS.get(answer[3], f'code {answer[3]}')}."
            )
        sock.sendall(b"\xe0\x00")
    return _result(
        f"The MQTT broker accepted the connection at {target}.",
        ["Signed in." if values.get("username") else "Connected without credentials."],
    )


def _amqp(values: Dict[str, Any]) -> Dict[str, Any]:
    target = f"{values['host']}:{values['port']}"
    with _connect(values, bool(values.get("tls"))) as sock:
        sock.sendall(b"AMQP\x00\x00\x09\x01")
        answer = _read(sock, 8)
    if answer.startswith(b"AMQP"):
        raise ConnectionCheckError(f"{target} speaks a different AMQP version than 0-9-1.")
    # A method frame (type 1) on channel 0: Connection.Start.
    if answer[0] != 1 or answer[1:3] != b"\x00\x00":
        raise ConnectionCheckError(f"{target} answered, but not as a RabbitMQ (AMQP 0-9-1) broker.")
    return _result(
        f"RabbitMQ (AMQP 0-9-1) is answering at {target}.",
        [
            "The user name, password and virtual host are checked when Entropy connects"
            " (needs the AMQP client)."
        ],
    )


def _kafka(values: Dict[str, Any]) -> Dict[str, Any]:
    target = f"{values['host']}:{values['port']}"
    client = str(values.get("client_id") or "entropy").encode("utf-8")
    # ApiVersions v0: api key 18, version 0, correlation id 1, client id.
    request = struct.pack("!hhih", 18, 0, 1, len(client)) + client
    with _connect(values, bool(values.get("tls"))) as sock:
        sock.sendall(struct.pack("!i", len(request)) + request)
        size, correlation = struct.unpack("!ii", _read(sock, 8))
        if correlation != 1 or not 2 <= size < 1_000_000:
            raise ConnectionCheckError(f"{target} answered, but not as a Kafka broker.")
        (error,) = struct.unpack("!h", _read(sock, 2))
    if error:
        raise ConnectionCheckError(f"The Kafka broker answered with error code {error}.")
    return _result(
        f"Kafka is answering at {target}.",
        [
            "SASL credentials, when the cluster needs them, are checked when Entropy connects"
            " (needs the Kafka client)."
        ],
    )


@_guard
def check_queue(values: Dict[str, Any]) -> Dict[str, Any]:
    broker: Optional[str] = values.get("broker")
    if broker == "activemq":
        return _stomp(values)
    if broker == "mqtt":
        return _mqtt(values)
    if broker == "rabbitmq":
        return _amqp(values)
    if broker == "kafka":
        return _kafka(values)
    raise ConnectionCheckError(f"Unknown broker '{broker}'.")


CHECKS = {
    "database_target": check_database,
    "cache": check_cache,
    "queue": check_queue,
}

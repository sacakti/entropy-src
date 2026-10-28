"""Connection checks for the migration target, the cache and the queue."""

from __future__ import annotations

import contextlib
import socket
import struct
import threading
from typing import Any, Callable, Dict, Iterator, List

import pytest

from lib.database.connection import DatabaseConnection
from lib.system.connections import ConnectionCheckError, check_cache, check_database, check_queue
from lib.system.settings import SettingsError, SystemSettings

Reply = Callable[[socket.socket, List[bytes]], None]


@pytest.fixture()
def server() -> Iterator[Callable[[Reply], Dict[str, Any]]]:
    """A one-connection fake server: `reply` reads the request and answers."""

    listeners: List[socket.socket] = []

    def start(reply: Reply) -> Dict[str, Any]:
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listeners.append(listener)
        received: List[bytes] = []

        def serve() -> None:
            connection, _ = listener.accept()
            with connection:
                connection.settimeout(3)
                with contextlib.suppress(OSError):
                    reply(connection, received)

        threading.Thread(target=serve, daemon=True).start()
        return {"host": "127.0.0.1", "port": listener.getsockname()[1], "received": received}

    yield start
    for listener in listeners:
        listener.close()


def _recv(connection: socket.socket, received: List[bytes]) -> bytes:
    data = connection.recv(4096)
    received.append(data)
    return data


def test_postgres_answers_ssl_request(server: Any) -> None:
    def reply(connection: socket.socket, received: List[bytes]) -> None:
        _recv(connection, received)
        connection.sendall(b"N")

    values = server(reply)
    result = check_database({**values, "engine": "postgresql", "ssl": False})
    assert "PostgreSQL is answering" in result["summary"]
    assert values["received"][0] == struct.pack("!ii", 8, 80877103)

    values = server(reply)
    with pytest.raises(ConnectionCheckError, match="does not offer TLS"):
        check_database({**values, "engine": "postgresql", "ssl": True})


def test_redis_auth_ping_select(server: Any) -> None:
    def reply(connection: socket.socket, received: List[bytes]) -> None:
        for answer in (b"+OK\r\n", b"+PONG\r\n", b"+OK\r\n"):
            _recv(connection, received)
            connection.sendall(answer)

    values = server(reply)
    result = check_cache(
        {**values, "password": "secret", "username": "", "database": 2, "tls": False}
    )
    assert result["details"] == ["Signed in.", "Database 2 selected."]
    assert values["received"][0] == b"*2\r\n$4\r\nAUTH\r\n$6\r\nsecret\r\n"

    def refuse(connection: socket.socket, received: List[bytes]) -> None:
        _recv(connection, received)
        connection.sendall(b"-WRONGPASS invalid username-password pair\r\n")

    values = server(refuse)
    with pytest.raises(ConnectionCheckError, match="WRONGPASS"):
        check_cache({**values, "password": "bad", "database": 0})


def test_activemq_stomp(server: Any) -> None:
    def reply(connection: socket.socket, received: List[bytes]) -> None:
        _recv(connection, received)
        connection.sendall(b"CONNECTED\nversion:1.2\n\n\0")

    values = server(reply)
    result = check_queue({**values, "broker": "activemq", "username": "admin", "password": "pw"})
    assert "STOMP 1.2" in result["summary"]
    assert b"login:admin\npasscode:pw" in values["received"][0]

    def refuse(connection: socket.socket, received: List[bytes]) -> None:
        _recv(connection, received)
        connection.sendall(b"ERROR\nmessage:User name [x] or password is invalid.\n\n\0")

    values = server(refuse)
    with pytest.raises(ConnectionCheckError, match="password is invalid"):
        check_queue({**values, "broker": "activemq", "username": "x", "password": "y"})


def test_mqtt_connack_codes(server: Any) -> None:
    def accept(connection: socket.socket, received: List[bytes]) -> None:
        _recv(connection, received)
        connection.sendall(b"\x20\x02\x00\x00")

    values = server(accept)
    assert (
        "accepted" in check_queue({**values, "broker": "mqtt", "client_id": "entropy"})["summary"]
    )
    assert values["received"][0][0] == 0x10 and b"MQTT" in values["received"][0]

    def refuse(connection: socket.socket, received: List[bytes]) -> None:
        _recv(connection, received)
        connection.sendall(b"\x20\x02\x00\x04")

    values = server(refuse)
    with pytest.raises(ConnectionCheckError, match="user name or password is wrong"):
        check_queue({**values, "broker": "mqtt", "username": "u", "password": "p"})


def test_rabbitmq_and_kafka_handshakes(server: Any) -> None:
    def amqp(connection: socket.socket, received: List[bytes]) -> None:
        _recv(connection, received)
        connection.sendall(b"\x01\x00\x00\x00\x00\x01\xf4\x00")

    values = server(amqp)
    assert "RabbitMQ" in check_queue({**values, "broker": "rabbitmq"})["summary"]

    def kafka(connection: socket.socket, received: List[bytes]) -> None:
        _recv(connection, received)
        connection.sendall(struct.pack("!iih", 6, 1, 0))

    values = server(kafka)
    assert (
        "Kafka is answering"
        in check_queue({**values, "broker": "kafka", "client_id": "entropy"})["summary"]
    )


def test_unreachable_server_is_reported() -> None:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    with pytest.raises(ConnectionCheckError, match="Unable to reach"):
        check_cache({"host": "127.0.0.1", "port": port})


def test_settings_validate_and_hide_passwords(tmp_path: Any) -> None:
    store = SystemSettings(DatabaseConnection(tmp_path / "entropy.db"), key=b"k" * 32)
    with pytest.raises(SettingsError, match="host name"):
        store.update("queue", {"enabled": True, "host": ""})
    saved = store.update("cache", {"enabled": True, "host": "redis", "password": "secret"})
    assert saved["password"] == "" and saved["password_set"] is True
    assert store.values("cache")["password"] == "secret"

"""Whether a node can reach the main node, and what to tell the user."""

import pytest

from lib.nodes.provision import ProvisionError, ProvisionRequest
from lib.nodes.reach import advice, classify, classify_log, is_loopback


@pytest.mark.parametrize(
    "host", ["localhost", "127.0.0.1", "127.1.2.3", "::1", "[::1]", "0.0.0.0", "LOCALHOST"]
)
def test_loopback_hosts(host) -> None:
    assert is_loopback(host)


@pytest.mark.parametrize("host", ["10.0.0.5", "build-1.example.com", "192.168.1.20", ""])
def test_other_hosts(host) -> None:
    assert not is_loopback(host)


@pytest.mark.parametrize(
    ("output", "kind"),
    [
        ('ok 200 {"status":"ok","application":"entropy","initialized":true}', "ok"),
        ("ok 200 <html>nginx</html>", "other-service"),
        ("ok 404", "http"),
        (
            "fail curl-7 curl: (7) Failed to connect to 10.0.0.1 port 8000: Connection refused",
            "refused",
        ),
        ("fail curl-28 curl: (28) Connection timed out after 8001 milliseconds", "timeout"),
        ("fail curl-6 curl: (6) Could not resolve host: nope", "dns"),
        ("fail curl-60 curl: (60) SSL certificate problem", "tls"),
        ("fail refused [Errno 111] Connection refused", "refused"),
        ("fail other [Errno 113] timed out", "timeout"),
        ("fail wget-4 wget: unable to resolve host address 'x'", "other"),
        ("notool", "notool"),
        ("", "notool"),
    ],
)
def test_probe_output_is_classified(output, kind) -> None:
    assert classify(output)[0] == kind


def test_agent_log_is_classified() -> None:
    assert (
        classify_log("Heartbeat failed: <urlopen error [Errno 111] Connection refused>")
        == "refused"
    )
    assert classify_log("POST /api/agent/jobs/claim failed: <urlopen error timed out>") == "timeout"


def test_advice_names_the_cause_and_the_fix() -> None:
    local = {"local_only": True, "bind_host": "127.0.0.1", "port": 8000, "suggestions": []}
    assert "points at the node itself" in advice("refused", "http://localhost:8000", local)
    assert "ent web config --host 0.0.0.0" in advice("refused", "http://10.0.0.2:8000", local)
    reachable = {"local_only": False, "suggestions": ["http://10.0.0.2:8000"]}
    timeout = advice("timeout", "http://10.0.0.2:8000", reachable)
    assert "firewall" in timeout and "http://10.0.0.2:8000" in timeout


def _request(host: str, url: str) -> ProvisionRequest:
    return ProvisionRequest(name="build-1", host=host, port=22, ssh_user="deploy", server_url=url)


def test_a_remote_node_may_not_use_a_loopback_url() -> None:
    with pytest.raises(ProvisionError, match="points at the node itself"):
        _request("10.0.0.7", "http://localhost:8000").validate()
    _request("10.0.0.7", "http://10.0.0.2:8000").validate()
    # A node on this very machine may use localhost.
    _request("127.0.0.1", "http://localhost:8000").validate()


def test_a_node_on_this_machine_may_use_loopback() -> None:
    local = {"local_only": True, "bind_host": "127.0.0.1", "port": 8000, "suggestions": []}
    text = advice("refused", "http://127.0.0.1:8999", local, node_host="127.0.0.1")
    assert "nothing accepts connections" in text and "node itself" not in text


def test_listening_on_every_interface_is_not_local_only(monkeypatch) -> None:
    from lib.nodes import reach

    monkeypatch.setattr(reach, "bind_address", lambda: ("0.0.0.0", 8000))
    info = reach.server_addresses()
    assert not info["local_only"]
    assert all(url.endswith(":8000") for url in info["suggestions"])

    monkeypatch.setattr(reach, "bind_address", lambda: ("127.0.0.1", 8000))
    assert reach.server_addresses() == {
        "bind_host": "127.0.0.1",
        "port": 8000,
        "local_only": True,
        "suggestions": [],
    }
